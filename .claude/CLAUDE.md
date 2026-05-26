# tra project context

Build a structured database of every Tax Receivable Agreement disclosed on
EDGAR, the public companies that pertain to each one, and human-readable
timelines at both the firm level and the per-TRA level.

## Key references

- `docs/workflow-goal.qmd` — end-to-end pipeline (five phases from EDGAR
  discovery to structured database).
- `docs/tra-background.md` — TRA subject-matter reference (what a TRA is,
  title patterns, anatomy, defining terminology, termination rules).

## Environment

Python managed by pixi. Run via `pixi run python ...` or `pixi run -- <cmd>`.
The `pixi.toml` and `pixi.lock` live at the project root.

## Conventions

- **Hyphens vs underscores.** Underscores only for Python-parsed names
  (modules, functions, variables). Hyphens everywhere else (filenames, YAML
  keys, enum values, CLI flags).
- **Render verification.** `quarto render` does not verify browser-rendered
  content (mermaid, KaTeX). Use `pixi run python scripts/render_html.py
  <file.html>` to generate a PNG and verify visually before claiming a
  rendered deliverable is ready.

## Skills

Local skills under `.claude/skills/`:

- `sec-edgar` — SEC EDGAR API client (rate-limited, cache-aware).
- `tra-download-filings` — download TRA-relevant filings per CIK.
- `tra-process-filings` — classify TRA contracts within a firm directory.
- `tra-build-timeline` — write per-firm TRA summary files.
- `tra-htm-to-md` — convert TRA HTML to clean markdown.

The pipeline architecture is in transition toward a per-firm narrative model
(see `docs/workflow-goal.qmd`). Several of the skills above will be
refactored or replaced as that architecture lands.
