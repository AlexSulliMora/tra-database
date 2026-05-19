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
