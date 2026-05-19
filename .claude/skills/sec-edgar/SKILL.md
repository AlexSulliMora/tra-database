---
name: sec-edgar
description: >-
  Fetch SEC EDGAR filings (HTML, XML, JSON, PDF) by CIK, accession number,
  form type, or date range, with rate-limited and cache-aware access. Use this
  skill when a task requires pulling a company's filing history, retrieving the
  body of a specific filing, listing filings of a given form type within a date
  window, or discovering filings across firms via keyword search. Typical
  triggers: "get Apple's 10-K filings", "pull the document for accession
  0000320193-23-000106", "search for 8-Ks mentioning 'tax receivable
  agreement'", or "verify a TRA cancellation from the source filing".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# SEC EDGAR Skill

The `sec_edgar` Python package (at `scripts/sec_edgar/` in the `tra` project) provides rate-limited, cache-aware access to the Electronic Data Gathering, Analysis, and Retrieval (EDGAR) system operated by the Securities and Exchange Commission (SEC). It targets 9 requests per second against the 10/sec SEC hard cap, caches responses under `.tra_history_cache/edgar_*/`, and returns polars `LazyFrame`s for tabular results. The package does not cover bulk Financial Statement Data Set downloads or XBRL cross-sectional queries; those remain in the `2025_11_notes/` pipeline.

**PYTHONPATH requirement.** Import the package by prepending `scripts/` to `PYTHONPATH`:

```bash
PYTHONPATH=scripts pixi run python -c "from sec_edgar import fetch_filing"
```

Or inside a script:

```python
import sys
sys.path.insert(0, "scripts")   # path relative to project root
from sec_edgar import fetch_submissions, fetch_filing, list_filings_by_form, search_filings
```

**User-Agent.** The SEC rejects requests from generic headers. The active contact email is `sulli98@uw.edu`; if you need to change it, edit `client.USER_AGENT` in `scripts/sec_edgar/client.py`.

For endpoint selection guidance, see [access patterns](references/access-patterns.md), [data products](references/resources.md), [rate and access rules](references/limitations.md), and [naming conventions](references/conventions.md).

---

## Operation: `fetch-by-CIK`

**Purpose.** Retrieve a company's full filing history and static entity metadata from the Submissions API (`https://data.sec.gov/submissions/CIK<10>.json`). Returns all filings, including those in continuation JSON files, merged into one `LazyFrame`.

**Function.** `fetch_submissions` from `sec_edgar.submissions`.

**Signature.**

```python
fetch_submissions(
    cik: str | int,
    client: EdgarClient | None = None,
    cache_max_age_s: float | None = None,
) -> tuple[pl.LazyFrame, dict]
```

**Inputs.**

| Argument | Type | Notes |
|---|---|---|
| `cik` | `str` or `int` | Zero-padded 10-digit preferred (`"0000320193"`), or bare integer (`320193`). |
| `client` | `EdgarClient` or `None` | Pass a shared client when making multiple calls in one script; `None` creates and closes one automatically. |
| `cache_max_age_s` | `float` or `None` | Override the 7-day cache freshness window. Pass `0` to force a fresh fetch. |

**Outputs.**

- `LazyFrame`: one row per filing. Columns include `accessionNumber`, `filingDate`, `reportDate`, `form`, `primaryDocument`, `primaryDocDescription`, `items`, `size`. All ~1,000 recent filings plus any continuation blocks are merged; the total row count for a long-lived filer can exceed 2,000.
- `dict`: static entity fields, including `name`, `cik`, `sic`, `sicDescription`, `tickers`, `exchanges`, `addresses`, `formerNames`.

**Worked example.**

```python
import sys
import polars as pl
sys.path.insert(0, "scripts")
from sec_edgar import fetch_submissions

lf, static = fetch_submissions("0000320193")
print(static["name"], static["sic"])           # Apple Inc. 3571
print(lf.collect().height)                     # 2231
print(lf.filter(pl.col("form") == "10-K").collect().height)  # 30
```

Expected output:

```
Apple Inc. 3571
2231
30
```

**Caveats.** The `filings.recent` block covers the most recent ~1,000 filings; `fetch_submissions` automatically fetches continuation files for older history. The 7-day cache means a company that filed yesterday may not appear until the cache expires; pass `cache_max_age_s=0` if recency is critical.

---

## Operation: `fetch-by-accession`

**Purpose.** Pull the primary document of a specific filing, identified by the registrant's Central Index Key (CIK) and accession number. Also returns a `LazyFrame` of every document in the filing folder (the index). Use this when you need the actual text (or bytes) of a 10-K, an 8-K exhibit, or any other filing document.

**Function.** `fetch_filing` from `sec_edgar.forms`.

**Signature.**

```python
fetch_filing(
    cik: str | int,
    accession: str,
    client: EdgarClient | None = None,
) -> tuple[str | bytes, pl.LazyFrame]
```

**Inputs.**

| Argument | Type | Notes |
|---|---|---|
| `cik` | `str` or `int` | Registrant's CIK. Zero-padded 10-digit or bare integer. |
| `accession` | `str` | Dashed accession number, e.g. `"0000320193-23-000106"`. |

**Outputs.**

- `str` (HTML) or `bytes` (PDF): body of the primary document.
- `LazyFrame`: one row per document in the filing folder. Columns include `name` (filename), `type`, `description`, `size`.

**Worked example.**

```python
import sys
sys.path.insert(0, "scripts")
from sec_edgar import fetch_filing

body, idx_lf = fetch_filing("0000320193", "0000320193-23-000106")
print(len(body))            # 1558924
print(type(body))           # <class 'str'>
print(idx_lf.collect().height)   # 99
```

To fetch a specific non-primary document (e.g., an exhibit) visible in the index:

```python
from sec_edgar import fetch_document

idx_df = idx_lf.collect()
# Find the Tax Receivable Agreement exhibit, if present
exhibit = idx_df.filter(
    idx_df["description"].str.contains("Tax Receivable", literal=False)
)
if exhibit.height > 0:
    filename = exhibit["name"][0]
    exhibit_body = fetch_document("0000320193", "0000320193-23-000106", filename)
```

**Caveats.** `fetch_filing` first tries to resolve the primary document name from the Submissions JSON (one fewer HTTP call). If the accession is absent from the Submissions cache, it falls back to fetching `index.json`. HTML is returned as `str`; PDFs are returned as `bytes`. The archive cache freshness is 30 days, since accepted filings are immutable.

---

## Operation: `fetch-by-form-type`

**Purpose.** List all filings of a given form type for one company, with an optional date range. Returns a filtered view of the company's Submissions history. Use this when the task is "show me all of Apple's 8-K filings since 2022" or "find the most recent 10-K for CIK X".

**Function.** `list_filings_by_form` from `sec_edgar.forms`.

**Signature.**

```python
list_filings_by_form(
    cik: str | int,
    form_type: str,
    startdt: str | date | None = None,
    enddt: str | date | None = None,
    client: EdgarClient | None = None,
) -> pl.LazyFrame
```

**Inputs.**

| Argument | Type | Notes |
|---|---|---|
| `cik` | `str` or `int` | Registrant's CIK. |
| `form_type` | `str` | Exact form string, e.g. `"10-K"`, `"8-K"`, `"S-1"`. Amendments require `"8-K/A"` explicitly. |
| `startdt` | `str` or `date` or `None` | Inclusive lower bound on `filingDate`, as `"YYYY-MM-DD"` string or `datetime.date`. |
| `enddt` | `str` or `date` or `None` | Inclusive upper bound on `filingDate`. |

**Output.** `LazyFrame` with the same columns as `fetch_submissions` output, filtered to the matching form type and date range. Call `.collect()` to materialize.

**Worked example.**

```python
import sys
sys.path.insert(0, "scripts")
from sec_edgar import list_filings_by_form

lf = list_filings_by_form("0000320193", "10-K", startdt="2020-01-01")
df = lf.collect()
print(df.select(["accessionNumber", "filingDate", "form"]))
```

Expected output (5 rows, one per annual 10-K since FY2019):

```
shape: (5, 3)
┌────────────────────────────┬────────────┬──────┐
│ accessionNumber            │ filingDate │ form │
╞════════════════════════════╪════════════╪══════╡
│ 0000320193-24-000123       │ 2024-11-01 │ 10-K │
│ 0000320193-23-000106       │ 2023-11-03 │ 10-K │
│ …                          │ …          │ …    │
└────────────────────────────┴────────────┴──────┘
```

**Caveats.** The filter is an exact string match on the `form` column; `"10-K"` does not match `"10-K/A"`. The underlying `fetch_submissions` call is cached, so repeated calls for the same CIK within the freshness window cost no network round-trips.

---

## Operation: `search-filings`

**Purpose.** Discover filings across all companies using the EDGAR full-text search endpoint (`https://efts.sec.gov/LATEST/search-index`). The text search index covers filing body text and exhibits from 2001 onward; use it when the task is phrase-driven rather than CIK-driven, e.g., "find 8-Ks mentioning 'tax receivable agreement' in 2024".

**Function.** `search_filings` from `sec_edgar.search`.

**Signature.**

```python
search_filings(
    q: str,
    forms: str | None = None,
    startdt: str | None = None,
    enddt: str | None = None,
    max_results: int | None = None,
    client: EdgarClient | None = None,
) -> tuple[pl.LazyFrame, dict]
```

**Inputs.**

| Argument | Type | Notes |
|---|---|---|
| `q` | `str` | Query string. Double-quote a phrase for exact match: `'"tax receivable agreement"'`. Supports boolean operators. |
| `forms` | `str` or `None` | Comma-separated form types, e.g. `"8-K"` or `"8-K,10-K"`. `None` searches all forms. |
| `startdt` | `str` or `None` | `"YYYY-MM-DD"` lower bound on filing date. |
| `enddt` | `str` or `None` | `"YYYY-MM-DD"` upper bound on filing date. |
| `max_results` | `int` or `None` | Cap total rows fetched. The text search API paginates at 100 per page; `search_filings` auto-pages up to this limit. `None` fetches all available results up to the 10,000-result ceiling. |

**Outputs.**

- `LazyFrame`: one row per matching filing. Columns include `adsh` (accession number, dashed), `ciks` (list; a single hit can match multiple filers), `display_names`, `form`, `file_date`, `period_of_report`, `snippet`, and `primary_doc` (the matching document filename parsed from the text search `_id` field).
- `dict`: search metadata, including `total` (total hits), `relation` (`"eq"` when exact, `"gte"` when the 10,000-result cap was hit), `fetched`, `hit_cap`.

**The `adsh` / `primary_doc` split.** The text search API encodes both fields into a single composite `_id` value formatted as `<accession>:<filename>`. `search_filings` splits this into `adsh` (bare dashed accession, directly usable by `fetch_filing` and `fetch_document`) and `primary_doc` (the matching filename, usable as the third argument to `fetch_document` if you want to pull that specific exhibit rather than the filing's primary document).

**Worked example.**

```python
import sys
sys.path.insert(0, "scripts")
from sec_edgar import search_filings

lf, meta = search_filings(
    q='"tax receivable agreement"',
    forms="8-K",
    startdt="2024-01-01",
    enddt="2024-12-31",
    max_results=250,
)
print(meta)
# {'total': 580, 'relation': 'eq', 'fetched': 250, 'hit_cap': False}

df = lf.collect()
print(df.select(["adsh", "display_names", "file_date", "primary_doc"]).head(3))
```

To then pull the matching document body for the first hit:

```python
from sec_edgar import fetch_document

row = df.row(0, named=True)
# ciks is a list; take the first entry for the primary filer
body = fetch_document(row["ciks"][0], row["adsh"], row["primary_doc"])
```

**Caveats.** The text search index covers filings from 2001 onward; earlier filings are absent. The total addressable result set per query is capped at 10,000: `from + size <= 10000`. When `meta["relation"] == "gte"`, the result set was truncated; partition the query by year or form type to recover the full set. Text search cache freshness is 1 day, since the index is live.

---

## Operation: `fetch-company-concept`

**Purpose.** Retrieve the time series of one XBRL fact for one company from the Company Concept API (`https://data.sec.gov/api/xbrl/companyconcept/CIK<10>/<taxonomy>/<concept>.json`). Returns one row per period the company reported the tag, across all unit-of-measure variants. The wrapper handles 404 (concept not tagged for this company) as a non-error path, returning an empty LazyFrame plus a meta-dict flag.

**Function.** `fetch_concept` from `sec_edgar.concept`; the convenience wrapper `fetch_tra_liability_series` walks a fallback chain of TRA-related concept tags.

**Signature.**

```python
fetch_concept(
    cik: str | int,
    concept: str,
    taxonomy: str = "us-gaap",
    client: EdgarClient | None = None,
) -> tuple[pl.LazyFrame, dict]

fetch_tra_liability_series(
    cik: str | int,
    client: EdgarClient | None = None,
) -> tuple[pl.LazyFrame, dict]
```

**Inputs.**

| Argument | Type | Notes |
|---|---|---|
| `cik` | `str` or `int` | Zero-padded 10-digit preferred. |
| `concept` | `str` | XBRL tag name (e.g. `LiabilitiesUnderTaxReceivableAgreements`, `DeferredTaxLiabilitiesNoncurrent`). |
| `taxonomy` | `str` | One of `us-gaap`, `ifrs-full`, `dei`, `srt`. Default `us-gaap`. |

**Outputs.**

- `LazyFrame`: columns `end` (period end date), `val` (value), `unit` (e.g. `USD`), `accn`, `fy`, `fp`, `form`, `filed`, `frame`. Empty when the concept is not tagged for this CIK.
- `dict`: `found` (bool), `taxonomy`, `concept`, `label`, `description`, `url`. The `fetch_tra_liability_series` variant adds `tried` (list of the fallback walk).

**Worked example.**

```python
from sec_edgar.concept import fetch_tra_liability_series

lf, meta = fetch_tra_liability_series("0001638833")  # Surgery Partners
print(meta["taxonomy"], meta["concept"], meta["found"])  # us-gaap DeferredTaxLiabilitiesNoncurrent True
print(lf.collect().sort("end").select(["end", "val", "form"]).tail(3))
```

**Caveats.** Many TRA-issuing firms tag the TRA liability using a filer-specific (custom) concept rather than a standard us-gaap concept; the Company Concept API does not expose custom tags, so `found` returns False for every fallback. In that case, fall back to the Company Facts API at `https://data.sec.gov/api/xbrl/companyfacts/CIK<10>.json` (not currently wrapped) or read the TRA liability directly from the periodic filings' tax footnotes.

---

## TRA search terminology

The EDGAR full-text index matches exact strings; a query for "tax receivable agreement" misses filings that use only the plural "tax receivable agreements", and vice versa. For Tax Receivable Agreement (TRA) work, run both queries and union the results.

Common variants and how to handle them:

- **Singular vs. plural:** run `"tax receivable agreement"` and `"tax receivable agreements"` as separate calls; deduplicate on `adsh`.
- **Abbreviation-only references:** some 8-K exhibit cover pages and press releases mention only "TRA" or "TRAs" after defining the term earlier in the document. A phrase search on "tax receivable" (without "agreement") catches these but produces more noise; use it only for a secondary pass after the two exact-phrase queries.
- **Capitalization:** EDGAR full-text search is case-insensitive, so "Tax Receivable Agreement", "tax receivable agreement", and "TAX RECEIVABLE AGREEMENT" all match the same query. No special handling needed.
- **Hyphenated forms:** the form "tax-receivable agreement" is rare and non-standard, but present in a small number of older filings. If coverage is critical, add a third query for `"tax-receivable agreement"`.

The `adsh` column is the natural deduplication key when combining results from multiple queries.

---

## Troubleshooting

**HTTP 403.** Either the User-Agent header is wrong or the SEC's rate limit was exceeded. Check `client.USER_AGENT` in `scripts/sec_edgar/client.py`; it must include a human-resolvable name and a real email address (current value: `tra-research-pipeline Alex Sullivan sulli98@uw.edu`). If the request rate was the cause, the block clears after roughly 10 minutes; the client's token bucket should prevent this under normal single-process use.

**HTTP 429.** The client's token bucket targets 9 requests per second and handles transient 429 responses with a narrow retry loop. Sustained 429 errors indicate a second concurrent process is sharing the same source IP; reduce total request rate across both processes.

**HTTP 404.** The filing does not exist at the constructed URL. Verify the accession number format (dashed, 20 characters) and confirm the CIK is the registrant's, not the filer's (these differ when a financial printer submitted on the registrant's behalf).

**Import error (`ModuleNotFoundError: No module named 'sec_edgar'`).** `PYTHONPATH` must include the project's `scripts/` directory. From the project root: `export PYTHONPATH=scripts` or prepend inline: `PYTHONPATH=scripts pixi run python yourscript.py`.

**Changing the contact email.** Edit `USER_AGENT` at the top of `scripts/sec_edgar/client.py`. The string is applied to every outgoing request via the `httpx.Client` default headers; no other files need changing.
