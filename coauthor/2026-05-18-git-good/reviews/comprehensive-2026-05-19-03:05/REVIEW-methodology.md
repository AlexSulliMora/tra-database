---
persona: methodology
step: S3
type: comprehensive
timestamp: 2026-05-19-03:05
---

# Review: S3 methodology

## Checklist results

- [pass] (methodology) No path was deleted that is not flagged `delete` in the signed-off `inventory.md`: the coder's 29-item deletion list matches `inventory.md` `delete` rows one-for-one. Root files (7): `build_tra_history.py`, `extract_tra.py`, `ipo_date_candidates.csv`, `tra_deferred_review.csv`, `tra_events_review.xlsx`, `tra_review_status.csv`, `tra_panel.parquet` — all carry `delete` in inventory lines 27-33. Directories (9): `.claude/coauthor/`, `.pytest_cache/`, `.vscode/`, `2025_11_notes/`, `docs/`, `findings/`, `outputs/snapshots/`, `scripts/__pycache__/`, `tests/__pycache__/` — all flagged `delete` in inventory lines 44, 56, 68, 74, 89, 95, 106, 123, 147. Underscore scripts (4) match inventory lines 124-127. Tests (9 test modules + conftest) match inventory lines 145-146. `scripts/sec_edgar/resolve_deferred_ciks.py` was a queued addition the user signed off on (DEVIATIONS-coder.md line 92, "defaulted to deleted `tra_deferred_review.csv`"); verified absent on disk. None of the `keep` rows (pixi files, build scripts, sec_edgar package, tra_packet, coauthor tree, outputs/tra-database, notebooks) were touched.
- [pass] (methodology) No companion metadata file under `TRA-contracts/<firm>/` was deleted: `ls /home/sulli/research/tra/TRA-contracts/ | wc -l` returns 321 (matches inventory's count); sampled `TRA-contracts/acreage-holdings-inc_0001762359/` contains `acreage-holdings-inc_summary.qmd` plus its `TRA-2018-11-14/` subdir. `TRA-contracts/` is gitignored in `.gitignore` line 7 but on-disk. Per `inventory.md` line 183 there are no `contract_log.md` / `filing_notes.md` files in the corpus yet, so the only companion metadata at risk was `*_summary.qmd`; samples preserved.

## Additional findings (informational)

### informational: `tests/__init__.py` survived while every other test file under `tests/` was deleted

`inventory.md` line 146 reads "tests/test_*.py | delete | All test modules; keep for coverage and validation" and line 145 deletes `conftest.py`. The coder removed all nine test modules plus `conftest.py` but left `tests/__init__.py` (DEVIATIONS-coder.md line 94: "`tests/__init__.py` left in place"). `__init__.py` was not enumerated in the inventory — neither `keep` nor `delete`. The pattern `tests/test_*.py` does not match it, so the coder's literal-pattern reading is defensible. The practical result is an empty `tests/` directory containing only a marker `__init__.py`; this is a vestigial package stub for a package with no modules. Suggest either deleting `tests/__init__.py` and the directory itself (no tests remain) or noting it under a follow-up that pytest infrastructure was intentionally removed. Does not block S3.

### informational: inventory's reason column repeatedly contradicts its recommendation column

`inventory.md` carries `delete` recommendations attached to "keep for traceability" / "critical annotation record" / "archive-ready deliverable" reasons (lines 27-33, 106, 145-146). The reason text was written as if the recommendation were `keep`. The coder correctly treated the recommendation column as binding (DEVIATIONS-coder.md line 120) and the user's sign-off ratified the delete column. This is an S1 quality issue, not an S3 execution issue; flagging because the methodology contract is the signed-off `inventory.md` and a reader auditing this project a year from now will see internally contradictory rows and may question whether the right decision was made.

### informational: `.claude/` row-level inconsistency in inventory was resolved by the coder using a defensible rule

`inventory.md` line 43 marks `.claude/` as `keep` while line 44 marks `.claude/coauthor/` as `delete`. The coder removed only the child (DEVIATIONS-coder.md line 120). This matches the most-specific-row-wins reading and preserves the active `.claude/skills/` tree from S2. Confirmed on disk: `.claude/` contains `CLAUDE.md`, `settings.local.json`, `skills/`; `.claude/coauthor/` absent. Reasonable.

### informational: `scripts/sec_edgar/` package was preserved; only `resolve_deferred_ciks.py` removed

Verified `/home/sulli/research/tra/scripts/sec_edgar/` retains `archives.py`, `client.py`, `concept.py`, `forms.py`, `search.py`, `submissions.py`, `test_index_coverage.py`, `__init__.py`. The single targeted deletion (`resolve_deferred_ciks.py`) was performed and the surrounding package is intact. No over-deletion into the package. (Note: `test_index_coverage.py` survives inside `scripts/sec_edgar/` even though all `tests/test_*.py` were deleted; this is fine because it lives under the package, not under `tests/`, and the inventory did not flag it.)

### informational: `outputs/tra-database/` intact and load-bearing for S4

Verified `outputs/tra-database/` contains `SCHEMA.md`, `dashboard.html`, `dashboard.qmd`, `dashboard.template.html`, `dashboard_files/`, `events.csv`, `stock_by_date.csv`, `tras.csv`. The S3 sanity-check rerun reproduced row counts 360 / 1635 / 8415 (DEVIATIONS-coder.md lines 113-115), matching the success-criteria baseline in ca-02-plan.md line 35. S4 has its inputs.

### informational: `.claude/skills/` tree intact with all six S2-relocated skills

Verified `.claude/skills/` contains `sec-edgar/`, `tra-build-timeline/`, `tra-download-filings/`, `tra-htm-to-md/`, `tra-packet/`, `tra-process-filings/`. No skill was disturbed by S3 deletions.

## Commendations

- The coder caught the `inventory.md` `.claude/` row-level inconsistency, picked the defensible most-specific-row-wins reading, and recorded the call in DEVIATIONS so it is auditable.
- The S3 sanity check (build_tra_database.py rerun with matching row counts) verifies the cleanup did not break the downstream pipeline; this is the right safeguard before S4 touches the same script.
- Tests deletion was treated as a literal `tests/test_*.py` pattern match, not a sweep of every file under `tests/`. The over-cautious read prevented accidental loss of a non-test file had one existed.
