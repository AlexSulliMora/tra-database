# SEC EDGAR data products

> **Verification status.** Direct WebFetch against `*.sec.gov` returned HTTP 403 to the research tooling, so content here was synthesized from third-party SEC documentation mirrors plus search-result summaries citing the canonical SEC pages. Canonical verification of any specific endpoint or response shape happens when the S2 Python client (with its own conforming User-Agent header) is invoked against it.

Catalog of public data products the SEC offers, with one canonical URL per product and a note on when to prefer it over alternatives. For URL templates and parameter detail see [access patterns](access-patterns.md); for rate and authentication constraints see [limitations](limitations.md); for schema and naming conventions see [conventions](conventions.md).

The Securities and Exchange Commission (SEC) publishes filings via the Electronic Data Gathering, Analysis, and Retrieval system (EDGAR). The data products below are all public, free, and unauthenticated.

## Submissions API

Endpoint: `https://data.sec.gov/submissions/CIK<10-digit-zero-padded>.json`

Example: `https://data.sec.gov/submissions/CIK0000320193.json`

Returns one company's identifying metadata (name, Central Index Key (CIK), Standard Industrial Classification (SIC) code, addresses, tickers, exchanges, former names) plus a columnar listing of its filing history. The `filings.recent` block holds the most recent ~1,000 filings; older filings are spread across continuation JSON files referenced under `filings.files`. Updated in real time as filings are accepted (processing delay typically under one second per the SEC's API documentation).

Prefer this over the legacy `browse-edgar` Atom feed for any case where you want structured per-company filing metadata. The columnar layout reads cleanly into a polars DataFrame.

## Company Facts API

Endpoint: `https://data.sec.gov/api/xbrl/companyfacts/CIK<10-digit-zero-padded>.json`

Returns every eXtensible Business Reporting Language (XBRL) numeric fact this company has ever reported, organized by taxonomy and tag, with each tag carrying one or more unit-of-measure arrays of fact records. Each fact gives `val`, `end` (period end date), `accn` (accession), `fy`, `fp`, `form`, `filed`.

Prefer when you need many concepts for one company in one fetch. The response can be large (several megabytes for a long-lived large filer); for a single concept time series, use Company Concept instead.

## Company Concept API

Endpoint: `https://data.sec.gov/api/xbrl/companyconcept/CIK<10-digit-zero-padded>/<taxonomy>/<Tag>.json`

Example: `https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/AccountsPayableCurrent.json`

Returns the time series of one XBRL tag for one company. Taxonomy slugs: `us-gaap`, `ifrs-full`, `dei` (Document and Entity Information), `srt` (SEC Reporting Taxonomy).

Prefer when you only want one metric and a long history; much smaller payload than Company Facts.

## XBRL Frames API

Endpoint: `https://data.sec.gov/api/xbrl/frames/<taxonomy>/<Tag>/<unit>/<period>.json`

Example: `https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY2019Q1I.json`

Returns one tag's value across every company that reported it at a single fiscal period. Period grammar (see [access patterns](access-patterns.md)): `CY####` annual, `CY####Q#` quarterly duration, `CY####Q#I` quarterly instantaneous. The frame collapses the XBRL universe along the company dimension, which is the opposite slice of Company Concept.

Prefer for cross-sectional analysis at one point in time (e.g., distribution of cash holdings across S&P 500 at 2024Q4 end).

## EDGAR Full-Text Search

Endpoint: `https://efts.sec.gov/LATEST/search-index`

Query parameters: `q` (search string, quotes for phrase), `forms` (comma-separated form types), `dateRange=custom` with `startdt`/`enddt` in `YYYY-MM-DD`, `from` (offset), `size` (page size, max 100). Returns JSON with `hits.total.value`, `hits.hits[]._source.adsh`, `display_names`, `ciks`, `form`, `file_date`.

Coverage: full text of EDGAR filings from 2001 forward, including primary documents and exhibits. Indexing is fast (sub-second for most filings) but trails filing acceptance; see [limitations](limitations.md) for known lag.

Prefer text search when the search target is a phrase that lives in unstructured filing text (e.g., "tax receivable agreement", "Up-C", "termination of the TRA"). Prefer Submissions API when you already know the CIK and form-type filter is enough.

## Financial Statement Data Sets (DERA bulk dumps)

Landing page: `https://www.sec.gov/dera/data/financial-statement-data-sets`

Direct quarterly download URL pattern: `https://www.sec.gov/files/dera/data/financial-statement-data-sets/<YYYY>q<1-4>.zip`

Example: `https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q1.zip`

The Division of Economic and Risk Analysis (DERA) publishes one zip per quarter (and a monthly "notes" variant for newer data) containing the structured numeric and textual XBRL fact tables: `sub.tsv` (filing-level metadata), `num.tsv` (numeric facts), `txt.tsv` (text facts), `pre.tsv` (presentation), `tag.tsv`, `dim.tsv`, `cal.tsv`, `ren.tsv`. This is the dataset the `2025_11_notes/` directory in the active project derives from.

Notes-variant URL pattern: `https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/<YYYY>q<1-4>_notes.zip` (or monthly variants).

Prefer the bulk dumps for cohort-scale analyses (panel regressions over thousands of filers); prefer the JSON APIs for selective per-filer fetches. The two surfaces draw from the same underlying XBRL submissions.

## ATOM/RSS feeds

Per-company filing feed: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=<FORM>&output=atom`

Site-wide new-filings feed: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=<FORM>&output=atom`

EDGAR's RSS feeds landing page: `https://www.sec.gov/about/rss-feeds`

The Atom feeds are the SEC's push-style channel. They predate the JSON APIs but remain the right tool for monitoring: a single periodic fetch tells you what's new without re-scanning a full filing history. The site-wide `action=getcurrent` feed (filtered by `type=8-K`) is the natural mechanism for the project's 8-K monitoring sketch.

## Company tickers mapping

Files:

- `https://www.sec.gov/files/company_tickers.json`: CIK to ticker to company name.
- `https://www.sec.gov/files/company_tickers_exchange.json`: adds exchange (NYSE, Nasdaq, etc.).

These are the canonical CIK <-> ticker bridges. Use them once at startup; the SEC notes the files are updated periodically and offers no accuracy guarantee, but they are the only first-party mapping available.

## Index files (historical bulk)

Landing: `https://www.sec.gov/Archives/edgar/full-index/`

URL pattern: `https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<1-4>/<master|company|form>.idx`

Example: `https://www.sec.gov/Archives/edgar/full-index/2024/QTR1/form.idx`

Pipe-delimited (with `master.idx` carrying the canonical ordering by CIK then accession). Each row gives form, CIK, company, filing date, filename. Daily indexes live at `Archives/edgar/daily-index/<YYYY>/QTR<1-4>/`.

Prefer the index files for historical sweeps where every filing of a class matters and the JSON APIs would require thousands of per-CIK fetches.

## Choosing the right product

| Question | Product |
|----------|---------|
| What did this firm file? | Submissions API |
| What's every XBRL fact this firm reported? | Company Facts |
| Time series of one metric for one firm | Company Concept |
| Cross-section of one metric at one period | XBRL Frames |
| Filings mentioning a phrase | text search |
| Bulk numeric data, many firms, many quarters | Financial Statement Data Sets |
| New filings as they appear | Atom feeds (`getcurrent`) |
| CIK from a ticker | `company_tickers.json` |
| Every filing in 2024 Q1 (any firm, any form) | Index files |

## Sources

- EDGAR Application Programming Interfaces (APIs): `https://www.sec.gov/search-filings/edgar-application-programming-interfaces` (SEC; canonical page returned HTTP 403 to WebFetch, summarized from search-result content)
- Accessing EDGAR Data: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data` (SEC)
- EDGAR Full-Text Search FAQ: `https://www.sec.gov/edgar/search/efts-faq.html` (SEC)
- DERA Financial Statement Data Sets landing: `https://www.sec.gov/dera/data/financial-statement-data-sets` (SEC)
- Company Tickers: `https://www.sec.gov/file/company-tickers` (SEC)
- EDGAR RSS Feeds: `https://www.sec.gov/about/rss-feeds` (SEC)
- "data.sec.gov XBRL API", tldrfiling.com: `https://tldrfiling.com/blog/sec-edgar-api-guide`
- "Full-Text Search API", tldrfiling.com: `https://tldrfiling.com/blog/sec-edgar-full-text-search-api`
