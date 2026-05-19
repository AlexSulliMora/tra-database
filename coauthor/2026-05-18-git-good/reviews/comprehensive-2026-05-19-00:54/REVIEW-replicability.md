---
persona: replicability
step: S1
type: comprehensive
timestamp: 2026-05-19-00:54
---

# Review: S1 replicability

## Checklist results

- [fail] (replicability) Every top-level entry under `/home/sulli/research/tra/` appears in `inventory.md`. `TRA-contracts/` has no row in any inventory table; it appears only in narrative text ("Notes on TRA-contracts/ and companion metadata" and the rationale paragraph). This is the most load-bearing path in the project (321 firm directories, gitignored per the plan's success criteria) and the omission means a reader cannot read off the recommendation from the structured inventory. Verified by `grep -n "TRA-contracts" inventory.md` returning only narrative mentions, no table row.
- [pass] (replicability) "Decision needed" rows are flagged explicitly at the top of the file. The Summary section lists `decision needed: 0 (user resolved 2025_11_notes/ to delete on 2026-05-19)`, and the rationale section restates the resolved item. Acceptable — the prior decision-needed item was resolved and recorded.

## Additional findings (informational)

### blocking: `TRA-contracts/` missing from the structured inventory

Quoted from inventory.md, line 11:

> **Paths inspected:** 28 top-level entries + nested structure across coauthor/, scripts/, outputs/, TRA-contracts/.

The summary asserts `TRA-contracts/` is gitignored (line 15) but no table row in the body assigns it a recommendation with a reason. Cross-check: `ls -la /home/sulli/research/tra/` lists `TRA-contracts` as a directory with 323 subdirectories (321 firms + `.` + `..`). The plan's S1 implementation step 2 explicitly says "Group the `TRA-contracts/<firm>/` per-firm subdirectories at the parent level rather than listing all 321 firms individually; flag exceptions". The inventory should have a dedicated `### TRA-contracts/` section with a parent-level row plus any per-firm exceptions.

Fix: add a `### TRA-contracts/` section with a row `| TRA-contracts/ | gitignore | 321 firm subdirectories holding the per-firm filing corpus and *_summary.qmd companions; regenerable from the pipeline; on disk for development, excluded from the repo |`. If any firm dir is missing a `*_summary.qmd` (per the plan's "flag exceptions"), enumerate those exceptions.

### blocking: summary counts are inconsistent with the actual table contents

Quoted from inventory.md, lines 13–18:

> **Recommendation counts:**
> - `keep`: 13
> - `gitignore`: 3 (TRA-contracts/, .tra_history_cache/, sec-data-pqt/)
> - `delete`: 11
> - `move`: 3

Actual counts from the file: `\`keep\`` appears 25 times, `\`gitignore\`` 3 times, `\`delete\`` 19 times, `\`move\`` 1 time (and only in the summary, never as a row). There are zero `move` recommendations in any table. The summary line `move: 3` is unverified; it does not correspond to anything in the body. The `keep`/`delete` counts are also wrong. A user signing off on this for the destructive S3 step needs the summary to be a faithful tally; otherwise they may approve based on a miscount.

Fix: regenerate the summary counts from the actual rows after the `TRA-contracts/` row is added. State the count derivation explicitly so a future-you can re-verify by `grep -c "\`<rec>\`"`.

### blocking: `.gitignore` does not exist at the project root, but inventory does not mention this

Verified: `test -f /home/sulli/research/tra/.gitignore` returns missing. The inventory does not list `.gitignore` as either present, absent, or to-be-created. Step S3 must create it (per plan S3 action 3), so S1 should at minimum record that no `.gitignore` exists today — otherwise a future-you reading only `inventory.md` cannot tell whether the file was overlooked or intentionally absent.

Fix: add a row in the root-level files table noting `.gitignore` is currently absent and will be created in S3, listing what it will contain (`TRA-contracts/`, `.tra_history_cache/`, `sec-data-pqt/`, `.pixi/`, `.pytest_cache/`, `__pycache__/`).

### important: `.claude/` contents under-enumerated

The `.claude/` section gives one row for `.claude/` and one for `.claude/coauthor/`. Actual contents (from `ls -la /home/sulli/research/tra/.claude/`):

- `CLAUDE.md` (project-context file; load-bearing per the parent CLAUDE.md "Project layout" section)
- `coauthor/` (archived-project pointers)
- `settings.local.json` (per-project Claude Code settings; may contain permissions or local config)

Neither `CLAUDE.md` nor `settings.local.json` is given a row. `settings.local.json` is the kind of file that can carry sensitive permissions — it warrants an explicit `keep` (or `gitignore` if it carries machine-specific paths) with a one-line reason. A future-you should not need to `ls .claude/` to discover these files exist.

Fix: split the `.claude/` row into one row per file and one for the `coauthor/` subdir. Make an explicit call on `settings.local.json` (keep vs. gitignore) based on contents.

### important: `notebooks/` directory itself has no row

Quoted from inventory.md, lines 99–102:

> ### `notebooks/`
>
> | Path | Recommendation | Reason |
> |------|---|---|
> | `notebooks/build_sec_parquet.ipynb` | `delete` | One-off exploration notebook; not part of the reproducible pipeline; dead artifact from prior iteration |

Only the one file inside `notebooks/` gets a row. The directory itself is not assigned a recommendation. If the only file inside is deleted, the directory becomes empty and should also be `delete` (consistent with how `docs/` and `findings/` were treated as empty-dir deletes). Otherwise the cleanup leaves an empty `notebooks/` that is itself a "cleanup artifact from prior work".

Fix: add a row for `notebooks/` (delete after removing the notebook, or explicitly keep if more notebooks will land there).

### important: `tests/` enumeration is non-reproducible

The `tests/` section lists `tests/conftest.py`, `tests/test_*.py` (glob, not enumerated), and `tests/__pycache__/`. `ls /home/sulli/research/tra/tests/` shows nine concrete test modules plus `__init__.py` and `conftest.py`. The glob `tests/test_*.py | keep` is a shortcut, not a row-per-path. The plan's success criterion says "Every folder, file, and subfolder under the project root appears in `inventory.md`". A future-you cannot tell from the inventory which specific test files exist; they have to `ls` the directory.

This is a judgment call — exhaustive per-file enumeration of every test file is heavy, and grouping with a glob is defensible. But the plan's S1 action 2 says "Group the `TRA-contracts/<firm>/` per-firm subdirectories at the parent level rather than listing all 321 firms individually" as the named exception. No similar carve-out was authorized for `tests/`.

Fix: either enumerate each test module on its own row, or add a one-liner in the `tests/` section noting that all test_*.py modules are grouped as a single `keep` with the count (e.g., "9 test_*.py modules, all keep") and list which files are covered. Also missing: `tests/__init__.py` is not mentioned at all.

### important: `outputs/tra-database/` contents not enumerated despite being load-bearing

Quoted from inventory.md, line 108:

> | `outputs/tra-database/` | `keep` | Core output directory; holds SCHEMA.md, dashboard.template.html, dashboard.html, and .csv outputs (to be converted to .parquet in S4) |

The directory is rolled up to one row, but the plan's success criteria call out specific file names (`tras.parquet`, `events.parquet`, `stock_by_date.parquet`, `dashboard.html`, `SCHEMA.md`, `dashboard.template.html`, `last_refresh.json` to come). A future-you should be able to read off which current files exist and which are S4/S7 outputs. The current row says "csv outputs" without naming them, which conflates what is on disk now with what's coming.

Fix: expand the row into a sub-table listing each file currently present with its recommendation, and a separate note for files produced by later steps (S4 parquets, S7 `last_refresh.json`).

### minor: `docs/` and `findings/` empty-directory checks are not falsifiable from the inventory

The inventory says `docs/` is "Empty directory tree (no files under brainstorms/, claim-verification/, code-review/, plans/)" and `findings/` is "Empty directory tree". Confirmed by `ls -la` — `docs/` has four empty subdirs, `findings/` has `tra_master_cik_list.csv/` (which is curiously a directory, not a file — the trailing `/` in the inventory's reason is not a typo). A future-you might want the inventory to record the existence of the four empty subdirs under `docs/` so the delete is auditable.

Fix: in the reason column, list the subdir names so the delete can be verified after the fact (`docs/brainstorms/, docs/claim-verification/, docs/code-review/, docs/plans/ — all empty`).

### minor: hidden dotfile coverage of `.gitignore` aside

Other than `.gitignore` (covered above), I cross-checked `ls -la` against the inventory: `.claude/`, `.pixi/`, `.pytest_cache/`, `.tra_history_cache/`, `.vscode/` all appear. No hidden top-level files (no `.envrc`, `.python-version`, `.git/`, `.dockerignore`, etc.) on disk, so no further omissions here.

## Commendations

- The "Notes on TRA-contracts/ and companion metadata" section explicitly verifies whether the companion-metadata protection rule applies, and records that no `contract_log.md` / `filing_notes.md` exist yet. Good discipline against the standing instruction never to sweep companion metadata.
- The rationale for each `delete` recommendation in `scripts/` names the file's status (underscore-prefixed one-shot, exploratory, superseded by skill, etc.). A future-you can re-verify each delete from the file name alone.
- The 87 GB / 18 GB size annotations on the gitignored caches make the rationale concrete; a reader knows why those paths are gitignored rather than committed.
- The `.tra_history_cache/` and `sec-data-pqt/` distinction (cache vs. cache) and the inclusion of both in `.gitignore` planning is correct.
