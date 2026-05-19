# Project context

This file is written by `/coauthor:ca-01-scope` to `<cwd>/.claude/CLAUDE.md`. Operating rules (principles, response style, banned writing patterns, workflow stages, audit-log conventions) come from the coauthor plugin's canonical `CLAUDE.md`, loaded via the canonical at `/home/sulli/research/CLAUDE.md` (in scope via Claude Code's directory walk).

## Context

- **Name:** tra
- **One-line description:** Clean up the TRA workflow directory, relocate skills into the project tree, convert outputs to parquet, write a README, push to a private GitHub repo, then re-run the corpus build systematically.
- **Slug:** 2026-05-18-git-good
- **Goal:** Turn the working TRA pipeline into a self-contained, reproducible private GitHub repo with relocated skills, parquet outputs, a documented workflow, a new EDGAR refresh skill, and a second end-to-end pass on a fresh CIK seed list.
- **Data:** Per-firm `*_summary.qmd` files under `TRA-contracts/` (321 firms, 360 TRAs); SEC EDGAR filings re-fetched during the rerun.
- **Method summary:** Sequential cleanup (skill relocation, keep/delete pass, csv→parquet, README), git init + private GitHub push, skill edits, new `tra-refresh` skill, integration rerun from a fresh CIK seed list.

The active project's artifacts live at `<cwd>/coauthor/<slug>/`. The text file `<cwd>/coauthor/CURRENT` carries the active slug; every skill resolves the project by reading it (override with `--project=<slug>`).

## Prior projects

- `2026-05-12-edgar-scrape` (2026-05-12): EDGAR scraper that collected TRA-mentioning filings into the per-firm corpus.
- `2026-05-18-tra-database` (2026-05-18): Built `tras.csv`, `events.csv`, `stock_by_date.csv`, dashboard, and `SCHEMA.md` from the per-firm `*_summary.qmd` files.
