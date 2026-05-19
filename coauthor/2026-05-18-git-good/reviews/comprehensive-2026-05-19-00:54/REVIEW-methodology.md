---
persona: methodology
step: S1
type: comprehensive
timestamp: 2026-05-19-00:54
---

# Review: S1 methodology

## Checklist results

- [pass] (methodology) Each row in `inventory.md` carries one of `keep`, `delete`, `move <dest>`, `gitignore` and a one-line reason: every row in the rendered tables uses one of the four labels plus a one-line reason cell. No row uses `move` (count says 3 but none appear in the body — see informational finding below).
- [pass] (methodology) `TRA-contracts/` is flagged `gitignore` rather than `delete`: not listed as a row directly, but the "Notes on TRA-contracts/ and companion metadata" closing section and the summary recommendation count (`gitignore: 3`) name it explicitly. The closing rationale says "TRA-contracts/ is also gitignored". This satisfies the intent of the check though the absent table row is a presentation gap (see informational).
- [pass] (methodology) Companion metadata files (`contract_log.md`, `filing_notes.md`, `*_summary.qmd`) inside `TRA-contracts/<firm>/` are not flagged for deletion: the closing notes section confirms "All 321 firm directories contain at least one per-firm *_summary.qmd file. ... no metadata protection is needed; all per-firm files are safe assets that should not be deleted even if TRA-contracts/ is gitignored." Verified by spot-check: `find TRA-contracts -maxdepth 2 -name "*_summary.qmd"` returns matches in every firm directory inspected.

## Additional findings (informational)

### blocking: `2025_11_notes/` deletion breaks the XBRL pipeline that `inventory.md` keeps

Inventory row:

> `2025_11_notes/` | `delete` | Raw XBRL bulk feeds (~2 GB); exploratory data dump, no scripts reference it. User resolved 2026-05-19.

Both `build_tra_history.py` and `extract_tra.py` (both flagged `keep`) consume `2025_11_notes/` as input. `build_tra_history.py`'s docstring says "Walks every notes directory under `fin_stmt_and_notes_data/` and produces: tra_panel.parquet, tra_events_review.xlsx, ..." `extract_tra.py`'s usage line is `python extract_tra.py 2025_11_notes/`. The directory holds the XBRL Financial Statement Data Sets the scripts walk. The "no scripts reference it" reason in the inventory is false. Tests `test_panel_assembly.py`, `test_ipo_harvest.py`, `test_commit.py`, `test_review_writer.py` import from `build_tra_history` and exercise the panel logic; if the data are gone the test surface narrows or breaks.

The deeper issue: `build_tra_history.py`, `extract_tra.py`, `2025_11_notes/`, `tra_panel.parquet`, `ipo_date_candidates.csv`, `tra_deferred_review.csv`, `tra_events_review.xlsx`, `tra_review_status.csv`, and most of `tests/` form a self-contained XBRL-tag-based extraction pipeline that is *separate* from the documented `scripts/build_tra_database.py` + `TRA-contracts/` pipeline named in the scope and plan. The inventory keeps the XBRL pipeline scripts and outputs while deleting one of its inputs and saying it has no callers. The two pipelines need to be addressed as a unit:

- Option A: Keep both pipelines, in which case `2025_11_notes/` is `gitignore` (~2 GB, regenerable from EDGAR bulk feeds), not `delete`.
- Option B: Retire the XBRL pipeline (scope item 1 describes the corpus-based pipeline as the future), in which case `build_tra_history.py`, `extract_tra.py`, `tra_panel.parquet`, `ipo_date_candidates.csv`, `tra_deferred_review.csv`, `tra_events_review.xlsx`, `tra_review_status.csv`, plus the dependent test files all go too. The plan's S3 cleanup must then either delete those tests or refactor `tests/` against the new pipeline.

Suggested fix: raise this as a decision-needed item rather than silently committing to a half-step. The user note in the summary records only the `2025_11_notes/` decision, not the entailment for the pipeline that consumes it.

### blocking: `scripts/tra_download.py` deletion will break the relocated `tra-download-filings` skill

Inventory row:

> `scripts/tra_download.py` | `delete` | Superseded by tra-download-filings skill (will be relocated to skills/ in S2); remove the script copy

The header of `scripts/tra_download.py` says `"""TRA filing downloader (implements ~/.claude/skills/tra-download-filings)."""`. This is not a "copy"; it is the implementation that the skill points to. The skill SKILL.md (per S2 — relocate `~/.claude/skills/tra-download-filings` into `.claude/skills/`) presumably references this code via an absolute or relative path. Deleting `scripts/tra_download.py` while the skill expects to find its implementation will break the skill load or its invocation surface.

Suggested fix: before flagging this `delete`, either (i) confirm the skill's SKILL.md is self-contained and does not import from `scripts/tra_download.py`, or (ii) re-flag as `move scripts/tra_download.py -> .claude/skills/tra-download-filings/<file>` so the skill carries its implementation post-S2. Marking `delete` based on "skill replaces it" is shaky when the skill is the script.

### blocking: `scripts/tra_master_cik_list.py` deletion removes the only reference design for S8's seed-list step

Inventory row:

> `scripts/tra_master_cik_list.py` | `delete` | Exploratory CIK-list generation script; superseded by seed-list generation in S8 (systematic rerun with EDGAR full-text search)

Per `ca-02-plan.md` S8 ("Step s8 is a placeholder. Its decomposition ... depends on the shape the skills end up taking after s7"), S8 has no implementation yet. `scripts/tra_master_cik_list.py` is the only working EDGAR full-text-search seed-list builder in the tree (its docstring describes the partitioned-by-date strategy + the EDGAR 700-hit safe-window design that the S8 rerun would presumably reuse). Deleting it before S8 designs the replacement removes the working reference. Also flagged `delete` are `tra_master_cik_list_reaggregate.py` and `tra_refined_master.py`, which share imports with `tra_master_cik_list.py`.

Suggested fix: hold these three scripts (`tra_master_cik_list.py`, `tra_master_cik_list_reaggregate.py`, `tra_refined_master.py`) at `keep` or `move scripts/_archive/` until S8 has a frozen plan, then delete or move as a single batch. Pre-emptively deleting the reference implementation now invites rediscovery of the EDGAR pagination edge cases the existing script encodes.

### blocking: `2025_11_notes/` summary count contradicts the body decision

Summary block:

> `decision needed`: 0 (user resolved 2025_11_notes/ to delete on 2026-05-19)

The body row for `2025_11_notes/` is `delete`, but at the top the count breakdown is `keep: 13 / gitignore: 3 / delete: 11 / move: 3`. The body has eleven `delete` rows including `2025_11_notes/`, but only ten of those rows show in the inventory tables; counting the body I get: `.pixi/`, `.pytest_cache/`, `2025_11_notes/`, `docs/`, `findings/`, `notebooks/build_sec_parquet.ipynb`, plus 11 `scripts/` deletions = 17 not 11, and `tests/__pycache__/` makes 18. The `move: 3` count has no corresponding rows at all in the body. This is a tallying error; the numbers do not match a count of the table rows. The user signing off on the inventory cannot trust the counts.

Suggested fix: recount each recommendation type by direct enumeration of the table rows and reconcile the summary numbers, or generate the counts programmatically.

### blocking: no `move` rows in body despite summary count of 3

Summary block says `move: 3`. No row in the body carries `move`. The plan S1 actions list `move <new path>` as a permitted recommendation but explicitly excludes `scripts/tra_download.py` from the `move` discussion (it is flagged `delete`). The three moves cited in the summary are phantom rows; the user cannot review what is being moved.

Suggested fix: either add the three missing `move` rows with destinations or correct the summary count to `move: 0`. If the inventory author intended `move scripts/tra_download.py -> .claude/skills/tra-download-filings/`, raise to the count and add the row (and see the related blocking finding above).

### blocking: top-level files missing from inventory

The plan requires "Every top-level entry under `$PROJECT_ROOT/` appears in `inventory.md` (no silently omitted paths)" (replicability check; methodology flags these because they raise scope-completeness questions about the audit). Missing from the inventory tables:

- `.claude/CLAUDE.md` (the project-context file, 1.7 KB)
- `.claude/coauthor/` (listed only as a directory, but the row label says `keep` for the parent `.claude/coauthor/`; the actual contents `coauthor/2026-05-12-edgar-scrape.md`, `2026-05-18-tra-database.md` are not enumerated — directory-level grouping is fine, but the directory contains only those two archive files and is currently empty in fact: `ls -la .claude/coauthor/` shows zero archive .md files. The reason text claims archived metadata exists when it does not.)
- `.claude/settings.local.json` (Claude Code permission allowlist; root-level dotfile in `.claude/`)
- `.vscode/extensions.json` (only file in `.vscode/`, listed by directory in inventory; explicit row would suffice)
- `findings/tra_master_cik_list.csv/` is named in the parent row's reason text but does not have its own row.
- `TRA-contracts/` has no row at all in any table — referenced only in the closing prose. The check passes on a technicality (the gitignored count is 3 and the prose mentions it), but a row with `gitignore` + reason would be cleaner.

Suggested fix: add explicit rows for `.claude/CLAUDE.md`, `.claude/settings.local.json`, `.vscode/extensions.json`, `findings/tra_master_cik_list.csv/`, `TRA-contracts/`. Also correct the `.claude/coauthor/` rationale — the directory is empty per `ls -la /home/sulli/research/tra/.claude/coauthor/`, so the reason "Archived project metadata (2026-05-12-edgar-scrape.md, 2026-05-18-tra-database.md)" is wrong as written.

### important: `outputs/tra-database/` row is grouped, hiding S4's load-bearing outputs

Inventory row:

> `outputs/tra-database/` | `keep` | Core output directory; holds SCHEMA.md, dashboard.template.html, dashboard.html, and .csv outputs (to be converted to .parquet in S4)

The directory contains the templates that S4 reads (`dashboard.template.html`), the build artifact that S4 overwrites (`dashboard.html`, `dashboard.qmd`, `dashboard_files/`), three csvs that S4 will replace with parquet (`tras.csv`, `events.csv`, `stock_by_date.csv`), and `SCHEMA.md`. Some of these (csvs) should be `delete` after S4 lands; `dashboard.html` and `dashboard_files/` may be `delete-and-regenerate`. The grouped `keep` row does not raise these decisions for S3's executor.

Suggested fix: expand `outputs/tra-database/` into one row per file with the post-S4 fate (csvs → `delete after S4`, parquet files → `keep`, template → `keep`, html → keep but regenerated, etc.). The user signing off needs to see what survives S4.

### important: `outputs/snapshots/` row is grouped, hiding three xlsx files of unknown freshness

Inventory row:

> `outputs/snapshots/` | `keep` | Archived analysis snapshots (TRA_liabilities, tra_comparison); research artifacts; keep for traceability

Directory contains three xlsx files (`TRA_liabilities_3q25_check.xlsx`, `tra_comparison.xlsx`, `tra_liabilities_2026-03-31.xlsx`). The recommendation is plausible but the inventory does not state what produced these files or whether they are inputs to anything kept. A bald `keep for traceability` row should at least name the producer (or "unknown producer; manual artifact").

Suggested fix: either (i) name the producer in the reason, or (ii) flag `decision needed — unknown producer`.

### important: tests/__pycache__/ is delete but tests/ row is implicit `keep`

The inventory lists `tests/conftest.py`, `tests/test_*.py`, and `tests/__pycache__/` as rows but never gives a parent row for `tests/`. The summary "decision needed: 0" implies all of `tests/` is keep; the closing rationale says "all tests" keep. But `test_review_writer.py`, `test_commit.py`, `test_ipo_harvest.py`, `test_panel_assembly.py`, `test_panel_slice.py`, `test_transfers.py`, `test_terminations.py`, `test_cli.py` are the *XBRL-pipeline* tests (they import from `build_tra_history`/`extract_tra`). If the XBRL pipeline retires (see blocking finding on `2025_11_notes/`), most of `tests/` should retire too. The inventory's blanket `keep` for the tests is inconsistent with deletion of `2025_11_notes/` and silent on the new pipeline's test coverage.

Suggested fix: tie the `tests/` recommendations to the XBRL-pipeline decision. Either keep both or retire both. Note that the new `scripts/build_tra_database.py` has no tests in the inventory; that is its own gap but outside S1's scope.

### important: `scripts/_*.py` rationale assumes "underscore prefix means one-shot WIP"

Each of `_enrich_deferred_urls.py`, `_merge_decisions.py`, `_persist_phase1.py`, `_rename_unprefixed_dirs.py` is flagged `delete` with the rationale "One-shot WIP script (underscore-prefixed); ... exploratory artifact". `_enrich_deferred_urls.py` is grep-callable from `tests/test_review_writer.py` (per the earlier grep output it appears in `scripts/sec_edgar/resolve_deferred_ciks.py` references too). Quick spot-check needed before commit.

Suggested fix: grep each underscore-prefixed script for callers (`grep -r "_enrich_deferred_urls\|_merge_decisions\|_persist_phase1\|_rename_unprefixed_dirs" --include="*.py"`). If any have live callers, hold them.

### minor: build_sec_parquet.ipynb deletion may sever the only documentation of `sec-data-pqt/` build

Inventory row:

> `notebooks/build_sec_parquet.ipynb` | `delete` | One-off exploration notebook; not part of the reproducible pipeline; dead artifact from prior iteration

The notebook name suggests it built `sec-data-pqt/` (the 18 GB parquet cache the inventory keeps gitignored). If the parquet cache ever needs rebuilding, the notebook is the only reference. The inventory keeps the output but deletes the recipe.

Suggested fix: either move the notebook to `scripts/_archive/` or document the build steps in `outputs/tra-database/SCHEMA.md` (or wherever) before deleting.

### minor: `docs/` and `findings/` empty-directory deletion is fine but `.gitignore` is silent on rebuild

Both directories are flagged `delete` with the rationale "empty directory tree". Fine. But the future repo has no `.gitignore` entries to prevent these from re-accumulating; that is S3's job, not S1's, and the inventory is correct to stop there. Just noting that the S3 reviewer should check that `.gitignore` covers regenerable empty trees if any new scripts produce them.

## Commendations

- The closing "Notes on TRA-contracts/ and companion metadata" section addresses the methodology-critical companion-metadata risk head-on and verifies it empirically by checking what files exist in each firm directory.
- The grouped treatment of `TRA-contracts/<firm>/` at the parent level (rather than enumerating 321 firms) follows the plan's instruction and keeps the inventory readable.
- The split of `scripts/` into "Core pipeline" and "Dead/exploratory" sub-tables is a clean presentation that makes the deletion intent legible.
- The `gitignore` decisions on `.tra_history_cache/` (87 GB) and `sec-data-pqt/` (18 GB) correctly trade repo size against developer convenience and quote the cache sizes.
