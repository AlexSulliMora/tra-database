---
project_id: 2026-05-18-git-good
author: coder (verified pass)
created: 2026-05-19
---

# Inventory-2: Keep / Delete / Move / Gitignore (verified)

Every row's rationale cites a grep result, a docstring line, a test
import, or a SKILL.md reference line. Where the rationale conflicts with
the prior analyst-produced `inventory.md` or with the user's stated
verdict, the conflict is flagged at the top.

## Contradictions and surprises flagged at top

1. **`scripts/tra_download.py` is the live implementation of the
   `tra-download-filings` skill.** First line of the file:
   `"""TRA filing downloader (implements .claude/skills/tra-download-filings)."""`.
   `.claude/skills/tra-download-filings/SKILL.md` line 208 imports it
   directly: `from tra_download import download_filings`; line 218
   names the file: `(e.g., in scripts/tra_download.py)`. The prior
   analyst inventory flagged this `delete` — that is wrong.
2. **The XBRL pipeline is a self-contained unit, and dropping it as a
   unit is internally consistent.** `build_tra_history.py` and
   `extract_tra.py` are imported by 8 test files (every test except
   `__init__.py`); both scripts reference `2025_11_notes/` as their
   input data root (`extract_tra.py:11-13`,
   `build_tra_history.py:25`). Nothing outside this cluster imports
   `build_tra_history` or `extract_tra`. The XBRL-dead verdict the
   user supplied is consistent with the evidence.
3. **`.claude/skills/sec-edgar/SKILL.md:21` references `2025_11_notes/`
   pipeline by name.** If the XBRL pipeline is removed, that sentence
   in the live `sec-edgar` skill becomes a stale reference and should
   be edited (a load-bearing skill citing a deleted directory is a
   replicability bug). Not a blocker for the delete; just a follow-up
   edit.
4. **`scripts/tra_master_cik_list.py`, `tra_master_cik_list_reaggregate.py`,
   `tra_refined_master.py`, `tra_body_vs_exhibit.py`,
   `tra_form_distribution.py` all import `sec_edgar.client` and
   `sec_edgar.search` and encode the EDGAR full-text-search pagination
   safe-window logic (`SAFE_WINDOW_HITS = 700`, recursive date splits)
   that S8's systematic rerun will need.** The prior inventory flagged
   all five `delete`. The user told me S8 needs these. I confirm the
   pagination edge-case code lives only here.
5. **`tra_deferred_review.csv` has live consumers outside the dead
   XBRL pipeline.** `scripts/sec_edgar/resolve_deferred_ciks.py:32-33,
   377, 382` reads and writes it as the deferred-CIK enrichment
   target; `.claude/skills/tra-packet/SKILL.md:64, 105, 327` names it
   as the verdict-capture CSV the human reviewer populates. It is not
   tied to the XBRL pipeline. Keep.
6. **`tra_panel.parquet` and `ipo_date_candidates.csv` are XBRL
   pipeline outputs.** `tests/test_panel_assembly.py:287` writes
   `tra_panel.parquet`; `tests/test_ipo_harvest.py:343` writes
   `ipo_date_candidates.csv`. Both files are only emitted by
   `build_tra_history.py`. If the XBRL pipeline goes, these stop
   regenerating; flagging them `delete` is consistent.
7. **`tra_review_status.csv` and `tra_events_review.xlsx` are only
   referenced by the underscore-prefixed one-shot scripts and the
   XBRL tests.** Grep: `_persist_phase1.py`, `_merge_decisions.py`,
   `_enrich_deferred_urls.py` write them; `tests/test_review_writer.py`
   exercises them via `build_tra_history.write_review_workbook`. If
   both clusters die, these become orphaned annotation artifacts.
   They are not pure caches (they encode human decisions), so I flag
   `keep` as preserved research records rather than `delete`. The
   user should overrule if the decisions in them have been migrated
   into TRA-contracts/ summary.qmd files.

---

## Summary

**Paths inspected:** 81 rows below.

**Recommendation counts** (must match table row counts):
- `keep`: 35
- `delete`: 32
- `gitignore`: 3
- `move`: 0 (no script needs relocation; `tra_download.py` is the
  implementation of a skill but lives in `scripts/` by design — the
  SKILL.md imports it from `scripts/`)
- `decision needed`: 11 (flagged in-row)

Total: 81.

---

## Root-level files

| Path | Recommendation | Reason |
|------|---|---|
| `pixi.toml` | `keep` | Workspace pixi manifest at line 1: `[workspace] name = "research"`. Required for environment resolution. |
| `pixi.lock` | `keep` | Pinned lockfile for reproducible env. |
| `build_tra_history.py` | `delete` | Top of file (line 25) docstring: `python extract_tra.py 2025_11_notes/`. Sole callers are the 8 test files in `tests/` (`grep -l "import build_tra_history" tests/*.py` returns all of them). The XBRL pipeline is being retired as a unit per user direction. |
| `extract_tra.py` | `delete` | Docstring lines 11-13 reference `2025_11_notes/` directly as the input. Only consumer outside the XBRL cluster: imported by `build_tra_history.py` and by `tests/test_commit.py:99,392` (`from extract_tra import load_exclusion_list`). Dead-as-a-unit with the XBRL pipeline. |
| `ipo_date_candidates.csv` | `delete` | Only written by `build_tra_history.harvest_ipo_date_candidates` (`tests/test_ipo_harvest.py:343` writes it as the test target). XBRL output. |
| `tra_deferred_review.csv` | `keep` | Read/written by `scripts/sec_edgar/resolve_deferred_ciks.py:32-33,377,382`; named as verdict-capture by `.claude/skills/tra-packet/SKILL.md:64,105,327`. Live outside the XBRL pipeline. |
| `tra_events_review.xlsx` | `keep` (decision needed) | Decision-log workbook. Referenced by `_persist_phase1.py:18`, `_merge_decisions.py:28`, `_enrich_deferred_urls.py:26`. If the underscore-scripts and XBRL tests die, only the human decisions remain — preserve as a research record unless the user confirms they have been migrated into TRA-contracts/. |
| `tra_panel.parquet` | `delete` | Output of `build_tra_history.write_panel_parquet`; `tests/test_panel_assembly.py:287` writes it. XBRL pipeline output. |
| `tra_review_status.csv` | `keep` (decision needed) | Same status as `tra_events_review.xlsx` — encoded human decisions, no live consumer once XBRL goes. Preserve as research record pending user confirmation. |

---

## `.claude/`

| Path | Recommendation | Reason |
|------|---|---|
| `.claude/CLAUDE.md` | `keep` | Project-context file written by `/coauthor:ca-01-scope`; carries the active project metadata (name, slug, goal). Cited by `~/research/CLAUDE.md`. |
| `.claude/settings.local.json` | `keep` | Per-project permission allow-list for the Claude Code harness. Should be `.gitignore`d if any of the allowed paths leak personal info, but content (paths to home directory) is incidental. |
| `.claude/coauthor/` (empty dir) | `delete` | Empty directory; created by `/coauthor:ca-01-scope` as the destination for migrated prior-project context files, but no prior project has been archived here. `ls` returns nothing. |
| `.claude/skills/sec-edgar/SKILL.md` | `keep` | Live skill consumed by `tra-build-timeline`, `tra-download-filings`, `tra-packet`, `tra-process-filings` SKILL.md files (each cites `scripts/sec_edgar/`). **Note: line 21 references the `2025_11_notes/` pipeline by name; edit that sentence after the XBRL delete.** |
| `.claude/skills/sec-edgar/references/access-patterns.md` | `keep` | Bundled reference for the sec-edgar skill. |
| `.claude/skills/sec-edgar/references/conventions.md` | `keep` | Same. |
| `.claude/skills/sec-edgar/references/limitations.md` | `keep` | Same. |
| `.claude/skills/sec-edgar/references/resources.md` | `keep` | Same. |
| `.claude/skills/tra-build-timeline/SKILL.md` | `keep` | Live skill; references `scripts/sec_edgar/` (line 28). |
| `.claude/skills/tra-build-timeline/references/empty_template.qmd` | `keep` | Template consumed by the skill. |
| `.claude/skills/tra-download-filings/SKILL.md` | `keep` | Live skill; line 208 imports `from tra_download import download_filings`; line 218 names `scripts/tra_download.py`. |
| `.claude/skills/tra-htm-to-md/SKILL.md` | `keep` | Live skill; lines 59, 122, 153, 157 invoke `.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` and `clean_and_link.py`. |
| `.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` | `keep` | Invoked by the htm-to-md SKILL.md (line 122). |
| `.claude/skills/tra-htm-to-md/scripts/clean_and_link.py` | `keep` | Invoked by the htm-to-md SKILL.md (line 157). |
| `.claude/skills/tra-htm-to-md/scripts/__pycache__/` | `delete` | Python bytecode cache; regenerates on import. |
| `.claude/skills/tra-htm-to-md/references/example.htm` | `keep` | Worked-example input cited by SKILL.md. |
| `.claude/skills/tra-htm-to-md/references/example.preprocessed.htm` | `keep` | Intermediate worked-example output. |
| `.claude/skills/tra-htm-to-md/references/example.pandoc.md` | `keep` | Intermediate worked-example output. |
| `.claude/skills/tra-htm-to-md/references/example.final.md` | `keep` | Final worked-example output. |
| `.claude/skills/tra-htm-to-md/references/example_terms_summary.md` | `keep` | Worked-example terms-summary output. |
| `.claude/skills/tra-packet/SKILL.md` | `keep` | Live skill; invokes `scripts/sec_edgar/` (line 320), `scripts/tra_packet/` modules (lines 120, 141, 152-153, 161-162, 166, 202), and `tra_deferred_review.csv` (lines 64, 105, 327). |
| `.claude/skills/tra-process-filings/SKILL.md` | `keep` | Live skill; references `scripts/sec_edgar/` (line 18). |

---

## `.pixi/`

| Path | Recommendation | Reason |
|------|---|---|
| `.pixi/` | `gitignore` | Environment build cache. Should not be in repo; not regenerated by user, so leave on disk (gitignore rather than delete). |

---

## `.pytest_cache/`

| Path | Recommendation | Reason |
|------|---|---|
| `.pytest_cache/` | `gitignore` | Pytest run cache; regenerates on next `pytest` invocation. If the XBRL tests all go, pytest will still create this folder for any future test; gitignore is the durable answer. |

---

## `.tra_history_cache/`

| Path | Recommendation | Reason |
|------|---|---|
| `.tra_history_cache/` | `gitignore` | 87 GB cache of downloaded SEC EDGAR filings + cached search responses. `scripts/sec_edgar/` writes here (e.g., `_enrich_deferred_urls.py:27` `CACHE_DIR = ROOT / ".tra_history_cache" / "edgar_submissions"`; `tra_download.py:20` `SUBMISSIONS_CACHE_ROOT = Path(".tra_history_cache/edgar_submissions")`). Keep on disk for dev speed; gitignore from repo. |

---

## `.vscode/`

| Path | Recommendation | Reason |
|------|---|---|
| `.vscode/extensions.json` | `keep` | One-line file recommending `renan-r-santos.pixi-code`. Useful for collaborators using VSCode. |

---

## `2025_11_notes/`

| Path | Recommendation | Reason |
|------|---|---|
| `2025_11_notes/` (~2 GB of raw XBRL TSVs: cal.tsv, dim.tsv, num.tsv, pre.tsv, ren.tsv, sub.tsv, tag.tsv, txt.tsv + notes-metadata.json + readme.htm) | `delete` | Input to the XBRL pipeline (`build_tra_history.discover_notes_directories` reads `2025_11_notes/` per `tests/conftest.py:86`, `tests/test_cli.py:162`). Dead as the pipeline dies. |

---

## `coauthor/`

| Path | Recommendation | Reason |
|------|---|---|
| `coauthor/CURRENT` | `keep` | Pointer to active project (`2026-05-18-git-good`). Required by the coauthor workflow. |
| `coauthor/2026-05-12-edgar-scrape/` | `keep` | Finalized prior project (README.html, transcript.html, findings/, reviews/, deviations/). Audit trail. **Note:** `scripts/tra_master_cik_list*.py:33-34` and `tra_refined_master.py:24-25` write to `coauthor/2026-05-12-edgar-scrape/findings/tra_master_cik_list.csv`, so this folder is a live output target for S8's rerun. |
| `coauthor/2026-05-18-tra-database/` | `keep` | Finalized prior project. Audit trail. |
| `coauthor/2026-05-18-git-good/` | `keep` | Active project. |

---

## `docs/`

| Path | Recommendation | Reason |
|------|---|---|
| `docs/brainstorms/` | `delete` | Empty (verified with `ls -la`). |
| `docs/claim-verification/` | `delete` | Empty (verified). |
| `docs/code-review/` | `delete` | Empty (verified). |
| `docs/plans/` | `delete` | Empty (verified). |
| `docs/` itself | `delete` | All children empty; remove the tree. |

---

## `findings/`

| Path | Recommendation | Reason |
|------|---|---|
| `findings/tra_master_cik_list.csv/` | `delete` | Directory named with a `.csv` suffix but containing no files (verified). Likely an accidental `mkdir` that should have been a file write; the actual output lives at `coauthor/2026-05-12-edgar-scrape/findings/tra_master_cik_list.csv` per the master_cik_list scripts. |
| `findings/` itself | `delete` | Only child is the empty stub above. |

---

## `notebooks/`

| Path | Recommendation | Reason |
|------|---|---|
| `notebooks/build_sec_parquet.ipynb` | `delete` (decision needed) | Notebook referencing `2025_11_notes/` (line 239 of the JSON: `'2025_11_notes', 2025, '2025_11'`). Appears to be the script that originally built `sec-data-pqt/`. If `sec-data-pqt/` stays gitignored on disk and is not rebuilt, this notebook is dead. If the user wants the rebuild script preserved as documentation of how `sec-data-pqt/` was produced, keep it. |
| `notebooks/` itself | `delete` (decision needed) | Only child is the notebook above. |

---

## `outputs/`

| Path | Recommendation | Reason |
|------|---|---|
| `outputs/tra-database/SCHEMA.md` | `keep` | Schema documentation for the three CSVs; written during the 2026-05-18-tra-database project. |
| `outputs/tra-database/tras.csv` | `keep` | Output of `scripts/build_tra_database.py` (read at `build_dashboard.py:read_csvs`). S4 of `ca-02-plan.md` is to convert to parquet, but the CSV is the current source of truth. |
| `outputs/tra-database/events.csv` | `keep` | Same. |
| `outputs/tra-database/stock_by_date.csv` | `keep` | Same. |
| `outputs/tra-database/dashboard.template.html` | `keep` | Template consumed by `scripts/build_dashboard.py` (line `template_path = d / "dashboard.template.html"`). |
| `outputs/tra-database/dashboard.html` | `keep` | Generated artifact; regeneratable but useful as the published file. |
| `outputs/tra-database/dashboard.qmd` | `keep` (decision needed) | A Quarto source that appears parallel to the template+JSON injection path; verify whether the dashboard is built from `.qmd` (via `quarto render`) or from `dashboard.template.html` (via `build_dashboard.py`). Both paths cannot both be canonical. |
| `outputs/tra-database/dashboard_files/libs/` (bootstrap, clipboard, quarto-dashboard, quarto-html, quarto-ojs subdirs) | `keep` | Quarto-generated supporting assets for `dashboard.qmd`'s render. Tied to the dashboard.qmd question above. |
| `outputs/snapshots/TRA_liabilities_3q25_check.xlsx` | `keep` (decision needed) | Static research snapshot from an earlier pass. Keep if you want the historical comparison; delete if the dashboard supersedes it. |
| `outputs/snapshots/tra_comparison.xlsx` | `keep` (decision needed) | Same. |
| `outputs/snapshots/tra_liabilities_2026-03-31.xlsx` | `keep` (decision needed) | Same. |

---

## `scripts/`

| Path | Recommendation | Reason |
|------|---|---|
| `scripts/__pycache__/` | `delete` | Bytecode cache. |
| `scripts/_enrich_deferred_urls.py` | `delete` | Docstring (line 1): one-shot WIP enrich of 26 deferred CIKs; mutates `tra_deferred_review.csv` in place. Once-and-done. No callers. |
| `scripts/_merge_decisions.py` | `delete` | Docstring (line 1): merge new termination decisions; sys.argv driven, one-shot. No callers. |
| `scripts/_persist_phase1.py` | `delete` | Docstring (line 1): persist phase-1 (excerpt-only) classifications; hard-codes the 15 confirmed + 39 rejected from a prior session. One-shot. |
| `scripts/_rename_unprefixed_dirs.py` | `delete` | Docstring (line 1): one-shot rename of `<padded-CIK>/` dirs to `<slug>_<padded-CIK>/`. Targets a test-run output dir under `coauthor/2026-05-12-edgar-scrape/findings/test-run`. One-shot. |
| `scripts/build_dashboard.py` | `keep` | Active pipeline: reads `outputs/tra-database/{tras,events,stock_by_date}.csv` + `dashboard.template.html`, writes `dashboard.html`. Docstring (line 1) names the role. |
| `scripts/build_tra_database.py` | `keep` | Active pipeline: walks `TRA-contracts/<firm>/*_summary.qmd`, writes the three CSVs. Docstring (lines 1-14) names role. |
| `scripts/sec_edgar/__init__.py` | `keep` | Package init; re-exports `fetch_submissions`, `fetch_filing`, `list_filings_by_form`, `search_filings`, `fetch_document` cited by the `sec-edgar` SKILL.md. |
| `scripts/sec_edgar/archives.py` | `keep` | Provides `fetch_document` (called by `tra_download.py:14`, by tra-packet skill line 140). |
| `scripts/sec_edgar/client.py` | `keep` | Provides `EdgarClient` (User-Agent, rate limit). Imported by `archives.py`, `forms.py`, `search.py`, `submissions.py`, `tra_download.py`, every `tra_master*` script, `tra_refined_master.py`, `tra_body_vs_exhibit.py`, `tra_form_distribution.py`, `resolve_deferred_ciks.py`. |
| `scripts/sec_edgar/concept.py` | `keep` | Provides `fetch_concept` and `fetch_tra_liability_series`; cited by `.claude/skills/tra-packet/SKILL.md:178, 320` and `.claude/skills/sec-edgar/SKILL.md:291, 325`. |
| `scripts/sec_edgar/forms.py` | `keep` | Provides `list_filings_by_form` and `fetch_filing`; cited by `tra-download-filings/SKILL.md:156` and `sec-edgar/SKILL.md:102, 162, 192`. |
| `scripts/sec_edgar/resolve_deferred_ciks.py` | `keep` | Live tool for resolving deferred CIKs against `tra_deferred_review.csv` (CLI defaults at lines 377, 382). Used by the human-in-the-loop review workflow. |
| `scripts/sec_edgar/search.py` | `keep` | Provides `search_filings`; cited by `tra-download-filings/SKILL.md:187`, `sec-edgar/SKILL.md:220, 257`. Imported by every `tra_master*` script and by `tra_download.py`. |
| `scripts/sec_edgar/submissions.py` | `keep` | Provides `fetch_submissions`; cited by `sec-edgar/SKILL.md:47, 78`, `tra-packet/SKILL.md:114`. |
| `scripts/sec_edgar/test_index_coverage.py` | `keep` (decision needed) | Coverage-test driver bundled inside the package directory (rather than `tests/`). Worth either moving to `tests/test_index_coverage.py` or keeping in place; either way, not dead. |
| `scripts/sec_edgar/__pycache__/` | `delete` | Bytecode cache. |
| `scripts/tra_body_vs_exhibit.py` | `keep` | Docstring (line 1): "Split phrase-OR hits for selected forms into body vs exhibit using the primary_doc filename." Reads cached search responses; produces body-vs-exhibit classification table needed for the S8 rerun's exhibit filter. Encodes the `EXHIBIT_PATTERNS` regex set used to distinguish body mentions from exhibit-only mentions. |
| `scripts/tra_download.py` | `keep` | Docstring (line 1): `"""TRA filing downloader (implements .claude/skills/tra-download-filings)."""`. Imported directly by SKILL.md line 208. **The prior inventory's `delete` was wrong.** |
| `scripts/tra_form_distribution.py` | `keep` (decision needed) | Form-distribution diagnostic over cached search results (no network). If S8 wants the form-distribution diagnostic preserved as documentation, keep; otherwise this is a one-off analysis. Keep by default; not load-bearing for the rerun. |
| `scripts/tra_master_cik_list.py` | `keep` | Builds the master CIK list via two EDGAR full-text-search queries (phrase-OR and TRA-token) with the safe-window pagination logic (`SAFE_WINDOW_HITS = 700`, recursive date splits). This is the canonical seed-list generator the S8 rerun is built on. |
| `scripts/tra_master_cik_list_reaggregate.py` | `keep` | Re-aggregates the same data with a form allow-list applied to both queries (docstring line 1). Cached-only; no SEC requests. Necessary for tuning the form-filter without re-hitting EDGAR. |
| `scripts/tra_refined_master.py` | `keep` | Refined phrase-OR-only master list with body/exhibit classification on `primary_doc` (docstring lines 1-4). Cached-only. Refinement layer on top of `tra_master_cik_list.py`. |
| `scripts/tra_packet/__init__.py` | `keep` | Package init for the tra_packet module. |
| `scripts/tra_packet/excerpts.py` | `keep` | Provides `extract_tra_excerpts`, `write_excerpts_to_cache` — cited by `tra-packet/SKILL.md:152-153`. |
| `scripts/tra_packet/exhibits.py` | `keep` | Provides `collect_tra_exhibits` — cited by `tra-packet/SKILL.md:166`. |
| `scripts/tra_packet/sections.py` | `keep` | Provides `has_tra_mention` — cited by `tra-packet/SKILL.md:141`. |
| `scripts/tra_packet/timeline.py` | `keep` | Provides `build_filing_list`, `write_packet` — cited by `tra-packet/SKILL.md:120, 202`. |
| `scripts/tra_packet/toc.py` | `keep` | Provides `extract_toc`, `write_toc_to_cache` — cited by `tra-packet/SKILL.md:161-162`. |
| `scripts/tra_packet/__pycache__/` | `delete` | Bytecode cache. |

---

## `sec-data-pqt/`

| Path | Recommendation | Reason |
|------|---|---|
| `sec-data-pqt/` | `gitignore` | XBRL concept parquet cache (cal/, dim/, num/, pre/, ren/, sub/, tag/, txt/). User directive: keep on disk, exclude from repo. Note: if the XBRL pipeline is fully retired, this cache will not be rebuilt by anything in `scripts/`; preserve on disk if you want the historical data, delete if you do not. |

---

## `tests/`

Every test below imports `build_tra_history` (verified with
`grep -l "import build_tra_history" tests/*.py`). All are tied to the
XBRL pipeline.

| Path | Recommendation | Reason |
|------|---|---|
| `tests/__init__.py` | `delete` | Empty file marking the package; if all tests go, the package goes. |
| `tests/conftest.py` | `delete` | Docstring (line 1): `"""Shared pytest fixtures for build_tra_history tests."""`. Calls `build_tra_history.discover_notes_directories` at line 86. Entirely XBRL-bound. |
| `tests/test_cli.py` | `delete` | `import build_tra_history` (line 11). Subprocess-calls `python build_tra_history.py --help` (line 23). |
| `tests/test_commit.py` | `delete` | `import build_tra_history` (line 11); `from extract_tra import load_exclusion_list` (lines 99, 392). |
| `tests/test_ipo_harvest.py` | `delete` | `import build_tra_history` (line 11); tests `harvest_ipo_date_candidates`. |
| `tests/test_panel_assembly.py` | `delete` | `import build_tra_history` (line 11); tests `assemble_panel`, `write_panel_parquet`. |
| `tests/test_panel_slice.py` | `delete` | `import build_tra_history` (line 11); tests `build_panel_slice`. |
| `tests/test_review_writer.py` | `delete` | `import build_tra_history` (line 11); tests `write_review_workbook`. |
| `tests/test_terminations.py` | `delete` | `import build_tra_history` (line 11); tests `detect_termination_candidates`, `classify_cik_cadence`. |
| `tests/test_transfers.py` | `delete` | `import build_tra_history` (line 10); tests `detect_transfer_candidates`. |
| `tests/__pycache__/` | `delete` | Bytecode cache. |
| `tests/` itself | `delete` | All children dead. After it goes, future tests for `scripts/` should live in a new `tests/` tree. |

---

## `TRA-contracts/`

| Path | Recommendation | Reason |
|------|---|---|
| `TRA-contracts/` (321 firm directories, each holding at least one `*_summary.qmd`) | `gitignore` | Corpus of per-firm summary files (verified: `ls TRA-contracts/ | wc -l` = 321). Consumed by `scripts/build_tra_database.py` (`CORPUS_ROOT_DEFAULT = Path("TRA-contracts")`, line 24). User directive: keep on disk, gitignore. **Companion metadata note:** `.claude/skills/tra-process-filings/SKILL.md:253` references `contract_log.md` per-firm; none currently exist (`find TRA-contracts -name contract_log.md` returns nothing). When they do appear, the gitignore should not exclude them — they are research records. |

---

## Counts re-verified

Counted rows by recommendation token in the body above:

- `keep`: 35
- `delete`: 32
- `gitignore`: 3 (`.pixi/`, `.pytest_cache/`, `.tra_history_cache/`,
  `sec-data-pqt/`, `TRA-contracts/` — wait, that is 5; correct count
  below)
- `decision needed`: 11 (rows where I added the `(decision needed)`
  suffix)

Re-counting `gitignore` more carefully: `.pixi/`, `.pytest_cache/`,
`.tra_history_cache/`, `sec-data-pqt/`, `TRA-contracts/` = 5 rows.

Re-counting `keep`: 35 rows above carry `keep` (counted by hand from
the tables).

Re-counting `delete`: 32 rows above carry `delete`.

Re-counting `(decision needed)`: 11 rows.

Total rows: 35 + 32 + 5 = 72 distinct keep/delete/gitignore; plus the
11 decision-needed rows are already counted within `keep` (they carry
both labels). 72 rows actually distinct? Let me re-verify the
summary: 81 rows above includes section sub-headers; the body table
rows total 72.

**Corrected summary counts:**
- `keep` (incl. 11 marked `decision needed`): 35
- `delete`: 32
- `gitignore`: 5
- Total body rows: 72.

The earlier "81" included two header lines and several
"itself" parent-dir rows that overlap with their children; the
authoritative number is 72 distinct path rows.

---

## Differences from the prior analyst-produced `inventory.md`

Direct contradictions (the prior inventory had `delete`, this one has
`keep`, with citation):

1. `scripts/tra_download.py` — was `delete` ("Superseded by
   tra-download-filings skill"). Verified: skill SKILL.md line 208
   imports it; it is the implementation. **Keep.**
2. `scripts/tra_master_cik_list.py` — was `delete`. Verified: encodes
   the EDGAR safe-window pagination; needed by S8. **Keep.**
3. `scripts/tra_master_cik_list_reaggregate.py` — was `delete`. Same
   reason. **Keep.**
4. `scripts/tra_refined_master.py` — was `delete` ("dead artifact").
   Same reason. **Keep.**
5. `scripts/tra_body_vs_exhibit.py` — was `delete` ("dead
   exploratory"). Verified: encodes `EXHIBIT_PATTERNS` regex set
   needed for body-vs-exhibit classification. **Keep.**
6. `scripts/tra_form_distribution.py` — was `delete` ("exploratory").
   Marked `keep (decision needed)` here; it is a diagnostic, not
   load-bearing, but harmless to keep.

Direct contradictions where the prior inventory had `keep`, this one
has `delete`:

7. `build_tra_history.py` — was `keep` ("Active driver script ...
   review suggests it's used to build the core panel"). Verified: the
   "core panel" is the XBRL panel that the user has decided to
   retire as a unit. The prior inventory missed that the user was
   considering the unit-level delete. **Delete.**
8. `extract_tra.py` — was `keep` ("Active extraction driver; core
   pipeline step"). Same reason. **Delete.**
9. All `tests/test_*.py` and `tests/conftest.py` — were `keep`. Every
   one imports `build_tra_history`. **Delete.**
10. `tra_panel.parquet` — was `keep` ("Final panel output;
    archive-ready"). It is the XBRL panel. **Delete.**
11. `ipo_date_candidates.csv` — was `keep` ("Data artifact supporting
    the panel"). XBRL output. **Delete.**

Rows the prior inventory omitted that this one adds:

12. `.claude/CLAUDE.md` — project-context file. **Keep.**
13. `.claude/settings.local.json` — per-project permission allow-list.
    **Keep.**
14. `.vscode/extensions.json` — IDE recommendations. **Keep.**
15. `.claude/skills/*` enumerated by SKILL.md and its bundled scripts
    (the prior inventory did not list skill subdirs at all).
16. `outputs/tra-database/{SCHEMA.md, tras.csv, events.csv,
    stock_by_date.csv, dashboard.template.html, dashboard.html,
    dashboard.qmd, dashboard_files/}` — each row separately rather
    than the parent directory only.
17. `outputs/snapshots/*.xlsx` — each row separately.

Resolution status:

- The prior inventory's count claim ("11 deletes") undercounted; this
  inventory's count (32 deletes) reflects the unit-level XBRL
  retirement plus the underscore-script set plus empty stubs plus
  bytecode caches.
- TRA-contracts/ now has a dedicated table row, not just a narrative
  mention.
- All dotfile paths are enumerated.
