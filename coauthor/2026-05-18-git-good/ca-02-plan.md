---
project_id: 2026-05-18-git-good
status: frozen
owners: [analyst, coder, writer, researcher]
created: 2026-05-19
---

# Plan

## Goal

Take the working but messy TRA pipeline through a cleanup-then-rerun cycle that ends with a self-contained private GitHub repository: skills relocated under the project tree, dead files removed, csv outputs replaced with parquet, a README in place, a new EDGAR refresh skill that updates the database incrementally, and a second end-to-end pass run on a fresh CIK seed list using the improved skills.

## Decomposition

| Step id | Worker | Goal | Inputs | Output | Parallel-with |
|----------|--------|------|--------|--------|---------------|
| s1 | analyst | Inventory every folder, file, and subfolder under the project root with a keep / delete / move / gitignore recommendation and a one-line reason | project root tree, ca-01-scope.md | inventory.md (plus DEVIATIONS-analyst.md if deviated) | s2 |
| s2 | coder | Relocate the TRA-family skills and `sec-edgar` from `~/.claude/skills/` into `.claude/skills/` under the project root; update any in-project references | ~/.claude/skills/tra-*, ~/.claude/skills/sec-edgar | .claude/skills/tra-*, .claude/skills/sec-edgar (plus DEVIATIONS-coder.md if deviated) | s1 |
| s3 | coder | Execute the user-signed-off recommendations from `inventory.md`: delete, move, gitignore | inventory.md (with user sign-off), s2 output | cleaned project tree, `.gitignore` populated (plus DEVIATIONS-coder.md if deviated) | none |
| s4 | coder | Convert the database build and dashboard build to read and write parquet instead of csv; verify the dashboard rebuilds and renders | scripts/build_tra_database.py, scripts/build_dashboard.py, outputs/tra-database/ | scripts/build_tra_database.py and build_dashboard.py emitting parquet; outputs/tra-database/{tras,events,stock_by_date}.parquet; dashboard.html (plus DEVIATIONS-coder.md if deviated) | none |
| s5 | writer | Draft `README.md` at the project root covering workflow steps and commands, pixi setup, output locations, a schema pointer, and a skill catalog | s3 cleaned tree, s4 parquet outputs, outputs/tra-database/SCHEMA.md | README.md (plus DEVIATIONS-writer.md if deviated) | none |
| s6 | coder | Initialize a git repo, commit the cleaned baseline state, create a private GitHub repo under the user's account, push | s3, s4, s5 outputs, .gitignore | initial commit on `main`, private GitHub remote with `main` pushed (plus DEVIATIONS-coder.md if deviated) | none |
| s7 | coder | Build the new `tra-refresh` skill: query EDGAR for filings posted since the last cutoff per CIK, run the downstream pipeline, update the parquet outputs in place, write `last_refresh.json` | s6 baseline repo, .claude/skills/sec-edgar, .claude/skills/tra-process-filings, .claude/skills/tra-build-timeline, .claude/skills/tra-htm-to-md, outputs/tra-database/ | .claude/skills/tra-refresh/ with SKILL.md and helper code; baseline `last_refresh.json` written (plus DEVIATIONS-coder.md if deviated) | none |
| s8 | TBD | Systematic rerun: re-collect CIK seed list from EDGAR full-text search, run the improved skills end-to-end, rebuild the database, regenerate the dashboard, write initial refresh metadata; skill edits per scope item 6 are interleaved | s7 repo + skills | regenerated corpus, rebuilt parquet outputs, dashboard.html, last_refresh.json (plus DEVIATIONS-*.md per worker) | none |

Workers write DEVIATIONS files only when a step diverged from `ca-02-plan.md` or required a discretionary judgment call. Routine "what I did" content is captured in the per-worker audit log under `<slug>/.audit/<worker>.md`. A second step for the same worker appends a new dated section to the same `DEVIATIONS-<worker>.md` rather than overwriting.

**Step s8 is a placeholder.** Its decomposition (single PM-driven step versus split into seed-pull + pipeline run versus per-skill steps) depends on the shape the skills end up taking after s7. Refine s8 after s7 freezes by amending this plan (set `status: draft`, edit, refreeze).

## Success criteria

- Every folder, file, and subfolder under the project root appears in `inventory.md` with one of {keep, delete, move, gitignore} and a one-line reason.
- All TRA-family skills and `sec-edgar` load from `.claude/skills/` under the project (not from `~/.claude/skills/`) after s2 + s3.
- `outputs/tra-database/{tras,events,stock_by_date}.parquet` exist and round-trip the row counts from the prior csv outputs (360 / 1635 / 8415). The dashboard rebuild from parquet inputs renders.
- `README.md` covers workflow, commands, pixi setup, output locations, schema pointer, and skill catalog; every documented command runs without error from a fresh checkout.
- Private GitHub repo exists; `TRA-contracts/` is in `.gitignore`; the cleaned baseline is pushed to `main`.
- `tra-refresh` skill loads and runs in a dry-run mode that reports what it would do without modifying the parquets. A live run writes a valid `last_refresh.json`.
- Step s8 produces a regenerated corpus from a fresh CIK seed list and a rebuilt database / dashboard from it.

## Context pointers

- $PROJECT_ROOT/coauthor/2026-05-18-git-good/ca-01-scope.md
- $PROJECT_ROOT/scripts/build_tra_database.py
- $PROJECT_ROOT/scripts/build_dashboard.py
- $PROJECT_ROOT/outputs/tra-database/SCHEMA.md
- $PROJECT_ROOT/outputs/tra-database/dashboard.template.html
- $PROJECT_ROOT/TRA-contracts/ (321 firm subdirectories; gitignored after s3)
- ~/.claude/skills/tra-download-filings, tra-process-filings, tra-build-timeline, tra-htm-to-md, tra-packet, sec-edgar (source paths for s2)

## Implementation

### S1: Inventory and keep/delete recommendations

**Actions:**

1. Walk the project root `$PROJECT_ROOT/` to depth that distinguishes per-firm corpus entries from the rest of the tree. Use `find . -maxdepth 4 -type d` and `find . -maxdepth 3 -type f` to enumerate candidates, then expand deeper where useful (e.g., into `coauthor/`, `outputs/`, `scripts/`).
2. For every path that surfaces, decide a recommendation: `keep`, `delete`, `move <new path>`, `gitignore` (keep on disk but exclude from the repo). Group the `TRA-contracts/<firm>/` per-firm subdirectories at the parent level rather than listing all 321 firms individually; flag exceptions (e.g., a firm dir with no `*_summary.qmd`).
3. Write `coauthor/2026-05-18-git-good/inventory.md` with one row per recommended path: a level-1 path column, the recommendation, and a one-line reason. Organize the file by top-level directory (`coauthor/`, `outputs/`, `scripts/`, `TRA-contracts/`, `tests/`, etc.) so the user can scan section by section.
4. At the top of `inventory.md`, write a short summary: total paths inspected, count by recommendation, and any "decision needed" items flagged for the user.

**Return:**

- Path to `inventory.md`.
- A one-paragraph summary of what was found and where the load-bearing keep/delete decisions land.

### S2: Skill relocation

**Actions:**

1. Confirm the source skills exist at `~/.claude/skills/tra-download-filings`, `~/.claude/skills/tra-process-filings`, `~/.claude/skills/tra-build-timeline`, `~/.claude/skills/tra-htm-to-md`, `~/.claude/skills/tra-packet`, `~/.claude/skills/sec-edgar`.
2. `mkdir -p $PROJECT_ROOT/.claude/skills/` and move each source directory into it: `mv ~/.claude/skills/tra-* ~/.claude/skills/sec-edgar $PROJECT_ROOT/.claude/skills/`. Use `mv` (not `cp`) so the canonical copy lives under the project; the global location no longer carries them. The `.claude/skills/` path is Claude Code's documented project-skill auto-load location.
3. Grep the project tree (`scripts/`, `coauthor/`) for absolute paths referencing `~/.claude/skills/tra-*` or `~/.claude/skills/sec-edgar` and update each match to the new project-relative path. Use `grep -r "claude/skills/" $PROJECT_ROOT/scripts/ $PROJECT_ROOT/coauthor/`.
4. Verify each relocated skill still loads: run `claude --plugins` or equivalent (check that the skill listing includes the relocated ones). If the global skill mechanism does not pick up project-local skills automatically, document that in DEVIATIONS-coder.md and stop; the user resolves before s3.

**Return:**

- Confirmation that the six skills now live under `.claude/skills/` and load from there.
- List of files whose references were updated (if any).

### S3: Execute cleanup

**Actions:**

1. Wait for the user's sign-off on `inventory.md` before any destructive action. The PM gates this step on explicit user approval.
2. For each `delete` recommendation in the signed-off `inventory.md`, `rm` or `rm -r` the path. For `move` recommendations, `mv` to the indicated destination. For `gitignore` recommendations, append the path to a `.gitignore` at the project root.
3. Create or extend `$PROJECT_ROOT/.gitignore` to include `TRA-contracts/` (the per-firm corpus stays on disk but does not enter the repo) plus any other paths flagged `gitignore` in `inventory.md`.
4. Confirm the cleaned tree compiles end-to-end: re-run `pixi run -- python scripts/build_tra_database.py` and confirm it still produces the three csv outputs. (Parquet conversion is s4; this run is a sanity check that nothing required by the build was deleted.)

**Return:**

- Summary of paths deleted, moved, and gitignored.
- Confirmation that the database build script still runs end-to-end on the cleaned tree.

### S4: Parquet conversion

**Actions:**

1. Edit `scripts/build_tra_database.py` to write parquet outputs in place of csv: change `.write_csv(...)` calls to `.write_parquet(...)`, and rename the output filenames from `*.csv` to `*.parquet`. Preserve column ordering and schema; the existing schema-overrides logic for `cik` / `ciks` as strings transfers directly to parquet without manual override.
2. Edit `scripts/build_dashboard.py` to read parquet inputs: change `pl.read_csv(...)` calls to `pl.read_parquet(...)`. Update the three filename references.
3. Run `pixi run -- python scripts/build_tra_database.py` and confirm `tras.parquet`, `events.parquet`, `stock_by_date.parquet` are written.
4. Run `pixi run -- python scripts/build_dashboard.py` and confirm `dashboard.html` is rebuilt. Open the rendered HTML and confirm the three pages still render; report what cannot be visually verified (per "Honesty about untestable output" in the canonical rules).
5. Verify parquet row counts match the prior csv row counts (`tras 360`, `events 1635`, `stock_by_date 8415`). Update `outputs/tra-database/SCHEMA.md` to reflect the parquet filenames and column types.

**Return:**

- Confirmation that the three parquet files exist at expected row counts.
- Path to the rebuilt `dashboard.html` and a note on what was visually verifiable.

### S5: README

**Actions:**

1. Read `outputs/tra-database/SCHEMA.md` to anchor the schema-pointer section.
2. Read each relocated skill's `SKILL.md` to write a one-line catalog entry per skill (tra-download-filings, tra-process-filings, tra-build-timeline, tra-htm-to-md, tra-packet, sec-edgar; tra-refresh is added in s7 and inserted into the catalog at that step).
3. Draft `$PROJECT_ROOT/README.md` with four sections: Workflow (pipeline steps with exact commands), Environment (pixi setup, dependency install, how to run scripts), Outputs (where parquet files and dashboard.html land), Schema pointer (link to `outputs/tra-database/SCHEMA.md`), Skill catalog (one-line per skill).
4. Run each documented command on a clean shell to verify it actually works.

**Return:**

- Path to `README.md`.
- Confirmation that every documented command ran without error.

### S6: Git init and private GitHub push

**Actions:**

1. Confirm cwd is `$PROJECT_ROOT/` and `.gitignore` is in place (from s3).
2. `git init`. Stage everything not gitignored: `git add -A`. Commit with a baseline message documenting "first clean baseline after cleanup pass".
3. Create the private repo with `gh repo create <name> --private --source=. --remote=origin`. Confirm with the user before this step whether the repo name should default to `tra` or something else.
4. `git push -u origin main`. Confirm the push succeeded.
5. Verify the remote shows the expected files and that `TRA-contracts/` did not leak in.

**Return:**

- GitHub URL of the private repo.
- Confirmation that the local `main` tracks `origin/main` and that the gitignored corpus is absent from the remote.

### S7: tra-refresh skill

**Actions:**

1. Read existing skills' `SKILL.md` files to match house style for the new skill.
2. Design `.claude/skills/tra-refresh/SKILL.md`: trigger phrases ("refresh the TRA database", "check EDGAR for new TRA filings"), tool list, action sequence. The action sequence: (i) read `outputs/tra-database/last_refresh.json` for the prior cutoff (or default to the maximum filing date in `events.parquet` if missing); (ii) load the CIK list from `tras.parquet`; (iii) query EDGAR per CIK for filings filed after the cutoff using the `sec-edgar` skill; (iv) filter to TRA-relevant form types (10-K, 10-Q, 8-K, S-1, S-4, prospectus variants, proxy); (v) for each new filing, run the downstream pipeline (tra-process-filings → tra-build-timeline → tra-htm-to-md) on the firm's directory; (vi) re-run `scripts/build_tra_database.py` to regenerate parquets; (vii) write a new `last_refresh.json` with the run date, the cutoff used, the number of firms queried, and the number of new filings folded in.
3. Implement a `--dry-run` mode that performs steps (i)-(iv) and reports what would happen without modifying any file.
4. Write `.claude/skills/tra-refresh/SKILL.md` and any helper Python under `.claude/skills/tra-refresh/`. The helper code lives next to the SKILL.md so the skill self-contains.
5. Run a dry-run on the current database. Confirm the EDGAR query returns sensible counts and the cutoff logic uses the right starting date.
6. Run the skill live to write the baseline `outputs/tra-database/last_refresh.json` (date = today, cutoff = today since the corpus reflects current state).
7. Add the new skill's one-liner to `README.md`'s skill catalog.

**Return:**

- Path to `.claude/skills/tra-refresh/`.
- Dry-run output (sample) and the written `last_refresh.json`.

### S8: Systematic rerun (placeholder)

**Actions:**

1. Refined after s7 freezes. The decomposition depends on the final skill shapes from s7 and any skill edits committed during steps s1-s7.
2. Indicative content: re-collect a fresh CIK seed list from EDGAR full-text search; download filings per firm; run the per-firm processing chain; rebuild the database; rebuild the dashboard; run `tra-refresh` to write the post-rerun `last_refresh.json`.

**Return:**

- TBD when s8 is refined.

## Review specifications

### S1: Inventory and keep/delete recommendations

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] Every top-level entry under `$PROJECT_ROOT/` appears in `inventory.md` (no silently omitted paths). (replicability)
- [ ] Each row carries one of `keep`, `delete`, `move <dest>`, `gitignore` and a one-line reason. (methodology)
- [ ] `TRA-contracts/` is flagged `gitignore` rather than `delete`. (methodology)
- [ ] Companion metadata files (`contract_log.md`, `filing_notes.md`, `*_summary.qmd`) inside `TRA-contracts/<firm>/` are not flagged for deletion (per the standing instruction never to sweep companion metadata). (methodology)
- [ ] "Decision needed" rows are flagged explicitly at the top of the file. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S2: Skill relocation

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] All six skill directories exist under `.claude/skills/` after the move. (replicability)
- [ ] None of the six exist under `~/.claude/skills/` after the move (the move emptied the source location). (replicability)
- [ ] No in-project script references an absolute path under `~/.claude/skills/tra-*` or `~/.claude/skills/sec-edgar`. (methodology)
- [ ] The relocated skills load from the project (verified by listing skills in a Claude Code session). (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S3: Execute cleanup

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] No path was deleted that is not flagged `delete` in the signed-off `inventory.md`. (methodology)
- [ ] `.gitignore` exists at the project root and includes `TRA-contracts/`. (replicability)
- [ ] `pixi run -- python scripts/build_tra_database.py` still runs end-to-end after cleanup. (replicability)
- [ ] No companion metadata file under `TRA-contracts/<firm>/` was deleted. (methodology)

**Researcher deviation-monitor**: always runs in parallel.

### S4: Parquet conversion

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] `outputs/tra-database/tras.parquet`, `events.parquet`, `stock_by_date.parquet` exist. (replicability)
- [ ] Row counts match the prior csv outputs (360, 1635, 8415). (methodology)
- [ ] `cik` and `ciks` columns retain their string type (leading zeros preserved) in the parquet output. (methodology)
- [ ] `scripts/build_dashboard.py` reads parquet and produces a `dashboard.html` of comparable size to the prior csv-based build. (replicability)
- [ ] `outputs/tra-database/SCHEMA.md` is updated to reference the parquet filenames. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S5: README

**Intended reviewers**: framing, replicability.

**Checklist:**

- [ ] Workflow section lists pipeline steps in order with the exact command to invoke each. (framing)
- [ ] Environment section documents `pixi install` and the `pixi run --` prefix convention. (replicability)
- [ ] Outputs section names where parquet files and `dashboard.html` land. (framing)
- [ ] Schema pointer links to `outputs/tra-database/SCHEMA.md`. (framing)
- [ ] Skill catalog has one line per relocated skill describing what it does. (framing)
- [ ] Every documented command runs without error from a fresh shell. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S6: Git init and private GitHub push

**Intended reviewers**: replicability.

**Checklist:**

- [ ] `.git/` exists at the project root. (replicability)
- [ ] Initial commit on `main` includes README, scripts, skills, outputs (parquet + dashboard), and the `coauthor/` tree. (replicability)
- [ ] Remote `origin` points at a private GitHub repo under the user's account. (replicability)
- [ ] `TRA-contracts/` is absent from the pushed tree on the remote. (replicability)
- [ ] No file containing credentials or API keys was committed. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S7: tra-refresh skill

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] `.claude/skills/tra-refresh/SKILL.md` exists and follows the same header structure as the other relocated skills. (replicability)
- [ ] The skill's `--dry-run` mode reports what it would do without modifying any file. (methodology)
- [ ] The skill reads the prior cutoff from `outputs/tra-database/last_refresh.json` (or falls back to the max event date if absent). (methodology)
- [ ] `outputs/tra-database/last_refresh.json` is a valid JSON file with `run_date`, `cutoff_date`, `firms_queried`, `new_filings_count` keys after a live run. (replicability)
- [ ] The skill's catalog entry is added to `README.md`. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S8: Systematic rerun

Review specifications deferred until s8 is refined (per the placeholder note in the decomposition table).

**Researcher deviation-monitor**: always runs in parallel.
