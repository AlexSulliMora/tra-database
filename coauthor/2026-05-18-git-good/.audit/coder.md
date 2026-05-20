
## 2026-05-19T20:30:07-07:00

**Tool**: SendMessage
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

New task on the same TRA project at /home/sulli/research/tra/.

## Background

EDGAR full-text search returns one hit per matched *document*, and each hit's `_source` carries a `file_type` field naming the exhibit type ("EX-10.1", "EX-99.1", "8-K", etc.), verified in the cached responses under `.tra_history_cache/edgar_search/`. Our search wrapper currently discards `file_type`.

The cost: `data/edgar-query/full-text.parquet` is one row per filing, so `pull_exhibits.py` downloads every EX-10 exhibit in any TRA-mentioning filing. We want instead to keep only the EX-10 documents that themselves matched the TRA phrase, since the search already tells us exactly which document the phrase appeared in.

## Change two files

1. **`scripts/sec_edgar/search.py`** — in `_hit_to_row`, also extract `file_type` from `_source`. Add `"file_type"` to the `HIT_COLUMNS` tuple. Purely additive: do not remove or rename any existing field; other callers depend on the current schema.

2. **`scripts/find_candidates.py`** — two changes:
   - Carry `file_type` through the union. The union currently does `group_by("adsh").agg(...)`, collapsing to one row per filing. Because `file_type` is per-document, change the grouping so each matched EX-10 document is its own row: group by document identity (`adsh` plus the matched filename `primary_doc`) rather than `adsh` alone. Two distinct EX-10 exhibits in one filing then stay as two rows, while the same document matched by several phrase variants still collapses into one row with `phrase_variants_matched` unioned. Handle the case where `primary_doc` is null.
   - Filter the output parquet to keep only rows whose `file_type` matches `EX-10.*` (EX-10, EX-10.1, EX-10.27, and so on). Inspect the actual `file_type` values in the cached search JSON first so the match pattern is right; match case-insensitively. Report any TRA-relevant hits with a null or non-standard `file_type` that the filter would drop.

## Rebuild the parquet

Re-run `find_candidates.py` over the same month range as the original sweep, writing back to `data/edgar-query/full-text.parquet`. The documented range is 2001-01 through 2026-05 (the README step 1 example; cross-check `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md` for the exact bounds used). Every search page is already cached at `.tra_history_cache/edgar_search/` with the full `_source` including `file_type`, so pass a large `cache_max_age_s` (the search cache otherwise expires after 1 day) so the re-run reads from cache and makes no network calls. If a few windows miss the cache, letting them re-fetch is fine.

## Report

The new parquet's row count and how it compares to the 22,251-filing original; distinct CIK count; the distribution of `file_type` values you observed and the exact EX-10 match pattern you used; any hits dropped due to null or odd `file_type`.

Run Python with `pixi run -- python` (the package import needs `PYTHONPATH=scripts`). Ad-hoc task, no DEVIATIONS file: put everything in your response. Do not touch `pull_exhibits.py`; updating it to consume the new schema is a separate follow-up.

### Response



---
