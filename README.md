# tra

A reproducible build of a corpus of Tax Receivable Agreements (TRAs) from public SEC filings, plus an interactive dashboard summarizing the corpus.

A TRA is a contract, typically executed at IPO or as part of a SPAC business combination, under which a public company (PubCo) agrees to pay a share (commonly 85 percent) of its future cash tax savings from specific tax assets (basis step-ups, net operating losses, Section 743(b) and Section 704(c) attributes) back to pre-transaction holders of the operating LLC. This repository builds a structured database of every TRA the pipeline identifies in EDGAR, along with a timeline of TRA-affecting events (amendments, terminations, assignments, change-of-control payments) and an active-as-of-date count by category.

The end product is three Parquet files plus a self-contained HTML dashboard:

- `outputs/tra-database/tras.parquet` (one row per TRA),
- `outputs/tra-database/events.parquet` (one row per timeline event),
- `outputs/tra-database/stock_by_date.parquet` (active-TRA counts by month and category),
- `outputs/tra-database/dashboard.html` (opens in any browser from `file://`).

The corpus itself, the per-firm `TRA-contracts/<firm>/` directories with raw filings and intermediate summaries, is regenerable from EDGAR and stays out of the repository (see `.gitignore`).

## Workflow

The pipeline runs in seven steps. Steps 1 through 5 build the per-firm corpus under `TRA-contracts/`; steps 6 and 7 aggregate the corpus into the Parquet outputs and the dashboard. A fresh checkout has no `TRA-contracts/` directory: step 2 populates it.

1. **Collect a CIK seed list.** Produce a list of candidate firms by CIK (the SEC's 10-digit Central Index Key). The current corpus was built from an ad-hoc list assembled by hand; the systematic build uses the `sec-edgar` skill to query EDGAR full-text search for the phrase "tax receivable agreement" and collect filer CIKs from the matching filings. The list is consumed as input to step 2.

2. **Download TRA-relevant filings.** Run the `tra-download-filings` skill against the CIK list. For each CIK, the skill queries EDGAR for the relevant form types (10-K, 10-Q, 8-K, S-1, S-4, prospectus variants, proxy) and downloads each matching document into `TRA-contracts/<firm-slug>_<10-digit-CIK>/`. This is the one step that must run alone: concurrent SEC queries from multiple agents would breach the 10 requests-per-second rate cap.

3. **Process filings.** Run the `tra-process-filings` skill against each per-firm directory. The skill reads each downloaded filing, identifies TRA contracts, classifies them as original / amendment / termination, deduplicates contracts that appear across multiple filings, and writes a per-firm `contract_log.md` plus per-filing annotation files.

4. **Build per-firm timelines.** Run the `tra-build-timeline` skill against each processed firm directory. The skill writes a `<firm>_summary.qmd` (one per TRA at the firm) carrying YAML frontmatter (status, dates, tax-asset type, sharing ratio, companies, CIKs, role, trigger-event tags) and an event-grouped `## TRA Timeline` section. These `*_summary.qmd` files are the load-bearing input to step 6.

5. **Convert HTML to markdown.** Run the `tra-htm-to-md` skill against each per-firm directory. The skill produces a clean `.md` companion for each downloaded `.htm` exhibit via a pandoc first pass and an LLM cleanup pass that strips recurring SEC HTML artifacts. The HTML files remain in place as the canonical source.

6. **Build the database.** Aggregate the per-firm `*_summary.qmd` files into the three Parquet outputs:

   ```bash
   pixi run -- python scripts/build_tra_database.py
   ```

   The script reads each summary's YAML frontmatter and its timeline bullets, derives a stable `tra_id`, joins multi-valued fields with `|`, and writes `tras.parquet`, `events.parquet`, and `stock_by_date.parquet` into `outputs/tra-database/`.

7. **Build the dashboard.** Render the self-contained HTML dashboard from the three Parquet files:

   ```bash
   pixi run -- python scripts/build_dashboard.py
   ```

   The script reads `outputs/tra-database/*.parquet`, substitutes the data into `outputs/tra-database/dashboard.template.html`, and writes `outputs/tra-database/dashboard.html`. The output is portable: it loads Vega-Lite from a CDN and otherwise carries all data inline, so it opens with `file://` in any modern browser.

Steps 2 through 5 are skill invocations rather than scripts. The skills live under `.claude/skills/` (see the [Skill catalog](#skill-catalog) below) and load automatically when Claude Code is launched from the project root.

## Environment

Python dependencies are managed with [pixi](https://pixi.sh/). The pixi manifest at `~/research/pixi.toml` covers the full environment used by every sub-project under `~/research/`, including this one; running `pixi install` from the `tra/` project root resolves the manifest by walking up to the parent.

```bash
# from the project root
pixi install
```

After install, run any Python command through `pixi run`:

```bash
pixi run -- python scripts/build_tra_database.py
pixi run -- python scripts/build_dashboard.py
```

The `pixi run --` prefix activates the shared environment for one command without modifying the shell. Do not invoke bare `python` or `pip` against this project; the environment must be pixi-resolved for the `polars`, `pyarrow`, and `httpx` versions to match what the scripts expect.

The `sec_edgar` package under `scripts/sec_edgar/` is the EDGAR client used by the download skill. Importing it requires prepending `scripts/` to `PYTHONPATH`:

```bash
PYTHONPATH=scripts pixi run python -c "from sec_edgar import fetch_filing"
```

The skills handle the `PYTHONPATH` plumbing themselves; the line above is only relevant when calling the package directly from a script.

## Outputs

All build outputs land under `outputs/tra-database/`:

| File | Description |
|---|---|
| `tras.parquet` | One row per TRA (360 rows in the current corpus). |
| `events.parquet` | One row per timeline bullet across all TRAs (1635 rows). |
| `stock_by_date.parquet` | One row per (month, dimension, category) showing how many TRAs were active at each month-start (8415 rows). |
| `dashboard.html` | Self-contained interactive dashboard (~1.8 MB). |
| `dashboard.template.html` | Source template the dashboard build substitutes into. |
| `SCHEMA.md` | Column-level documentation for the three Parquet files. |

The per-firm corpus that feeds the build lives under `TRA-contracts/<firm-slug>_<10-digit-CIK>/`. Each firm directory carries the downloaded filings (`.htm`), their markdown companions (`.md`), per-filing annotation files, a `contract_log.md`, and one `*_summary.qmd` per TRA at the firm. This directory is excluded from the repository via `.gitignore` and is regenerated by steps 2 through 5 of the workflow.

## Schema

Column-level documentation for `tras.parquet`, `events.parquet`, and `stock_by_date.parquet`, including the active-as-of-date rule and the dashboard's status semantics, lives in [`outputs/tra-database/SCHEMA.md`](outputs/tra-database/SCHEMA.md).

## Skill catalog

The pipeline's per-firm and per-filing work is carried out by six Claude Code skills that live under `.claude/skills/` and load automatically when Claude Code is launched from the project root.

| Skill | One-line description |
|---|---|
| `sec-edgar` | Fetch SEC EDGAR filings (HTML, XML, JSON, PDF) by CIK, accession number, form type, or date range with rate-limited and cache-aware access; building block for downloading and refreshing. |
| `tra-download-filings` | Given a list of CIKs, download every TRA-relevant SEC filing (10-K, 10-Q, 8-K, S-1, S-4, prospectus variants, proxy) into a per-firm directory tree. Run standalone to respect the SEC 10-requests-per-second rate cap. |
| `tra-process-filings` | For each filing in a per-firm directory, identify TRA contracts, classify them as original / amendment / termination, deduplicate across filings, and write per-filing annotations plus a `contract_log.md`. |
| `tra-build-timeline` | Per firm, write a concise `*_summary.qmd` with YAML frontmatter (status, dates, tax-asset type, sharing ratio, companies, CIKs, role, trigger-event tags), an event-grouped timeline, and a one-paragraph explanation of what happened. |
| `tra-htm-to-md` | Convert each TRA contract `.htm` file in a firm directory to a clean `.md` companion via pandoc plus an LLM cleanup pass that strips recurring SEC HTML artifacts. Optionally also writes a `terms-summary.md` capturing four contractual term definitions. |
| `tra-packet` | Assemble a per-firm evidence packet (timeline, source-cited filings, TOC of every TRA-mentioning filing) for human review of an ambiguous TRA status. Used downstream of the main pipeline for manual adjudication. |
