## methodology | comprehensive | 2026-05-19 03:05

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

---

## replicability | comprehensive | 2026-05-19 03:05

---
persona: replicability
step: S3
type: comprehensive
timestamp: 2026-05-19-03:05
---

# Review: S3 replicability

## Checklist results

- [pass] (replicability) `.gitignore` exists at the project root and includes `TRA-contracts/`: `/home/sulli/research/tra/.gitignore` exists (168 bytes). Verified `TRA-contracts/` is the final entry. All four inventory-flagged `gitignore` paths are present: `.pixi/`, `.tra_history_cache/`, `sec-data-pqt/`, `TRA-contracts/`.

- [pass] (replicability) `pixi run -- python scripts/build_tra_database.py` still runs end-to-end after cleanup. Ran from `/home/sulli/research/tra/`. Output confirms:
  ```
  tras.csv          rows=  360  cols=18  -> outputs/tra-database/tras.csv
  events.csv        rows= 1635  cols=7   -> outputs/tra-database/events.csv
  stock_by_date.csv rows= 8415  cols=5   -> outputs/tra-database/stock_by_date.csv
  ```
  Exit code 0. Row counts match the planned baseline (360 / 1635 / 8415). Also independently re-read the CSVs with polars and re-confirmed the heights match.

## Additional findings (informational)

### blocking: silent deletion of `scripts/sec_edgar/resolve_deferred_ciks.py` not in inventory.md

DEVIATIONS-coder.md (S3 section, "Paths deleted") records:

> Queued additional (1):
> - `scripts/sec_edgar/resolve_deferred_ciks.py` (20K) — defaulted to deleted `tra_deferred_review.csv`.

Grep of `coauthor/2026-05-18-git-good/inventory.md` returns zero matches for `resolve_deferred_ciks`. This file does not appear in the signed-off inventory under any recommendation (`keep`, `delete`, `move`, `gitignore`). The methodology checklist for S3 reads:

> No path was deleted that is not flagged `delete` in the signed-off `inventory.md`.

DEVIATIONS labels this a "queued additional" deletion based on the coder's judgment that the file is dead because its input CSV was deleted. That reasoning is plausible (the file likely cannot run without `tra_deferred_review.csv`), but the rule is that destructive actions on paths absent from the signed-off contract require explicit user sign-off, not a downstream-of-deletion inference. The methodology persona owns the S3 checklist item this trips; the replicability concern is that an undocumented deletion creates a reproducibility gap (no row in the contract, only a free-text DEVIATIONS note explaining what was removed and why).

**Suggested fix:** Either (i) get explicit user sign-off after the fact and amend `inventory.md` to add a row for `scripts/sec_edgar/resolve_deferred_ciks.py` with recommendation `delete` and the cascade rationale, or (ii) restore the file. The first is cheaper and matches what already happened; the second is the strict-contract path. Either way, the DEVIATIONS note alone does not substitute for the inventory contract.

### informational: `.claude/coauthor/` deletion is a documented inventory inconsistency, but the resolution is undocumented for downstream reproducibility

`inventory.md` lines 43-44:

> `.claude/`             | `keep`   | Project-local CLAUDE.md and coauthor archived-project pointers; essential project metadata
> `.claude/coauthor/`    | `delete` | Archived project metadata (...); keeps prior project context accessible

The two reason strings are mutually contradictory (the row marked `delete` says "keeps prior project context accessible"). The coder honored the `delete` column per the brief and recorded the inconsistency in DEVIATIONS. That is the right call given the brief said the recommendation column is binding, but for a future replicator reading only `inventory.md`, the contradiction remains. Verified `.claude/coauthor/` no longer exists; `.claude/` itself is preserved (contains `CLAUDE.md`, `settings.local.json`, `skills/`).

**Suggested fix:** Patch `inventory.md` after the fact to correct the reason string on line 44 (the `delete` row) so the contract reads cleanly for a re-run. Not strictly blocking because the resolution is captured in DEVIATIONS.

### informational: every other `delete` row in `inventory.md` is accounted for in DEVIATIONS

Cross-checked each `delete` recommendation in `inventory.md` against the deletion ledger in DEVIATIONS-coder.md:

- Root files: `build_tra_history.py`, `extract_tra.py`, `ipo_date_candidates.csv`, `tra_deferred_review.csv`, `tra_events_review.xlsx`, `tra_review_status.csv`, `tra_panel.parquet` — all 7 listed.
- Directories: `.claude/coauthor/`, `.pytest_cache/`, `.vscode/`, `2025_11_notes/`, `docs/`, `findings/`, `outputs/snapshots/`, `scripts/__pycache__/`, `tests/__pycache__/` — all 9 listed.
- Underscore-prefixed scripts: `_enrich_deferred_urls.py`, `_merge_decisions.py`, `_persist_phase1.py`, `_rename_unprefixed_dirs.py` — all 4 listed.
- Test modules: 8 `test_*.py` files plus `conftest.py` — DEVIATIONS lists 9, matching.

Confirmed `tests/__init__.py` was preserved (DEVIATIONS noted this explicitly).

The total of 29 documented deletions matches what's in DEVIATIONS. The only deletion not traceable to a signed-off inventory row is `scripts/sec_edgar/resolve_deferred_ciks.py` (covered above).

### informational: stale follow-up task #142 references a path now under `.claude/skills/`

Task list shows `#142. [pending] Edit tra-packet/SKILL.md to remove tra_deferred_review.csv refs`. Since `tra_deferred_review.csv` was deleted in S3, any skill that still references it would silently break for the next runner. Worth confirming `.claude/skills/tra-packet/SKILL.md` no longer references the deleted CSV before s6 commits the baseline. Outside the strict S3 checklist but relevant to "build cleanly from this commit forward."

## Commendations

- The build-script sanity check at the end of S3 (re-running `pixi run -- python scripts/build_tra_database.py` and reporting exact row counts) is exactly the right replicability discipline; it confirms no upstream dependency was severed by the cleanup, and the recorded counts let any downstream reviewer (this one included) match against ground truth in one command.
- `.gitignore` was constructed inclusively: all three large caches the inventory flagged as `gitignore` made it in, not just `TRA-contracts/`. That prevents 100+ GB of regenerable artifacts from leaking into the s6 repo.
- DEVIATIONS-coder.md is precise about which deletions happened and proactively flags the one path not in the inventory rather than burying it in an audit log. The honesty is what makes the silent-deletion finding above adjudicable at all.
