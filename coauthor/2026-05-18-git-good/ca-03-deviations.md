# DEVIATIONS (aggregated)

Regenerated at 2026-05-19-03:23.

## coder

---
worker: coder
project_id: 2026-05-18-git-good
---

# DEVIATIONS — coder

## 2026-05-19 — S2 (Skill relocation): halted before move

**Status:** Halted. No files moved. Awaiting user decision on destination path.

**Plan said:** "`mkdir -p $PROJECT_ROOT/skills/` and move each source directory into it: `mv ~/.claude/skills/tra-* ~/.claude/skills/sec-edgar $PROJECT_ROOT/skills/`." Step 4 of the plan instructed: "If the global skill mechanism does not pick up project-local skills automatically, document that in DEVIATIONS-coder.md and stop; the user resolves before s3."

**What I found:** Per the official Claude Code skills documentation (`https://code.claude.com/docs/en/skills`), project-level skills are auto-loaded only from `.claude/skills/<skill-name>/SKILL.md` under the project root (and from parent directories up to the repo root). The documented load locations are:

| Scope | Path |
| --- | --- |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` |
| Project | `.claude/skills/<skill-name>/SKILL.md` |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` |
| Enterprise | Managed-settings path |

An arbitrary `skills/` directory at the project root (the plan's destination) is not on the auto-load list. Skills moved there would stop being discovered by Claude Code. That fails S2 success criterion 4 ("The relocated skills load from the project") and would block S6's README skill-catalog claim and S7's `tra-refresh` workflow.

**Source consulted:** WebFetch on `https://code.claude.com/docs/en/skills`, section "Where skills live" and "Automatic discovery from parent and nested directories."

**Why I halted instead of substituting:** The plan named `$PROJECT_ROOT/skills/` explicitly; the success criteria for S2 also name `skills/`. Silently rerouting to `.claude/skills/` would diverge from the frozen plan without user sign-off. The plan's own halt-and-flag instruction in S2 step 4 is the right path.

**Recommended resolution (for user):** Change the destination to `$PROJECT_ROOT/.claude/skills/` so the relocated skills auto-load as project skills. This requires an amendment to `ca-02-plan.md` (success criteria reference `skills/`; subsequent steps S3, S5, S7 also reference `skills/` and would need the same edit). Alternatively, accept that the skills will need to be invoked via a non-standard mechanism (e.g., kept in `skills/` but pointed at by an `--add-dir` invocation with a `.claude/skills/` subdirectory inside it, or referenced manually). The cleanest fix is `.claude/skills/`.

**No move performed.** All six source directories remain in place at `~/.claude/skills/`:

- `~/.claude/skills/tra-download-filings/`
- `~/.claude/skills/tra-process-filings/`
- `~/.claude/skills/tra-build-timeline/`
- `~/.claude/skills/tra-htm-to-md/`
- `~/.claude/skills/tra-packet/`
- `~/.claude/skills/sec-edgar/`

**Awaiting:** User decision on destination path before s3.

**Resolution (2026-05-19):** Plan amended; destination changed from `$PROJECT_ROOT/skills/` to `$PROJECT_ROOT/.claude/skills/` (Claude Code's documented project-skill auto-load path). Ran:

```
mkdir -p /home/sulli/research/tra/.claude/skills/
mv ~/.claude/skills/tra-download-filings ~/.claude/skills/tra-process-filings ~/.claude/skills/tra-build-timeline ~/.claude/skills/tra-htm-to-md ~/.claude/skills/tra-packet ~/.claude/skills/sec-edgar /home/sulli/research/tra/.claude/skills/
```

All six skill directories now live at `/home/sulli/research/tra/.claude/skills/` and each contains a `SKILL.md`. None remain at `~/.claude/skills/`. The system-reminder skill list at re-dispatch time confirmed Claude Code auto-loaded all six from the new project location.

**In-project references updated:** one — `scripts/tra_download.py` line 1 docstring changed from `~/.claude/skills/tra-download-filings` to `.claude/skills/tra-download-filings`. The other grep hits were historical (this DEVIATIONS file's own prior text, `ca-01-scope.md`, `ca-02-plan.md`, prior review files, and the `2026-05-12-edgar-scrape/transcript.html`); those record what was true at the time and should not be rewritten.

**Informational findings for s3** (intra-skill path references inside the relocated `SKILL.md` files that may need follow-up):

- `tra-htm-to-md/SKILL.md` references its bundled helper scripts via absolute paths `~/.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` and `~/.claude/skills/tra-htm-to-md/scripts/clean_and_link.py` (lines 59, 122, 153, 157). After the move, these paths no longer resolve; the skill is broken internally until s3 (or a follow-up) rewrites them to the new location (e.g. `.claude/skills/tra-htm-to-md/scripts/...`).
- `tra-download-filings/SKILL.md` line 218 mentions `scripts/tra_download.py` as the implementation, consistent with the methodology reviewer's S1 finding that the script and the skill are paired.
- `sec-edgar/SKILL.md`, `tra-build-timeline/SKILL.md`, `tra-process-filings/SKILL.md`, and `tra-packet/SKILL.md` reference the project's `scripts/sec_edgar/` package via project-relative paths (e.g. `scripts/sec_edgar/`, `PYTHONPATH=scripts`). Those references continue to work as long as the skills are invoked from the project root, which is the normal case.

## 2026-05-19 — S3 (Execute cleanup): completed

**Status:** Done. All inventory.md `delete` paths removed; `.gitignore` created; database build verified.

**Paths deleted (29 total):**

Root files (7):
- `build_tra_history.py` (116K)
- `extract_tra.py` (44K)
- `ipo_date_candidates.csv` (24K)
- `tra_deferred_review.csv` (36K)
- `tra_events_review.xlsx` (464K)
- `tra_review_status.csv` (24K)
- `tra_panel.parquet` (100K)

Directories (9):
- `.claude/coauthor/` (4K)
- `.pytest_cache/` (36K)
- `.vscode/` (8K)
- `2025_11_notes/` (2.0G)
- `docs/` (20K)
- `findings/` (8K)
- `outputs/snapshots/` (76K)
- `scripts/__pycache__/` (24K)
- `tests/__pycache__/` (316K)

Underscore-prefixed scripts (4):
- `scripts/_enrich_deferred_urls.py` (12K)
- `scripts/_merge_decisions.py` (4K)
- `scripts/_persist_phase1.py` (12K)
- `scripts/_rename_unprefixed_dirs.py` (4K)

Queued additional (1):
- `scripts/sec_edgar/resolve_deferred_ciks.py` (20K) — defaulted to deleted `tra_deferred_review.csv`.

Tests (9): `tests/conftest.py`, `tests/test_cli.py`, `tests/test_commit.py`, `tests/test_ipo_harvest.py`, `tests/test_panel_assembly.py`, `tests/test_panel_slice.py`, `tests/test_review_writer.py`, `tests/test_terminations.py`, `tests/test_transfers.py`. `tests/__init__.py` left in place.

Total reclaimed: approximately 2.0 GB (dominated by `2025_11_notes/`).

**`.gitignore` created** at `/home/sulli/research/tra/.gitignore` with:

```
# Local caches (regenerable; out of repo)
.pixi/
.tra_history_cache/
sec-data-pqt/

# TRA corpus (321 firm directories; regenerable from EDGAR pipeline)
TRA-contracts/
```

**Database build sanity check:** `pixi run -- python scripts/build_tra_database.py` succeeded. Output:

```
tras.csv          rows=  360  cols=18  -> outputs/tra-database/tras.csv
events.csv        rows= 1635  cols=7  -> outputs/tra-database/events.csv
stock_by_date.csv rows= 8415  cols=5  -> outputs/tra-database/stock_by_date.csv
```

Row counts (360 / 1635 / 8415) match the pre-cleanup baseline. Build unaffected by deletions.

**Inventory inconsistency noted:** `inventory.md` line 43 marks `.claude/` as `keep` while line 44 marks `.claude/coauthor/` as `delete`. The recommendation column was treated as the binding decision (per the brief); `.claude/coauthor/` was removed and `.claude/` itself (which still contains `skills/` and other live state) was preserved.

**No unexpected state encountered.** All deletion targets existed at the listed paths; no permission issues; no broken references that the build script tripped over.


## 2026-05-19 — S4 (Parquet conversion): two judgment calls

**Status:** Complete. Two discretionary choices recorded below.

**1. `outputs/tra-database/dashboard.qmd` deleted as stale alternate render path.**

The plan flagged that `dashboard.qmd` (Quarto dashboard format, reads csvs, renders to `dashboard.html` via `quarto render`) and `dashboard.template.html` + `scripts/build_dashboard.py` were two coexisting paths to the same output filename. I deleted the qmd path rather than updating it to read parquet. Reasoning: (a) the shipped `dashboard.html` is produced by `build_dashboard.py`, which is what `SCHEMA.md` documents as the build path; (b) the qmd path is not invoked by any script and requires a Quarto install at render time; (c) leaving both in the repo (especially after both target the same `dashboard.html`) invites silent overwrites in the future. I also removed the `dashboard_files/` sidecar (4.3 MB of Quarto-generated libs) since it was created by the qmd render and nothing else references it (`grep -c dashboard_files` against `dashboard.html`, `dashboard.template.html`, and `build_dashboard.py` returned 0 for all three).

**2. `stock_by_date.date` cast to ISO string at build time.**

After switching to parquet, the first `build_dashboard.py` run failed with `TypeError: Object of type date is not JSON serializable`. Root cause: `build_stock_by_date()` constructs the `date` column with `pl.date_range(...)`, which yields `pl.Date`. With csv, polars round-tripped that as a string; with parquet, the dtype is preserved, and `to_dicts()` then yields `datetime.date` objects that `json.dumps` rejects. Two viable fixes: (a) cast to ISO string at build time, (b) convert in `build_dashboard.py` before `to_dicts()`. I chose (a) and added `pl.col("date").dt.strftime("%Y-%m-%d")` to `build_stock_by_date()`. Reasoning: the SCHEMA.md "Dates as ISO strings" convention applies to all four date columns across the three files; doing the cast in the build script keeps the on-disk schema consistent with `creation_date`, `termination_date`, and `events.date` (all stored as `pl.String`). SCHEMA.md's Conventions section was updated to make the build-time cast explicit.

**Row counts and file integrity:**

- `tras.parquet`: 360 rows, 18 cols, all columns `pl.String`. `cik` and `ciks` retain leading zeros.
- `events.parquet`: 1635 rows, 7 cols, all `pl.String`.
- `stock_by_date.parquet`: 8415 rows, 5 cols. `date`, `dimension`, `group_value` are `pl.String`; `count` is `pl.UInt32`; `rank` is `pl.Int64`.
- `dashboard.html`: 1,804,164 chars (prior csv build was 1,804,180 chars — 16-byte delta is identical JSON content). All three placeholder tokens (`__TRAS_JSON__`, `__EVENTS_JSON__`, `__STOCK_JSON__`) substituted.
