---
project_id: 2026-05-18-git-good
name: git-good
status: frozen
created: 2026-05-18
---

# Scope

## Goal

Take the working but messy TRA pipeline (skill files scattered under `~/.claude/skills/`, csv outputs, ad-hoc directory layout from the first build) and turn it into a self-contained, reproducible repository on private GitHub. Done means: the project is on private GitHub with a clean directory layout, parquet outputs in place of csvs, a README documenting the workflow and skill catalog, the TRA + SEC EDGAR skills living under the project tree, and a second end-to-end pass run on a fresh CIK seed list using improved skills.

## Why this matters

The first pass through the corpus build was exploratory; the lessons (skill behaviour, edge cases, layout decisions) have not been folded back into the skills or the directory. Without that fold-back, the work is not reproducible by anyone else (or future-me), and the seed list is ad-hoc rather than the result of a documented EDGAR query. Making the project repository-ready also unblocks collaboration: the second pass can be reviewed and re-run by a fresh checkout.

## Scope

Eight concrete deliverables, sequenced:

1. **Skill relocation.** Move the TRA-family skills (`tra-download-filings`, `tra-process-filings`, `tra-build-timeline`, `tra-htm-to-md`, `tra-packet`) and `sec-edgar` from `~/.claude/skills/` into the project tree (e.g. `skills/` under the project root). After the move, those skills load from the project rather than the global location.
2. **Keep/delete cleanup pass.** Produce a single markdown deliverable listing every folder, file, and subfolder in the project with a recommendation (`keep`, `delete`, `move`, `gitignore`) and a one-line reason. The user reviews and signs off; the script then performs the actions.
3. **Parquet conversion.** Rewrite `scripts/build_tra_database.py` to emit `tras.parquet`, `events.parquet`, `stock_by_date.parquet` in place of the csvs. Update `scripts/build_dashboard.py` to read parquet. Verify the dashboard still builds and renders.
4. **README.** Write a top-level `README.md` covering: workflow steps and commands to run each (CIK seed list, download, process, build timeline, htm-to-md, compile database, build dashboard, refresh), pixi environment setup, where outputs land, a pointer to `outputs/tra-database/SCHEMA.md` for column definitions, and a skill catalog with one line per skill.
5. **Git init + private GitHub.** Initialize the repo, commit the cleaned-up state, create a private GitHub repo under the user's account, push.
6. **Skill edits.** Improve the relocated skills based on lessons from the first pass (specific lessons identified during the rerun, recorded as deviations as they come up). Commit and push the edits.
7. **EDGAR refresh skill.** Build a new skill (working name `tra-refresh`) that takes the CIKs already in the database, queries EDGAR for filings posted since the last refresh cutoff, identifies TRA-relevant ones, runs them through the existing pipeline (download → process → build-timeline → htm-to-md → compile-database), and updates the parquet outputs in place with any new events / amendments / terminations. The skill writes a refresh-metadata file (e.g. `outputs/tra-database/last_refresh.json`) recording the run date, the EDGAR filing-date cutoff, the number of firms queried, and the number of new filings folded in. Re-invoking the skill on a later date uses the recorded cutoff so each refresh covers only the gap since the last one.
8. **Systematic rerun.** Re-collect the CIK seed list from EDGAR full-text search (rather than the ad-hoc list from pass one), run the improved skills end-to-end, rebuild the database, regenerate the dashboard. The resulting corpus may add or drop firms relative to the current 321; that is expected. The rerun serves as an integration test of the full toolkit, the refresh skill included (initial refresh metadata written at the end of this step).

Sequencing: 1, 2, 3, 4 happen first as a single cleanup block. Then 5 (git init + initial commit + push). Then 6 (skill edits during early rerun). Then 7 (build the refresh skill, committed and pushed). Then 8 completes the rerun with the improved skills + refresh skill, with edits pushed as they happen.

## Approach summary

Mechanical work for items 1-4 (file moves, build-script rewrite, README draft), human-in-the-loop sign-off for the keep/delete deletion step, then git plumbing for item 5, the new refresh skill in item 7, and the integration rerun in item 8 which produces the load-bearing deliverable: a reproducible end-to-end corpus build plus a verified incremental-refresh path. Skill edits in item 6 are interleaved with item 8 since the lessons that motivate them only become visible during re-execution.

## Out of scope

- The carrying-values / TRA-liability time series (deferred S6 from the prior project; depends on a separate LLM extraction pass).
- Any change to the dashboard's analytical content beyond pointing it at parquet inputs.
- Academic paper writing or descriptive statistics work.

## Definition of done

- Private GitHub repo exists, current state pushed.
- `TRA-contracts/` is gitignored; `outputs/tra-database/{tras,events,stock_by_date}.parquet` exist; `outputs/tra-database/dashboard.html` opens locally and renders.
- `README.md` at repo root with the four documented sections.
- TRA + SEC EDGAR skills (plus the new `tra-refresh` skill) live under `skills/` in the project tree and load from there.
- A second end-to-end run has produced a regenerated corpus from a fresh CIK seed list using the improved skills, with the database and dashboard rebuilt from it.
- `outputs/tra-database/last_refresh.json` exists, written by the refresh skill at the end of the rerun, recording the date and EDGAR filing-date cutoff used.

## Open questions for user

None at scope-freeze. Specific lessons that motivate skill edits in step 6 will be identified during the rerun and recorded as deviations.
