---
name: tra-download-filings
description: >-
  Given a list of CIKs, download all TRA-relevant SEC filings (10-K,
  10-Q, 8-K, S-1, S-4, prospectus variants, proxy) to a local directory
  tree. Run this skill standalone before invoking tra-process-filings;
  do not invoke from inside another agent running SEC queries.
---

# TRA filing downloader

## Purpose

For each CIK in a supplied list, locate every TRA-relevant filing via
EDGAR full-text search, then download the specific matched document to a
local directory tree. The skill is intentionally isolated: running SEC
queries from multiple concurrent agents risks breaching the 10 req/sec
rate cap. Run this skill to completion before spawning other agents that
read the same firms' filings.

## Universal constraints

- All SEC interaction goes through `scripts/sec_edgar/` (invoked as
  `PYTHONPATH=scripts pixi run python ...` from `<project root>`).
- `EdgarClient` enforces the 10 req/sec rate cap; do not add a second
  throttle layer.
- Wrap every `search_filings()` call with the 5xx retry loop described
  in [Retry wrapper](#retry-wrapper). The search module does not retry on
  HTTP 5xx errors internally.
- Never write output filenames starting with `report`, `summary`,
  `findings`, or `analysis` (the subagent Write tool blocks those
  prefixes).
- Do not use the acronym "EFTS"; write "EDGAR full-text search" or
  "full-text search" in any notes or logs.

## Inputs

| Parameter | Type | Notes |
|-----------|------|-------|
| `ciks` | list of strings | CIK strings. The SEC full-text-search `ciks` parameter requires the 10-digit zero-padded form (e.g. `0001775625`); passing the unpadded form (`1775625`) silently returns zero hits. The implementation must zero-pad internally so callers may pass either form. |
| `output_dir` | path | Root directory for downloaded files. Created if absent. |

## Outputs

Files saved at `<output_dir>/<CIK>/<accession>/<filename>`. The
`<filename>` is the `primary_doc` field from the search result, which
names the specific document (not the full filing) that matched the query.
Cache writes go through `.tra_history_cache/` via the normal `EdgarClient`
path; the output directory is a separate, caller-owned tree.

## Workflow

### Step 1: build the search union per CIK

For each CIK, run three `search_filings()` calls:

**Query A (phrase, TRA name variants):**

```python
q = (
    '"tax receivable agreement" OR "tax receivable agreements" '
    'OR "tax receivables agreement" OR "tax receivables agreements"'
)
```

**Query B (token):**

```python
q = "TRA"
```

**Query C (corporate events):**

```python
q = (
    '"Chapter 11" OR "Chapter 7" OR "voluntary petition" '
    'OR "plan of reorganization" OR "plan of liquidation" '
    'OR "rejection of executory contracts" '
    'OR "agreement and plan of merger" OR "merger consideration" '
    'OR "tender offer" OR "asset purchase agreement" '
    'OR "going-private"'
)
```

Rationale for query C: a firm's most TRA-impactful events (bankruptcy
filing, M&A close, going-private wind-down) often occur in filings
that do not contain the literal phrase "tax receivable agreement", so
queries A and B miss them. The events query closes that gap by
matching the standard legal phrases that mark these triggers. Union
its post-allow-list results into the same `(adsh, primary_doc)` set
used for downloads, and track its hits and net-new contributions
separately in the manifest (`events_hits_raw`, `events_hits`,
`events_form_breakdown`).

All three calls **omit the `forms` parameter** and apply form filtering
locally on the returned LazyFrame:

```python
ciks = "<zero-padded CIK>"
# No forms arg, no startdt / enddt.
lf, meta = search_with_retry(q, ciks=ciks)
```

**SEC quirk (important):** the EDGAR full-text-search `forms`
parameter has a parser bug when the comma-separated list contains
slash-bearing form codes (e.g. `10-K/A`, `10-Q/A`, `8-K/A`, `S-1/A`,
`S-4/A`, `DRS/A`): the server silently drops the result count to ~0.
Confirmed empirically on Vince Holding: `forms=10-K` returned 16 hits;
adding `10-K/A` to the same query returned 0. Do not re-add the
`forms` parameter to the search call. Post-filter the `form` column
locally instead:

```python
ALLOWED_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "6-K",
    "DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A",
    "8-K", "8-K/A",
    "S-1", "S-1/A", "S-4", "S-4/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "DRS", "DRS/A",
}
df = lf.collect().filter(pl.col("form").is_in(ALLOWED_FORMS))
```

Take the union of the three filtered result sets by `adsh` +
`primary_doc`. When the same `(adsh, primary_doc)` pair appears in
more than one query, keep one copy.

### Step 2: download the matched document per result

For each `(adsh, primary_doc)` pair in the union:

```python
from sec_edgar.archives import fetch_document

body, meta = fetch_document(cik, adsh, primary_doc)
# Write body to: <output_dir>/<CIK>/<adsh>/<primary_doc>
```

`fetch_document` handles cache lookup and returns cached bytes on
subsequent runs; the output directory write is idempotent if you check
for an existing file before writing.

Do not download the full filing SGML envelope or all exhibits for search
hits; the matched document is sufficient at this stage. `tra-process-filings`
fetches exhibits separately when it identifies TRA contracts.

### Step 3: S-1 / S-1/A / S-4 / S-4/A / 424B completeness pass

The search index may miss earlier versions of registration statements
if the TRA phrase was added or removed across amendments. After step 2,
enumerate all versions for each form type in
`{S-1, S-1/A, S-4, S-4/A, 424B1, 424B2, 424B3, 424B4, 424B5}`:

```python
from sec_edgar.forms import list_filings_by_form

for form_type in ("S-1", "S-1/A", "S-4", "S-4/A",
                  "424B1", "424B2", "424B3", "424B4", "424B5"):
    lf = list_filings_by_form(cik, form_type)
    # For each accession not already in the downloaded set, fetch
    # the primary document via fetch_document and write to output_dir.
```

A firm can announce a TRA in an early S-1, revise or remove it in a
later S-1/A, and that change is real signal. All versions are needed.

### Step 4: log the manifest

After all CIKs complete, write a manifest file at
`<output_dir>/download_log.md`. One section per CIK with:

- Total filings found (union count).
- Total documents downloaded.
- Any `(adsh, primary_doc)` pairs where `fetch_document` raised an error
  (log the exception type and message; do not swallow).
- Whether the S-1/S-4/424B completeness pass added any accessions beyond
  the search union.

## Retry wrapper

`search_filings` does not retry on HTTP 5xx. Wrap every call:

```python
import time
import httpx
from sec_edgar.search import search_filings

def search_with_retry(*args, max_attempts: int = 3, backoff_s: float = 1.5, **kwargs):
    for attempt in range(max_attempts):
        try:
            return search_filings(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_attempts - 1:
                time.sleep(backoff_s)
                continue
            raise
```

Caller code: replace bare `search_filings(...)` with
`search_with_retry(...)`.

## Running the skill

```bash
# From <project root>
PYTHONPATH=scripts pixi run python - <<'EOF'
from tra_download import download_filings

download_filings(
    ciks=["0000320193"],          # Apple Inc, for trial run
    output_dir="scratch/filings",
)
EOF
```

The above assumes you have assembled the steps above into a callable
function (e.g., in `scripts/tra_download.py`). The exact module layout
is at the coder's discretion; the interface contract is the `ciks` +
`output_dir` pair.

## What this skill does not do

- Read or classify downloaded documents (that is `tra-process-filings`).
- Build timelines or narratives (that is `tra-build-timeline`).
- Retain old downloads when a CIK is re-run; the output directory is
  append-safe but not a managed database.
