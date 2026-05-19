# SEC EDGAR access patterns

> **Verification status.** Direct WebFetch against `*.sec.gov` returned HTTP 403 to the research tooling, so content here was synthesized from third-party SEC documentation mirrors plus search-result summaries citing the canonical SEC pages. Canonical verification of any specific endpoint or response shape happens when the S2 Python client (with its own conforming User-Agent header) is invoked against it.

How to pull SEC Electronic Data Gathering, Analysis, and Retrieval (EDGAR) data programmatically. This file lists the endpoint surfaces with one verifiable example URL each. For schema details see [conventions](conventions.md); for rate/auth constraints see [limitations](limitations.md); for product-by-product comparisons see [resources](resources.md).

Two host roots matter:

- `data.sec.gov` returns JSON; this is the modern REST surface for company filings metadata and XBRL (eXtensible Business Reporting Language).
- `www.sec.gov/Archives/edgar/` serves the underlying filing documents (HTML, XML, JSON, PDF) and the historical index files.

All endpoints below are public, unauthenticated, and require a User-Agent header (see [limitations](limitations.md)).

## data.sec.gov JSON endpoints

### Submissions API (filing history per company)

Each registrant's full filing history:

```
GET https://data.sec.gov/submissions/CIK##########.json
```

`##########` is the Central Index Key (CIK), 10 digits, zero-padded. Example for Apple Inc. (CIK 320193):

```
https://data.sec.gov/submissions/CIK0000320193.json
```

Top-level keys include `name`, `cik`, `sic`, `sicDescription`, `tickers`, `exchanges`, `addresses`, `formerNames`, and `filings`. The `filings.recent` object holds the most recent ~1,000 filings as parallel columnar arrays: `accessionNumber[]`, `filingDate[]`, `reportDate[]`, `form[]`, `primaryDocument[]`, `primaryDocDescription[]`, `items[]` (for 8-K), `size[]`, plus index-aligned siblings. Older filings live in `filings.files[]`, each entry pointing at a continuation JSON of the form `CIK##########-submissions-001.json`, fetched from the same host. (Verified against community summaries of the SEC's documentation; field list is the documented contract, exact column set varies across submissions.)

### Company Facts API (every XBRL fact for one company)

```
GET https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
```

Returns every numeric XBRL fact across every filing for that CIK, organized as `facts.us-gaap.<TagName>.units.<UoM>[]`. Each fact carries `end`, `val`, `accn` (accession), `fy`, `fp`, `form`, `filed`. Useful when you want a full time series of, say, every `AccountsPayableCurrent` value Apple ever reported.

### Company Concept API (one tag, one company, time series)

```
GET https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<TagName>.json
```

Example:

```
https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/AccountsPayableCurrent.json
```

Cheaper than Company Facts when you only want one concept. Taxonomy slug is one of `us-gaap`, `ifrs-full`, `dei`, `srt`.

### XBRL Frames API (one tag across all companies at one period)

```
GET https://data.sec.gov/api/xbrl/frames/<taxonomy>/<Tag>/<unit>/<period>.json
```

Example:

```
https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY2019Q1I.json
```

Period grammar:

- `CY####` for calendar-year annual durations (filings reporting ~365 days, +/- 30).
- `CY####Q#` for calendar-quarter durations (~91 days, +/- 30).
- `CY####Q#I` for instantaneous (point-in-time) values; the trailing `I` is required for balance-sheet tags.

Returns one fact per company that reported the tag at that period. The "frame" answers cross-sectional questions ("what did everyone report for cash at end of Q1 2019") in a single request.

## www.sec.gov/Archives primary documents

### Filing folder

Every accepted filing lives at:

```
https://www.sec.gov/Archives/edgar/data/<CIK_no_padding>/<accession_no_dashes>/
```

Example (Tesla 10-K, accession 0000950170-22-000796):

```
https://www.sec.gov/Archives/edgar/data/1318605/000095017022000796/
```

`accession_no_dashes` is the 18-digit accession with dashes stripped. CIK in this path may be unpadded.

### Index file inside a filing folder

Each filing folder contains three index variants, one human-readable and two machine-readable:

```
.../<accession_no_dashes>/<accession_with_dashes>-index.htm
.../<accession_no_dashes>/index.json
.../<accession_no_dashes>/index.xml
```

`index.json` is the natural fetch for programmatic discovery; it lists every document in the filing with size, type, and a relative URL to construct the primary-document link. The primary document filename also appears in the Submissions API under `filings.recent.primaryDocument[i]`; one HTTP call to Submissions can usually substitute for an index fetch.

### Bulk index files for catch-up crawling

For historical or batch discovery rather than per-CIK pulls:

```
https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<1-4>/master.idx
https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<1-4>/company.idx
https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<1-4>/form.idx
```

Same content, three sort orders (CIK / company name / form type). Each row gives form, CIK, company name, filing date, and a relative path to the filing text. Use these when you need every filing of a given form over a long window without paging the JSON APIs.

## Full-text search (efts.sec.gov)

EDGAR full-text search backs the search box at `www.sec.gov/edgar/search/`. JSON endpoint:

```
GET https://efts.sec.gov/LATEST/search-index?q=<query>&forms=<form>&dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD&from=<offset>&size=<n>
```

Example (search for the phrase "tax receivable agreement" in 8-K filings in 2024):

```
https://efts.sec.gov/LATEST/search-index?q=%22tax+receivable+agreement%22&forms=8-K&dateRange=custom&startdt=2024-01-01&enddt=2024-12-31
```

Documented parameters:

- `q`: query string. Double-quote a phrase for exact match; supports boolean operators.
- `forms`: comma-separated form types (e.g. `8-K,10-K`).
- `dateRange`: pass `custom` and supply `startdt` and `enddt` in `YYYY-MM-DD` form.
- `from`: zero-indexed offset for pagination.
- `size`: results per page, default 10, max 100.

Response shape (`hits.hits[]._source` per filing): `display_names`, `ciks`, `adsh`, `form`, `file_date`, `period_of_report`, `file_description`. Pagination caps at 10,000 results total (`from + size <= 10000`); see [limitations](limitations.md).

Coverage starts in 2001 and includes filing primary documents and attached exhibits.

## ATOM and RSS feeds (monitoring)

EDGAR exposes Atom-format feeds via the legacy `browse-edgar` CGI. Two patterns matter:

### Per-company feed

```
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=<FORM>&dateb=&owner=include&count=40&output=atom
```

Example (Apple's recent 8-K filings):

```
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=8-K&dateb=&owner=include&count=40&output=atom
```

Parameters: `CIK`, `type` (form prefix; `8-K` also matches `8-K/A`), `dateb` (filings before this date, YYYYMMDD), `datea` (filings on/after), `count` (max 100), `start` (offset), `owner` (`include`/`exclude` insider ownership filings), `action` (`getcompany`), `output=atom`.

### Site-wide newest filings feed

```
https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=<FORM>&company=&dateb=&owner=include&count=40&output=atom
```

Use `action=getcurrent` for the live stream of newly accepted filings; combine with `type=` to monitor a single form-class arrival rate (e.g. all new 8-Ks). This is the right pattern for the project's "8-K monitoring after a Tax Receivable Agreement-bearing IPO" sketch in S5.

The legacy `getcompany` Atom feed predates `data.sec.gov/submissions/` and overlaps with it; prefer Submissions for filing history, and Atom for change-detection / push-style monitoring.

## Sitemap

`https://www.sec.gov/robots.txt` lists two SEC sitemap entries: `https://www.sec.gov/sec-sitemap.xml` and `https://www.sec.gov/sitemap/sitemap-index.xml`. These index static pages (rules, news, search-assistance) for crawlers and are not useful for filing discovery. Use the sitemap only when the goal is to find SEC content outside `/Archives/edgar/` (rules, staff guidance, press releases). For filings, do not start at the sitemap; the Archives directory listings, index files, Submissions API, and full-text search together cover every filing.

The robots.txt `Allow: /Archives/edgar/data` rule explicitly permits crawlers over the filing tree; the SEC's stance is that automated access is fine within the rate limit ([limitations](limitations.md)).

## Choosing among surfaces

| Need | Use |
|------|-----|
| Every filing for one company | Submissions API |
| One financial metric across many quarters for one company | Company Concept |
| One financial metric across many companies at one period | XBRL Frames |
| Free-text search across filing body and exhibits | text search |
| Live monitoring of new filings for one company | per-company Atom feed |
| Live monitoring of all filings of a form type | site-wide `action=getcurrent` Atom |
| Bulk historical sweep of every filing in a window | full-index `master.idx` files |
| The actual filing document (10-K HTML, exhibit, financial-statement R-files) | `Archives/edgar/data/<CIK>/<accession_no_dashes>/` |

## Sources

- EDGAR Application Programming Interfaces (APIs): `https://www.sec.gov/search-filings/edgar-application-programming-interfaces` (SEC; canonical doc page returned HTTP 403 to the WebFetch tool, summarized from search results)
- Accessing EDGAR Data: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data` (SEC)
- EDGAR Full-Text Search FAQ: `https://www.sec.gov/edgar/search/efts-faq.html` (SEC)
- "data.sec.gov XBRL API: CompanyFacts, CompanyConcept, Submissions", tldrfiling.com: `https://tldrfiling.com/blog/sec-edgar-api-guide` (verified via WebFetch)
- "SEC EDGAR Full-Text Search API", tldrfiling.com: `https://tldrfiling.com/blog/sec-edgar-full-text-search-api` (verified via WebFetch)
- Cross-Company XBRL example URL: `https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY2019Q1I.json` (SEC, returned in search-result enumeration)
