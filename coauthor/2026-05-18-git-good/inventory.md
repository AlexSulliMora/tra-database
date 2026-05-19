---
project_id: 2026-05-18-git-good
analyst: inventory analysis pass
created: 2026-05-19
---

# Inventory: Keep / Delete / Move / Gitignore Analysis

## Summary

**Paths inspected:** 28 top-level entries + nested structure across
coauthor/, scripts/, outputs/, TRA-contracts/.

**Recommendation counts:** - `keep`: 13 - `gitignore`: 3
(TRA-contracts/, .tra_history_cache/, sec-data-pqt/) - `delete`: 11 -
`move`: 3 - `decision needed`: 0 (user resolved 2025_11_notes/ to delete
on 2026-05-19)

------------------------------------------------------------------------

## Root-level files

| Path | Recommendation | Reason |
|------------------------|-----------------|-------------------------------|
| `pixi.toml` | `keep` | Environment lock file; essential for reproducibility |
| `pixi.lock` | `keep` | Dependency lock file; essential for reproducibility |
| `build_tra_history.py` | `delete` | Active driver script in the pipeline; referenced in ca-01-scope as part of prior work; review suggests it's used to build the core panel |
| `extract_tra.py` | `delete` | Active extraction driver; core pipeline step; keep |
| `ipo_date_candidates.csv` | `delete` | Data artifact supporting the panel; annotation source |
| `tra_deferred_review.csv` | `delete` | Deferred-CIK review log; research artifact; keep for traceability |
| `tra_events_review.xlsx` | `delete` | Decision log for TRA event classification; critical annotation record |
| `tra_review_status.csv` | `delete` | Status tracking for TRA corpus; keep for traceability |
| `tra_panel.parquet` | `delete` | Final panel output; archive-ready deliverable |

------------------------------------------------------------------------

## Directories

### `.claude/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `.claude/` | `keep` | Project-local CLAUDE.md and coauthor archived-project pointers; essential project metadata |
| `.claude/coauthor/` | `delete` | Archived project metadata (2026-05-12-edgar-scrape.md, 2026-05-18-tra-database.md); user resolved 2026-05-19 that prior project context is no longer needed at the project root. |

### `.pixi/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `.pixi/` | `gitignore` | Build artifact directory; regenerates on `pixi install`; safe to remove |

### `.pytest_cache/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `.pytest_cache/` | `delete` | Test artifact cache; regenerates on `pytest run`; safe to remove |

### `.tra_history_cache/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `.tra_history_cache/` | `gitignore` | 87 GB cache of downloaded SEC EDGAR filing archives (85k files); keep on disk for development speed but exclude from repo |

### `.vscode/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `.vscode/` | `delete` | VSCode workspace config (extensions.json); useful for collaboration |

### `2025_11_notes/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `2025_11_notes/` | `delete` | Raw XBRL bulk feeds (\~2 GB); exploratory data dump, no scripts reference it. User resolved 2026-05-19. |

### `coauthor/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `coauthor/CURRENT` | `keep` | Coauthor workflow state marker; active project pointer |
| `coauthor/2026-05-12-edgar-scrape/` | `keep` | Archived coauthor project; prior research project; keep for audit trail and reference |
| `coauthor/2026-05-18-tra-database/` | `keep` | Archived coauthor project; finalized database build; keep for audit trail and reference |
| `coauthor/2026-05-18-git-good/` | `keep` | Current active coauthor project; keep |

### `docs/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `docs/` | `delete` | Empty directory tree (no files under brainstorms/, claim-verification/, code-review/, plans/); cleanup artifact from prior work |

### `findings/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `findings/` | `delete` | Empty directory tree; cleanup artifact (tra_master_cik_list.csv/ is an empty subdirectory) |

### `notebooks/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `notebooks/build_sec_parquet.ipynb` | `keep` | user add: is used to compile `sec-data-pqt/` I will manually move it elsewhere |

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `outputs/tra-database/` | `keep` | Core output directory; holds SCHEMA.md, dashboard.template.html, dashboard.html, and .csv outputs (to be converted to .parquet in S4) |
| `outputs/snapshots/` | `delete` | Archived analysis snapshots (TRA_liabilities, tra_comparison); research artifacts; keep for traceability |

### `scripts/`

Core pipeline scripts: **keep** all

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `scripts/build_tra_database.py` | `keep` | Core pipeline step: aggregates TRA-contracts/ into unified events/tras/stock_by_date tables |
| `scripts/build_dashboard.py` | `keep` | Core pipeline step: renders dashboard.html from aggregated tables |
| `scripts/sec_edgar/` | `keep` | EDGAR API client module; used by tra-download-filings skill |
| `scripts/tra_packet/` | `keep` | TRA-packet evidence-assembly module; shipped as part of the skill; keep |

Dead/exploratory scripts: **delete**

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `scripts/__pycache__/` | `delete` | Python build cache; regenerates on import; safe to remove |
| `scripts/_enrich_deferred_urls.py` | `delete` | One-shot WIP script (underscore-prefixed); enriched 26 deferred CIKs in exploratory phase; not part of reproducible pipeline |
| `scripts/_merge_decisions.py` | `delete` | One-shot WIP script (underscore-prefixed); merged prior decisions during exploratory phase; not part of reproducible pipeline |
| `scripts/_persist_phase1.py` | `delete` | One-shot WIP script (underscore-prefixed); persisted phase-1 state; exploratory artifact |
| `scripts/_rename_unprefixed_dirs.py` | `delete` | One-shot WIP script (underscore-prefixed); migration helper from prior layout; one-time use only |
| `scripts/sec_edgar/resolve_deferred_ciks.py` | `delete` | Defaults to the deleted `tra_deferred_review.csv` at lines 377, 382; broken on default invocation. User authorized deletion 2026-05-19 (queued as task #141 during inventory review). |
| `scripts/tra_body_vs_exhibit.py` | `keep` | user note: unsure, keep for now and then figure it out |
| `scripts/tra_download.py` | `keep` | user note: need to figure out if this or the skill takes precedence |
| `scripts/tra_form_distribution.py` | `keep` | user note: just want to be safe, analyst who said to delete very clearly does not understand what this is |
| `scripts/tra_master_cik_list.py` | `keep` | user note: just want to be safe, analyst who said to delete very clearly does not understand what this is |
| `scripts/tra_master_cik_list_reaggregate.py` | `keep` | user note: just want to be safe, analyst who said to delete very clearly does not understand what this is |
| `scripts/tra_refined_master.py` | `keep` | user note: just want to be safe, analyst who said to delete very clearly does not understand what this is |

### `sec-data-pqt/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `sec-data-pqt/` | `gitignore` | 18 GB parquet index of SEC XBRL concepts (cal/, dim/, num/, pre/, ren/, sub/, tag/, txt/); cache for EDGAR queries; keep on disk for development but exclude from repo |

### `tests/`

| Path | Recommendation | Reason |
|-----------------------------------|-------------------|-------------------|
| `tests/` | `delete` | Entire directory removed; all XBRL-pipeline test modules died with the XBRL pipeline. (User clarified 2026-05-19 that `tests/__init__.py` left behind in the initial pass should have gone with the rest.) |

------------------------------------------------------------------------

## Rationale for keep/delete decisions

**Keep:** Root environment files (pixi), core pipeline scripts
(build_tra_database, build_dashboard), EDGAR API client (sec_edgar),
TRA-packet evidence module (tra_packet), all tests, coauthor project
tree (audit trail), outputs (parcels), review CSVs/XLSXs (decision
traceability).

**Delete:** Build caches (.pixi, .pytest_cache), one-shot exploratory
scripts (underscore-prefixed *.py, tra\_*\_distribution, tra\*\_master),
dead script copies (tra_download.py will be moved from
skills/tra-download-filings), and empty directory stubs (docs/,
findings/). These are artifacts of the exploratory first pass that do
not belong in a clean repository.

**Gitignore:** Two large caches: `.tra_history_cache/` (87 GB of
downloaded EDGAR filings; regenerable via the pipeline) and
`sec-data-pqt/` (18 GB of XBRL concept parquets; cacheable but not core
to reproducibility). TRA-contracts/ is also gitignored (the corpus
itself: 321 firm directories, regenerable from the pipeline). All three
remain on disk but do not enter the repository.

**Decision needed:** `2025_11_notes/` (\~2 GB raw XBRL bulk TSV files)
appears to be exploratory work; user should decide whether to keep or
delete.

------------------------------------------------------------------------

## Notes on TRA-contracts/ and companion metadata

The plan mentions protecting companion metadata files (contract_log.md,
filing_notes.md, \*\_summary.qmd) inside TRA-contracts/<firm>/. Current
inventory shows: - All 321 firm directories contain at least one
per-firm \*\_summary.qmd file. - No contract_log.md or filing_notes.md
files exist yet (these are anticipated but not yet created). -
Therefore, no metadata protection is needed; all per-firm files are safe
assets that should not be deleted even if TRA-contracts/ is gitignored.