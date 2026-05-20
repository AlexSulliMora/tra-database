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
| s7a | coder | Build candidate-discovery scripts at `scripts/find_candidates.py` (sweep EDGAR full-text search for the four TRA phrase variants across all time in monthly windows; bi-week halving on overflow; save union to `data/edgar-query/full-text.parquet`) and `scripts/pull_exhibits.py` (read the parquet, fetch each filing's index, filter to EX-10.* documents, download to `data/edgar-query/exhibits/<CIK>/`). The work is deterministic and ships as plain scripts under `scripts/` | sec-edgar package, retained scripts/tra_master_cik_list*.py and scripts/tra_body_vs_exhibit.py | `scripts/find_candidates.py`, `scripts/pull_exhibits.py`, `data/edgar-query/full-text.parquet`, `data/edgar-query/exhibits/` (plus DEVIATIONS-coder.md if deviated) | none |
| s7b | coder | Build the manual TRA classification step (a script that presents each EX-10.* candidate exhibit from `data/edgar-query/exhibits/` alongside the source filing's form, date, and a path to open the exhibit, then prompts the user for is_tra: yes/no/maybe) | s7a exhibits tree and manifest at `data/edgar-query/exhibits/manifest.csv` | `scripts/classify_candidates.py`, decision CSV recording is_tra verdict per candidate at `data/edgar-query/classifications.csv` (plus DEVIATIONS-coder.md if deviated) | none |
| s7c | coder | Rewrite `tra-download-filings` to the narrower spec: takes the confirmed-TRA-CIK list as input; pulls only 8-K, 10-K, the final IPO prospectus (one 424B per firm), and their exhibits. The three-query union, allow-list post-filter, S-1/S-4/424B completeness pass, and corporate-events query all retire | s7b output, .claude/skills/tra-download-filings/ | revised SKILL.md and helper code; downloads for trial CIK set verified (plus DEVIATIONS-coder.md if deviated) | none |
| s7d | coder | Edit `tra-process-filings` to read markdown instead of HTML (`tra-htm-to-md` now runs before `tra-process-filings`); remove the HTML-strip step from the SKILL.md | .claude/skills/tra-process-filings/ | revised SKILL.md (plus DEVIATIONS-coder.md if deviated) | s7c |
| s7e | coder | Retire `tra-packet`: delete `.claude/skills/tra-packet/` and `scripts/tra_packet/`; remove the catalog entry from `README.md` | .claude/skills/tra-packet/, scripts/tra_packet/, README.md | deleted skill + helper; README.md updated (plus DEVIATIONS-coder.md if deviated) | none |
| s7f | coder | Relocate skill-internal scripts into their owning skill directories: `scripts/sec_edgar/` → `.claude/skills/sec-edgar/scripts/sec_edgar/`; `scripts/tra_download.py` → `.claude/skills/tra-download-filings/scripts/`. Update every SKILL.md path reference (in-project absolute paths and `PYTHONPATH=scripts` invocations) to point at the new locations | scripts/, .claude/skills/* | scripts/ now contains only `build_tra_database.py` and `build_dashboard.py` plus any user-kept exploratory scripts; SKILL.md path refs updated (plus DEVIATIONS-coder.md if deviated) | none |
| s7g | coder | Build `tra-refresh` skill: for each confirmed-TRA CIK, query EDGAR for filings since the last cutoff in the new narrower form set (8-K, 10-K, final prospectus, exhibits), run the downstream pipeline (htm-to-md → process-filings → build-timeline → build-database), update parquet outputs in place, write `last_refresh.json` | s7a-s7f outputs, outputs/tra-database/ | .claude/skills/tra-refresh/ with SKILL.md and helper code; baseline `last_refresh.json` written (plus DEVIATIONS-coder.md if deviated) | none |
| s8 | TBD | Systematic rerun: run the new workflow end-to-end (s7a candidates discovery → s7b manual classification → s7c targeted downloads → htm-to-md → s7d markdown-reading process-filings → build-timeline → build-database → build-dashboard → s7g refresh writes baseline last_refresh.json). The resulting corpus may add or drop firms relative to the current 321 | s7a-s7g outputs | regenerated corpus, rebuilt parquet outputs, dashboard.html, last_refresh.json (plus DEVIATIONS-*.md per worker) | none |

Workers write DEVIATIONS files only when a step diverged from `ca-02-plan.md` or required a discretionary judgment call. Routine "what I did" content is captured in the per-worker audit log under `<slug>/.audit/<worker>.md`. A second step for the same worker appends a new dated section to the same `DEVIATIONS-<worker>.md` rather than overwriting.

**Step s8 was a placeholder in the original plan.** The 2026-05-19 amendment that introduced s7a-s7g also resolved s8's decomposition: a single orchestrator-driven step that walks the new workflow end-to-end, since each skill in the chain owns its own DEVIATIONS file and the per-skill reviewer specs already cover the load-bearing checks. Substantive divergences during s8 are recorded as DEVIATIONS entries in the relevant worker's file.

## Success criteria

- Every folder, file, and subfolder under the project root appears in `inventory.md` with one of {keep, delete, move, gitignore} and a one-line reason.
- All TRA-family skills and `sec-edgar` load from `.claude/skills/` under the project (not from `~/.claude/skills/`) after s2 + s3.
- `outputs/tra-database/{tras,events,stock_by_date}.parquet` exist and round-trip the row counts from the prior csv outputs (360 / 1635 / 8415). The dashboard rebuild from parquet inputs renders.
- `README.md` covers workflow, commands, pixi setup, output locations, schema pointer, and skill catalog; every documented command runs without error from a fresh checkout.
- Private GitHub repo exists; `TRA-contracts/` is in `.gitignore`; the cleaned baseline is pushed to `main`.
- `scripts/find_candidates.py` (s7a) runs EDGAR full-text search in monthly windows and writes the union of matching filings to `data/edgar-query/full-text.parquet`. `scripts/pull_exhibits.py` reads that parquet, fetches each filing's index, filters to EX-10.* documents, and downloads them to `data/edgar-query/exhibits/<CIK>/` with a manifest at `data/edgar-query/exhibits/manifest.csv`.
- Manual classification step (s7b, `scripts/classify_candidates.py`) produces `data/edgar-query/classifications.csv` with one row per candidate exhibit; the confirmed-TRA-CIK list for s7c is the unique CIK set among `is_tra=yes` rows.
- Revised `tra-download-filings` (s7c) takes a CIK list and pulls only 8-K, 10-K, final prospectus, and their exhibits.
- `tra-process-filings` (s7d) reads markdown input (htm-to-md runs first in the chain).
- `.claude/skills/tra-packet/` and `scripts/tra_packet/` are deleted (s7e); README catalog entry removed.
- `scripts/` after s7f contains only `build_tra_database.py`, `build_dashboard.py`, and any user-kept exploratory scripts; all skill-internal code lives under `.claude/skills/<skill>/scripts/`.
- `tra-refresh` skill (s7g) loads and runs in a dry-run mode that reports what it would do without modifying the parquets. A live run writes a valid `last_refresh.json`.
- Step s8 produces a regenerated corpus via the new discover → classify → narrow-download → htm-to-md → process → timeline → build chain, with a rebuilt database and dashboard and initial refresh metadata.

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

### S7a: Build candidate-discovery scripts

**Actions:**

1. Write `scripts/find_candidates.py`. The script: (i) queries the EDGAR full-text search index for each of the four TRA phrase variants (`"tax receivable agreement"`, `"tax receivable agreements"`, `"tax receivables agreement"`, `"tax receivables agreements"`) across `--start` through `--end` in monthly windows; (ii) bi-week halves any month-window where a query hits the 10,000-result ceiling; (iii) retries HTTP 5xx with back-off; (iv) unions the four queries' results on `adsh` per month, then concatenates across months; (v) writes the result to `--save-union-parquet` (default `data/edgar-query/full-text.parquet`). Use `sec_edgar.search.search_filings` from the `sec_edgar` package at `scripts/sec_edgar/`. The script is sweep-only by design; the exhibit-pull stage lives in a separate script.
2. Write `scripts/pull_exhibits.py`. The script: (i) reads the parquet at `--parquet` (default `data/edgar-query/full-text.parquet`); (ii) iterates rows, calling `fetch_filing_index(cik, adsh)` per row; (iii) filters the document list to entries matching the EX-10.* regex `(?:^|[^a-z])d?ex(?:hibit)?[-_]?10[._\-]?\d` and the extension allow-list `{.htm, .html, .txt}`; (iv) downloads each match via `fetch_document(cik, adsh, filename)` to `--output-dir/<CIK>/<accession>_<filename>` (default `data/edgar-query/exhibits/<CIK>/`); (v) appends to a manifest at `<output-dir>/manifest.csv` with columns `cik, accession, filename, filing_date, form, phrase_variants_matched`. Idempotent: skip exhibits already on disk.
3. The candidate-discovery work is deterministic, so no skill folder is created. Scripts live under `scripts/` alongside `build_tra_database.py` and `build_dashboard.py`. The README workflow section documents both commands.
4. Verify on a small time window. Run `find_candidates.py --start 2024-06 --end 2024-06 --save-union-parquet data/edgar-query/trial-2024-06.parquet` and confirm the parquet writes. Run `pull_exhibits.py --parquet data/edgar-query/trial-2024-06.parquet --output-dir data/edgar-query/trial-exhibits --limit 5` and confirm exhibits land on disk. Delete the trial outputs afterwards.

**Return:**

- Paths to `scripts/find_candidates.py` and `scripts/pull_exhibits.py`.
- Trial-run counts on the one-month window: hits per phrase variant, union size, EX-10.* exhibits pulled.

### S7b: Build manual TRA classification step

**Actions:**

1. Write `scripts/classify_candidates.py` (plain script, no skill folder; the work is deterministic interactive I/O).
2. Implement the script: load `data/edgar-query/exhibits/manifest.csv`, iterate over the exhibits, present each with the firm name (resolve via `fetch_submissions` for the CIK), the filing form type, the filing date, and a path to the exhibit file the user can open in a viewer. Prompt for `is_tra: y/n/m` (yes / no / maybe). Write each decision to `data/edgar-query/classifications.csv` with columns `cik, accession, filename, is_tra, classified_at`.
3. Idempotency: re-running the script should skip exhibits already in classifications.csv. The user can cancel partway through and resume.
4. Verify on a small batch: classify 10 candidates and confirm the CSV writes correctly.

**Return:**

- Path to `scripts/classify_candidates.py`.
- Sample output of `data/edgar-query/classifications.csv` after the trial batch.

### S7c: Rewrite `tra-download-filings` to the narrower spec

**Actions:**

1. Read the existing `.claude/skills/tra-download-filings/SKILL.md` to identify the sections to remove (three-query union, EDGAR full-text search per CIK, S-1/S-4/424B completeness pass, corporate-events query, ALLOWED_FORMS allow-list).
2. Rewrite the SKILL.md Workflow section. New action sequence: (i) load the confirmed-TRA-CIK list (derived from `candidates/classifications.csv` by selecting unique CIKs where `is_tra = yes`); (ii) for each CIK, call `list_filings_by_form(cik, form_type)` for each form in `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}`; (iii) for each filing, fetch every document in its index.json (the full filing including the primary doc and all exhibits, scoped to this filing only); (iv) save under `TRA-contracts/<firm-slug>/<accession>/<filename>`; (v) per firm, select the single "final IPO prospectus" by taking the latest `424B*` filed within 7 days of the IPO date, where the IPO date is inferred from the earliest 8-K with Item 1.01 mentioning an IPO. Document the inference rule in the SKILL.md.
3. Update or simplify the helper script at `scripts/tra_download.py` (or wherever it lands after s7f relocates it). Remove the three-query union and the allow-list post-filter; keep the rate-limit retry wrapper.
4. Verify by running against a small confirmed-TRA-CIK list (e.g., 3 firms) and confirming only the narrower form set is fetched.

**Return:**

- Diff or summary of changes to `tra-download-filings/SKILL.md`.
- Trial-run download counts per firm (number of filings fetched, broken down by form type).

### S7d: Edit `tra-process-filings` to read markdown

**Actions:**

1. Read `.claude/skills/tra-process-filings/SKILL.md`, locate Step 1 ("Strip HTML and read").
2. Remove the HTML-strip step. Replace with: "Read the markdown companion produced by `tra-htm-to-md` for each filing's documents. The markdown lives next to the source HTML in the same accession directory."
3. Update any references to HTML-specific behavior (e.g., the `html.parser` mention) and confirm the workflow ordering note at the top of the file reflects that `tra-htm-to-md` runs first.
4. The classification logic (Steps 2-7) stays unchanged; only the read source changes.

**Return:**

- The diff of changes to `tra-process-filings/SKILL.md`.

### S7e: Retire `tra-packet`

**Actions:**

1. Delete `.claude/skills/tra-packet/`.
2. Delete `scripts/tra_packet/`.
3. Edit `README.md` to remove the `tra-packet` row from the skill catalog table.
4. Search the project for any remaining references to `tra-packet` (`grep -rn "tra-packet" $PROJECT_ROOT/ --exclude-dir={.pixi,.tra_history_cache,sec-data-pqt,.git,TRA-contracts,__pycache__}`). Update each.

**Return:**

- Confirmation that both paths are gone.
- List of files where references were updated.

### S7f: Relocate skill-internal scripts

**Actions:**

1. Move `scripts/sec_edgar/` to `.claude/skills/sec-edgar/scripts/sec_edgar/`. Preserve the package structure (the `sec_edgar/` directory containing `client.py`, `submissions.py`, `forms.py`, `search.py`, `archives.py`, `concept.py`, `__init__.py`, `test_index_coverage.py`).
2. Move `scripts/tra_download.py` to `.claude/skills/tra-download-filings/scripts/tra_download.py`.
3. Update every `PYTHONPATH=scripts` invocation in any SKILL.md file. The new invocation pattern: `PYTHONPATH=.claude/skills/sec-edgar/scripts pixi run python -c "from sec_edgar import ..."`. Grep with `grep -rn "PYTHONPATH=scripts\|scripts/sec_edgar\|scripts/tra_download" $PROJECT_ROOT/.claude/skills/ $PROJECT_ROOT/README.md`.
4. Run `pixi run -- python scripts/build_tra_database.py` to confirm the build still works after the moves (it does not depend on `sec_edgar`, so it should still succeed).
5. Verify a sample import still resolves: `PYTHONPATH=.claude/skills/sec-edgar/scripts pixi run python -c "from sec_edgar import fetch_submissions; print(fetch_submissions)"`.

**Return:**

- The mv commands run.
- List of SKILL.md and README files whose path references were updated.
- Confirmation of the sample import.

### S7g: Build `tra-refresh` skill

**Actions:**

1. Design `.claude/skills/tra-refresh/SKILL.md`. Trigger phrases: "refresh the TRA database", "check EDGAR for new TRA filings". The action sequence: (i) read `outputs/tra-database/last_refresh.json` for the prior cutoff (or default to the max `filingDate` across the existing `events.parquet` rows if missing); (ii) load the confirmed-TRA-CIK list from `tras.parquet`; (iii) for each CIK, call `list_filings_by_form(cik, form_type)` for each form in `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}` filtered to `filingDate > cutoff`; (iv) save new filings under `TRA-contracts/<firm-slug>/<accession>/<filename>`; (v) run `tra-htm-to-md` on each new accession directory; (vi) run `tra-process-filings` on each affected firm directory; (vii) run `tra-build-timeline` to refresh per-firm summaries; (viii) re-run `scripts/build_tra_database.py` to regenerate the parquets; (ix) write a new `last_refresh.json` with `run_date`, `cutoff_date`, `firms_queried`, `new_filings_count`.
2. Implement a `--dry-run` mode that performs steps (i)-(iii) and reports what would happen without writing any new file or modifying parquets.
3. Write the SKILL.md and helper Python under `.claude/skills/tra-refresh/`. The helper code lives next to the SKILL.md so the skill self-contains.
4. Run a dry-run on the current database and confirm the cutoff logic and EDGAR query return sensible counts.
5. Run the skill live at the end of s8 to write the baseline `last_refresh.json` (the post-rerun corpus is the initial baseline).
6. Add the new skill's one-liner to `README.md`'s skill catalog.

**Return:**

- Path to `.claude/skills/tra-refresh/`.
- Dry-run output sample and the written `last_refresh.json` after the live run.

### S8: Systematic rerun

**Actions:**

1. Run `scripts/find_candidates.py` over the EDGAR full-text history in monthly windows, writing `data/edgar-query/full-text.parquet`. Then run `scripts/pull_exhibits.py` against that parquet to download all EX-10.* documents into `data/edgar-query/exhibits/<CIK>/`.
2. Run `scripts/classify_candidates.py` over `data/edgar-query/exhibits/manifest.csv`. The user marks each candidate yes/no/maybe.
3. Derive the confirmed-TRA-CIK list from `data/edgar-query/classifications.csv` (unique CIKs where `is_tra = yes`).
4. Run the rewritten `tra-download-filings` (s7c) against the confirmed-TRA-CIK list. Saves filings under `TRA-contracts/<firm-slug>/`.
5. Run `tra-htm-to-md` against each per-firm `TRA-*/` subdirectory once `tra-process-filings` has placed contracts there. Order note: `tra-htm-to-md` per the new workflow runs BEFORE `tra-process-filings`'s contract classification, so the markdown is available when classification reads filings; but `tra-htm-to-md` operates on contracts that `tra-process-filings` has already moved into `TRA-*/`. Reconcile this ordering during s8 if it bites; likely fix is to have `tra-htm-to-md` run twice, once over `<accession>/` directories for the markdown source the classifier reads, and once more over the final `TRA-*/` subdirectories after classification.
6. Run the markdown-reading `tra-process-filings` (s7d) per firm.
7. Run `tra-build-timeline` per firm to produce `<firm>_summary.qmd` files.
8. Run `scripts/build_tra_database.py` to produce the three parquet files.
9. Run `scripts/build_dashboard.py` to produce `dashboard.html`.
10. Run `tra-refresh` (s7g) in live mode to write the baseline `last_refresh.json`.
11. Commit and push the updated parquets and dashboard.

**Return:**

- Counts at each stage: candidates pulled, exhibits classified yes/no/maybe, confirmed CIKs, filings downloaded, contracts identified, summaries written, parquet row counts.
- Path to the final `dashboard.html` and `last_refresh.json`.

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

### S7a: Build candidate-discovery scripts

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] `scripts/find_candidates.py` and `scripts/pull_exhibits.py` exist; no `.claude/skills/tra-find-candidates/` folder remains. (replicability)
- [ ] `find_candidates.py` documents monthly windowing as the strategy to stay under the 10,000-result full-text-search ceiling, with bi-week halving as the overflow path. (methodology)
- [ ] All four phrase variants are queried by `find_candidates.py`; the union is deduplicated on `adsh`. (methodology)
- [ ] `pull_exhibits.py` saves only `EX-10.*` documents; the parent filing's primary document and other exhibits are excluded. (methodology)
- [ ] A manifest is written at `data/edgar-query/exhibits/manifest.csv` with one row per saved exhibit. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S7b: Build manual TRA classification step

**Intended reviewers**: methodology.

**Checklist:**

- [ ] The classification step writes one row per candidate to `data/edgar-query/classifications.csv` with `is_tra` ∈ `{yes, no, maybe}`. (methodology)
- [ ] Re-running the script skips exhibits already classified. (methodology)
- [ ] The script presents the firm name, filing form, filing date, and a path to the exhibit file alongside the accession number. (methodology)

**Researcher deviation-monitor**: always runs in parallel.

### S7c: Rewrite `tra-download-filings`

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] The SKILL.md inputs section names the confirmed-TRA-CIK list as input (not an FTS query). (methodology)
- [ ] The form set is exactly `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}` plus their exhibits. (methodology)
- [ ] The three-query union, allow-list post-filter, S-1/S-4/424B completeness pass, and corporate-events query are removed from the SKILL.md. (methodology)
- [ ] The IPO-prospectus selection rule (latest 424B within 7 days of the IPO 8-K Item 1.01 date) is documented. (methodology)
- [ ] A trial download on 3 firms succeeds and fetches only the documented form set. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S7d: Edit `tra-process-filings`

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] The "Strip HTML and read" step is removed from the SKILL.md. (methodology)
- [ ] The Workflow opening clarifies that `tra-htm-to-md` has produced markdown companions which the skill reads. (methodology)
- [ ] The classification logic (Steps 2-7 in the prior SKILL.md) is unchanged. (methodology)

**Researcher deviation-monitor**: always runs in parallel.

### S7e: Retire `tra-packet`

**Intended reviewers**: replicability.

**Checklist:**

- [ ] `.claude/skills/tra-packet/` no longer exists. (replicability)
- [ ] `scripts/tra_packet/` no longer exists. (replicability)
- [ ] `README.md` skill catalog no longer lists `tra-packet`. (replicability)
- [ ] No remaining references to `tra-packet` exist outside `coauthor/` (historical project records under coauthor/ stay as-is). (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S7f: Relocate skill-internal scripts

**Intended reviewers**: replicability.

**Checklist:**

- [ ] `.claude/skills/sec-edgar/scripts/sec_edgar/` exists with the full package contents. (replicability)
- [ ] `.claude/skills/tra-download-filings/scripts/tra_download.py` exists. (replicability)
- [ ] `scripts/` no longer contains `sec_edgar/` or `tra_download.py`. (replicability)
- [ ] Every `PYTHONPATH=scripts` reference in any SKILL.md or README.md is updated to the new path. (replicability)
- [ ] `pixi run -- python scripts/build_tra_database.py` still runs end-to-end. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S7g: Build `tra-refresh` skill

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] `.claude/skills/tra-refresh/SKILL.md` exists and follows the house style. (replicability)
- [ ] The skill reads the prior cutoff from `outputs/tra-database/last_refresh.json` (or falls back to the max filingDate across `events.parquet` if missing). (methodology)
- [ ] The skill's form set matches the new narrow set (`8-K, 10-K, 424B*` plus exhibits) consistent with the revised `tra-download-filings`. (methodology)
- [ ] The `--dry-run` mode reports counts without writing or modifying parquets. (methodology)
- [ ] `outputs/tra-database/last_refresh.json` is a valid JSON file with `run_date`, `cutoff_date`, `firms_queried`, `new_filings_count` keys after a live run. (replicability)
- [ ] The skill's catalog entry is added to `README.md`. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

### S8: Systematic rerun

**Intended reviewers**: methodology, replicability.

**Checklist:**

- [ ] The candidates discovery pass (s7a) ran without missing time windows (no gap between the earliest 2001 window and the current month). (replicability)
- [ ] Every candidate in `data/edgar-query/exhibits/manifest.csv` has a corresponding row in `data/edgar-query/classifications.csv`. (methodology)
- [ ] The confirmed-TRA-CIK list used in s7c is the unique CIK set among `is_tra=yes` rows. (methodology)
- [ ] The final database build produces parquet outputs with row counts of the same order of magnitude as the prior baseline (no silent collapse to zero or explosion by 10x without explanation). (replicability)
- [ ] `outputs/tra-database/dashboard.html` opens without error and contains every confirmed TRA. (replicability)
- [ ] `outputs/tra-database/last_refresh.json` is written and reflects the rerun's cutoff date. (replicability)

**Researcher deviation-monitor**: always runs in parallel.

**Researcher deviation-monitor**: always runs in parallel.
