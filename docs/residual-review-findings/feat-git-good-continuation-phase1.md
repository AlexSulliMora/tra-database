# Phase 1 — residual code-review findings

Recorded: 2026-05-26
Branch: `feat/git-good-continuation`
Source review: `/tmp/compound-engineering/ce-code-review/20260526-014234-1d62dbeb/`
Reviewers: ce-correctness, ce-adversarial, ce-testing, ce-maintainability, ce-project-standards, ce-agent-native, ce-learnings-researcher

## What was fixed before shipping

**5 safe_auto fixes** (autofix-applied):
- Deleted unreachable defensive raise in `_search_with_retry`
- Removed unused `typing.Iterable` imports
- Dropped never-needed `_pad_cik` / `_accession_no_dashes` backward-compat aliases
- Consolidated `atomic_write_parquet` / `write_manifest_atomic` to one canonical name
- Replaced `# type: ignore` + duck-typed sentinel in self-test with `unittest.mock.patch.object`

**7 P1 fixes** (user-selected from Residual Work Gate):
- R1: `discovery.parquet` write now uses `atomic_write_parquet`
- R2: `sweep_discovery` always re-runs; cache lives at the EdgarClient layer; documented
- R3: `_read_merger_map` validates flattened-CSV invariant — raises if any successor also appears as a predecessor (catches operator-error chains loudly)
- R4: `windows._self_test()` exercises the halving branch + double-overflow `WindowOverflowError` via monkeypatch of `_search_with_retry`
- R5: `discovery._self_test()` covers 5 synthetic scenarios for `_union_documents` (multi-variant union, null-primary-doc sentinel, distinct-EX-10s, form-filter, WindowOverflowError accumulator)
- R6: `registry._self_test()` covers AE2/AE3/PG&E-style slug/collision-suffix/all error paths; `_slugify` extracted as a testable helper
- R7: pure-function test of `_classify_status` covering all 7 exception branches against `FETCH_STATUS_VALUES`

## Residual P2 findings (deferred)

| # | File | Title | autofix_class | Reviewer (confidence) |
|---|---|---|---|---|
| R8 | `acquisition.py:_classify_status` | HTTP 429 after retry exhaustion classified as terminal `rate-limited` — permanently absent from corpus on restart with no in-band recovery signal | gated_auto | adversarial (80) |
| R9 | `driver.py:run_phase1` per-firm loop | Per-firm `append_rows` raises on first bad vocab value; all `firm_new_rows` lost from manifest while remaining on disk; restart re-emits and re-fails on the same row | gated_auto | adversarial (80) |
| R10 | `driver.py:_self_test` | Smoke-test docstring claims AE5 coverage but doesn't assert any `fetch_status != success`; empty-discovery branch and "first run with no manifest file" defensive write also untested | manual | testing (75) |
| R11 | `acquisition.py` re-emit branch | Re-emit branch only asserts `phrase_variants_matched` is truthy; doesn't verify `doc_description`, `exhibit_match_source`, `doc_type`, `form`, `filed_date` are correctly carried from discovery row | manual | testing (75) |
| R12 | `acquisition.py:acquire_filing` | `fetch_filing_index_html` failure branch (parse-error row emission) and `done_set` fast-path both untested | manual | testing (80) |
| R13 | `driver.py:_self_test` | Smoke-test asserts `first_rows >= 1` total but not per-variant; a future EDGAR change that breaks 4 of 5 phrase variants passes the smoke-test while losing 80% of production coverage | manual | adversarial (75) |

## Residual P3 findings (deferred)

| # | File | Title | autofix_class | Reviewer (confidence) |
|---|---|---|---|---|
| R14 | `done_marker.py:write_marker` | Non-atomic `write_text` — inconsistent with the tmp+rename discipline used elsewhere; crash mid-write yields corrupt YAML marker | gated_auto | correctness (75) |
| R15 | `discovery.py:_union_documents` | Schema inconsistency: with-hits path opportunistically adds `period_of_report`/`file_description`; no-hits early return uses only `DISCOVERY_COLUMNS` | gated_auto | correctness (75) |
| R16 | `driver.py:run_phase1` | Overflow errors logged but done marker still written — breaks "manifest is canonical for this range" contract | gated_auto | correctness (75) |
| R17 | `driver.py:_first_cik` vs `acquisition.py` | Inconsistent CIK handling: driver silently skips non-digit ciks, acquisition raises on them. Discovery rows with empty/null ciks silently skipped at driver layer, making the accession invisible to Phase 2 | gated_auto | adversarial+correctness (80) |
| R18 | `acquisition.py` | Cache path collision when a filing's primary doc is literally named `index.htm` (collides with HTML-index cache slot) | gated_auto | adversarial (65) |
| R19 | `discovery.py:DISCOVERY_COLUMNS` | Constant declares 9 columns but `_union_documents` emits 9/10/11 depending on upstream; constant name implies schema contract but isn't | gated_auto | maintainability (75) |
| R20 | `driver.py:_first_cik` & `registry.py:_flatten_discovery_ciks` | Duplicate CIK-list normalization logic in two places (handle None, list-vs-string, isdigit, zero-pad) | gated_auto | maintainability (80) |
| R21 | `acquisition.py:_lookup_firm_slug` | 3-line wrapper around `dict.get` with one call site — adds indirection without behavior | safe_auto (could inline) | maintainability (70) |
| R22 | `queries.py:_self_test` | `ALLOWED_FORMS` test asserts count + 6 samples; a regression swapping one form (e.g., dropping 424B4, adding 424B6) passes silently as long as count stays 24 | manual (tighten test) | testing (70) |
| R23 | `__init__.py`, `__main__.py` | Docstrings use `PYTHONPATH=scripts pixi run python -m phase1_discovery ...` invocation; should add a pixi `[tasks]` entry so operators run `pixi run phase1` per project convention | gated_auto | project-standards (75) |

## Residual risks (informational, not findings)

- All `_self_test()` blocks that hit live EDGAR silently couple test outcomes to EDGAR state. Known TRA-filer CIK losing Submissions JSON, a June 2024 hit count drifting to zero, or the Repay Holdings 8-K HTML layout changing all turn green tests red without any code change. Accepted by the project's no-pytest convention.
- Concurrent Phase 1 invocations against the same `output_root` will corrupt manifest via `os.replace` last-writer-wins race. Documented in plan Scope Boundaries as a social-only constraint.
- NFS/CIFS atomic-rename not guaranteed — `output_root` on a network mount risks corruption. Standard Python limitation.
- `phrase_variants_matched` is per-accession via pipe-joined string in the manifest. Any downstream consumer that wants to query "rows matching variant X" must use substring matching; a literal `|` in a future variant name would corrupt the encoding. Reasonable now; revisit if Phase 2 read patterns prefer list-typed.

## Recommended fix order if/when addressing

1. **R8, R9** (P2 correctness) — both are silent-data-loss paths. R8: treat `rate-limited` as retriable on next invocation (don't include in done_set). R9: catch vocab-validation errors per-row inside `append_rows`, route the bad row to `parse-error` status with the original value in `doc_description` for forensics.
2. **R14** (P3 atomicity gap) — extend the atomic-write discipline to `done_marker.write_marker` for symmetry.
3. **R23** (P3 pixi task) — small ergonomic improvement; add `phase1 = { cmd = "python -m phase1_discovery", env = { PYTHONPATH = "scripts" } }` to `pixi.toml`.
4. **R10-R13, R22** — additional test coverage. Lower priority than R7 (which already landed) because each is a specific scenario rather than a missing exception class.
5. Remaining P3 findings — discretionary cleanup; not worth blocking on.
