# SEC EDGAR limitations and access rules

> **Verification status.** Direct WebFetch against `*.sec.gov` returned HTTP 403 to the research tooling, so content here was synthesized from third-party SEC documentation mirrors plus search-result summaries citing the canonical SEC pages. Canonical verification of any specific rate-limit or pagination claim happens when the S2 Python client (with its own conforming User-Agent header) is invoked against it.

What you must do (or not do) when hitting Electronic Data Gathering, Analysis, and Retrieval (EDGAR) endpoints. Violating any of the rules below typically returns a 403 Forbidden response and triggers a short IP-level block (the enforcement mechanism is a hard block, with no soft warning preceding it). For URL patterns see [access patterns](access-patterns.md); for product choice see [resources](resources.md); for schema and naming see [conventions](conventions.md).

## Rate limit: 10 requests per second per IP

The Securities and Exchange Commission (SEC) caps EDGAR traffic at 10 requests per second across all hosts (`www.sec.gov`, `data.sec.gov`, `efts.sec.gov`), counted per source IP. The cap applies per effective user: every machine under one operator shares the same 10/sec budget, so parallelizing across servers does not increase headroom.

Exceeding the cap yields a 403 Forbidden response on subsequent requests and a temporary IP-level block (~10 minutes per the SEC's published guidance). The block applies to all EDGAR hosts during its duration.

Practical implementation in Python:

- Implement a token-bucket or simple sleep-throttle in the client wrapper. Targeting ~7-8 requests/second leaves headroom for retries and protocol overhead.
- Backoff on 403: log, sleep for the documented block window, retry with reduced concurrency.
- Cache aggressively on disk; the cheapest way to stay under the limit is to not re-fetch.

## User-Agent header required

EDGAR rejects requests that lack a recognizable User-Agent header. Generic strings (`python-requests/2.x`, `curl/8.x`, empty) are blocked. The SEC's documented format is the requester's name or organization followed by a contact email:

```
User-Agent: <Organization or Name> <contact email>
```

For this project, the active contact email is `sulli98@uw.edu`. A concrete acceptable header:

```
User-Agent: Alex Sullivan sulli98@uw.edu
```

Equally acceptable variations seen in third-party documentation and tooling: `MyApp/1.0 (sulli98@uw.edu)`, `UW Research sulli98@uw.edu`. The load-bearing requirement is a human-resolvable identifier and a real email address. The SEC reserves the right to reach out via that email to discuss traffic patterns.

Set this header on every request, including ones to `data.sec.gov`, `www.sec.gov/Archives/`, and `efts.sec.gov`. Some endpoints additionally expect `Accept-Encoding: gzip, deflate` and a plain `Host` header; the standard `httpx` or `requests` defaults satisfy this.

## No authentication, no API keys

EDGAR has no OAuth, no token registration, no rate-tier upgrade path. Every endpoint is public. This means:

- All rate limiting is client-side: there is no server signal telling you how close to the budget you are, only the 403 after you cross it. Build the throttle in deliberately; do not rely on adaptive feedback.
- No paid tier exists. Third-party services (sec-api.io, edgar-online, etc.) sit on top of EDGAR and charge for value-add (parsed exhibits, normalized fields, faster index); they do not unlock higher SEC rate limits, since the underlying SEC limit is per source IP.

## Pagination limits

### Submissions API

The Submissions JSON returns at most ~1,000 filings in the `filings.recent` block. Filings older than that live in continuation files referenced under `filings.files[]`, each entry pointing at `CIK<10-digit-padded>-submissions-NNN.json` (same host, same auth model). To get the full filing history of a long-lived large filer, you must fetch the base JSON, then iterate over `filings.files`.

### Full-Text Search

The EDGAR full-text search API at `https://efts.sec.gov/LATEST/search-index` caps total addressable results at 10,000 per query: `from + size <= 10000`. Any query whose `hits.total.value` exceeds 10,000 cannot be paged past the 10,000th result. The `relation` field in `hits.total` is `"eq"` when the exact count is computed; for larger result sets it switches to `"gte"` and the count becomes a lower bound. The 10,000-cap claim is sourced from third-party documentation mirrors; S2's trial run against an intentionally over-broad query is the verification point.

Workaround: partition the query along an orthogonal dimension. Common partitions: by year/quarter (`dateRange=custom&startdt=...&enddt=...`), by form (`forms=8-K` then `forms=10-K`, etc.), by ticker, or by CIK range. Smaller per-partition result sets stay under the cap.

### Index files and Atom feeds

`browse-edgar` Atom feed `count` parameter caps at 100; paginate with `start`. Index files (`master.idx`, etc.) are static, not paginated.

## Full-text search indexing lag

Full-text search coverage starts in 2001. Within that window the index is fast but not instantaneous: third-party measurements suggest sub-second to a few-second lag from filing acceptance to searchability for most filings, with occasional minutes-scale tails. The SEC has not published a service-level commitment on indexing latency.

Practical consequence: for time-critical monitoring (e.g., "did this firm just file a 1.02 termination"), the Atom feed at `action=getcurrent` is the right primary signal; text search supplements it for keyword filtering once filings are in the index. Do not assume a query made within the first minute after a 5:30 PM Eastern close window has caught up.

## JSON-accessible vs HTML-only content

| Content surface | JSON-accessible | Notes |
|---|---|---|
| Filing metadata (CIK, form, date, accession) | yes | Submissions API |
| Numeric XBRL facts | yes | Company Facts / Concept / Frames |
| Text XBRL facts | partial | The Division of Economic and Risk Analysis (DERA) bulk dumps include `txt.tsv` |
| Full filing body (10-K narrative, MD&A) | no | HTML or inline XBRL (iXBRL) only |
| Exhibits (material contracts, Tax Receivable Agreements) | no | HTML/PDF in `Archives/edgar/data/<CIK>/<accession>/` |
| Full-text keyword search | yes | text search endpoint (`efts.sec.gov`), structured JSON response |
| Filing index (which documents are in this submission) | yes | `index.json` in the filing folder, or Submissions API |

For Tax Receivable Agreement (TRA) work specifically: the agreement text itself lives in an exhibit (typically Exhibit 10.x) and must be fetched as HTML. The agreement's existence and termination signals are visible in JSON via the Submissions API (form types, 8-K item numbers) and text search (phrase search), but the contract body requires HTML retrieval.

## Search index coverage gaps

The full-text index is most reliable for textual content within the primary filing and standard exhibits. Filings before 2001 are not in the full-text index at all; for those, the index files and Submissions API are the only routes.

Image-only PDFs (rare in modern filings but present in older submissions) are not indexed for full text, since EDGAR does not run optical character recognition (OCR) on filings.

## What's allowed, in writing

The SEC's `robots.txt` explicitly permits crawling of `/Archives/edgar/data/` (the filing tree); the rate limit, not crawler-blocking, is the enforcement mechanism. The same file disallows several non-public paths (`/Archives/bin/`, `/cgi-bin/` other than the documented endpoints, internal Variable Prospectus Risk Return (VPRR) directories). Respect those.

## Sources

- SEC announcement of rate-control limits: `https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits` (SEC)
- Accessing EDGAR Data: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data` (SEC; describes User-Agent requirement and rate limit)
- Developer Resources: `https://www.sec.gov/about/developer-resources` (SEC; canonical page returned HTTP 403 to WebFetch, summarized from search-result content)
- Webmaster FAQ: `https://www.sec.gov/about/webmaster-frequently-asked-questions` (SEC)
- Sample EDGAR header (User-Agent format guidance): `https://www.sec.gov/edgar/searchedgar/sampleheader.htm` (SEC)
- "SEC EDGAR Rate Limits: 10 req/s Fair Access Policy", dealcharts.org: `https://dealcharts.org/blog/edgar-scraping-rate-limits-explained`
- "SEC EDGAR Full-Text Search API", tldrfiling.com (10,000-result pagination cap documentation): `https://tldrfiling.com/blog/sec-edgar-full-text-search-api`
- `https://www.sec.gov/robots.txt` (verbatim fetch returned 403; rules summarized from third-party mirrors and search results)
