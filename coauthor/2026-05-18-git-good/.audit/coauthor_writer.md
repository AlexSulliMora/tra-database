
## 2026-05-19T03:22:29-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **writer** for step S5 of the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Step: S5 — README

Read first:
- `coauthor/2026-05-18-git-good/ca-01-scope.md`
- `coauthor/2026-05-18-git-good/ca-02-plan.md` (S5 implementation actions + S5 review specs)
- `outputs/tra-database/SCHEMA.md` (the artifact you link to from the README)
- Each of the six SKILL.md files under `.claude/skills/` (you write one-line catalog entries from these)

## Goal

Draft `/home/sulli/research/tra/README.md` covering workflow steps and commands, pixi setup, output locations, a pointer to the schema doc, and a skill catalog. Every command you document must run without error from a fresh shell.

## Implementation actions (verbatim from ca-02-plan.md S5)

1. Read `outputs/tra-database/SCHEMA.md` to anchor the schema-pointer section.
2. Read each relocated skill's `SKILL.md` to write a one-line catalog entry per skill (`tra-download-filings`, `tra-process-filings`, `tra-build-timeline`, `tra-htm-to-md`, `tra-packet`, `sec-edgar`; the `tra-refresh` skill is added in s7 and will be inserted into the catalog at that step).
3. Draft `/home/sulli/research/tra/README.md` with four sections: Workflow (pipeline steps with exact commands), Environment (pixi setup, dependency install, how to run scripts), Outputs (where parquet files and dashboard.html land), Schema pointer (link to `outputs/tra-database/SCHEMA.md`), Skill catalog (one-line per skill).
4. Run each documented command on a clean shell to verify it actually works.

## Workflow context the writer needs

The TRA database pipeline is:

1. **Collect CIK seed list.** A list of firm CIKs that potentially have TRAs. In the first pass this was an ad-hoc list; the systematic rerun (s8) will collect this via EDGAR full-text search. For now, document the manual route.
2. **Download filings.** `tra-download-filings` skill: given a list of CIKs, downloads all TRA-relevant SEC filings (10-K, 10-Q, 8-K, S-1, S-4, prospectus variants, proxy) to a local directory tree. Output: `TRA-contracts/<firm>/` with raw HTM filings.
3. **Process filings.** `tra-process-filings` skill: per firm, classify TRAs as original/amendment/termination, write per-filing annotations and a contract log.
4. **Build timeline.** `tra-build-timeline` skill: per firm, write the concise `<firm>_summary.qmd` file with YAML frontmatter (status, dates, tax-asset type, sharing ratio, companies, CIKs, role, trigger-event tags), an event-grouped timeline, and a one-paragraph explanation.
5. **HTM to markdown.** `tra-htm-to-md` skill: convert each `.htm` contract file in `TRA-contracts/<firm>/` to a `.md` companion via pandoc + an LLM cleanup pass.
6. **Build database.** `pixi run -- python scripts/build_tra_database.py`: aggregates the per-firm `*_summary.qmd` files into `outputs/tra-database/tras.parquet`, `events.parquet`, `stock_by_date.parquet`.
7. **Build dashboard.** `pixi run -- python scripts/build_dashboard.py`: reads the three parquet files and renders `outputs/tra-database/dashboard.html` (self-contained, vega-lite from CDN, file://-portable).

The `sec-edgar` skill is a building block called by `tra-download-filings`; it can also be invoked directly for ad-hoc EDGAR queries. The `tra-packet` skill assembles a per-firm evidence packet for manual review.

## What sits under the project root after the s3 cleanup

```
/home/sulli/research/tra/
├── .claude/                     # Project-local Claude Code config + skills
│   ├── CLAUDE.md
│   ├── settings.local.json
│   └── skills/
│       ├── sec-edgar/
│       ├── tra-build-timeline/
│       ├── tra-download-filings/
│       ├── tra-htm-to-md/
│       ├── tra-packet/
│       └── tra-process-filings/
├── .gitignore                   # excludes large caches + corpus from the repo
├── TRA-contracts/               # 321 firm subdirs (gitignored; corpus stays local)
├── coauthor/                    # coauthor project tree
├── notebooks/                   # user will manually relocate; treat as user space
├── outputs/
│   └── tra-database/
│       ├── SCHEMA.md
│       ├── dashboard.html
│       ├── dashboard.template.html
│       ├── tras.parquet
│       ├── events.parquet
│       └── stock_by_date.parquet
├── pixi.toml
├── pixi.lock
└── scripts/
    ├── build_tra_database.py
    ├── build_dashboard.py
    ├── sec_edgar/               # EDGAR API client (Python package)
    ├── tra_packet/              # tra-packet helper module
    └── tra_*.py                 # CIK-list and exhibit helpers retained for s8
```

## Constraints

- Skip the user-invocable Claude Code skills' invocation syntax; just describe what each skill does in one line. The user knows how to invoke skills.
- Do NOT mention `tra-refresh` in the skill catalog. That skill doesn't exist yet (built in s7).
- The README is the front door for a new collaborator opening the repo. Lead with the workflow steps, not the data; the schema doc handles the data side.
- Every command in the README must actually work. Run them.
- Do not write a quick-start that depends on the corpus being present. A fresh clone will have no `TRA-contracts/`; the README should say "step 2 populates it" rather than "tras.parquet is in the repo, just run the dashboard build."
- Standard project convention: refer to files by their path relative to the project root (e.g., `scripts/build_tra_database.py`), not absolute paths.

## Banned terms (project enforcement, will be checked by linter)

- The word "delve"
- The word "leverage" as a verb
- The word "comprehensive"
- The word "robust" outside statistical contexts
- The word "surface" as a verb (use "raise", "expose", "show")
- The word "prose"
- The phrase "smoke test" (use "sanity check" or "trial run")
- The negation-correction pattern (`, not X`); state the positive claim
- Em-dashes (use commas, colons, or parens)

## DEVIATIONS

Write `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-writer.md` only if you had to make a judgment call (e.g., the workflow description departed from the plan, or you decided to omit a section the plan listed). Routine drafting doesn't need DEVIATIONS.

## Return

Reply with:
- Path to `README.md`.
- Confirmation that each documented command runs without error from a fresh shell (run them).
- A note on anything you couldn't verify (e.g., commands that require external state like `TRA-contracts/` being populated).

### Response



---
