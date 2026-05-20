
## 2026-05-19T03:19:22-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for step S4 of the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Step: S4 — Parquet conversion

Read first:
- `coauthor/2026-05-18-git-good/ca-02-plan.md` (S4 implementation actions + S4 review specs)
- `scripts/build_tra_database.py` (the build script)
- `scripts/build_dashboard.py` (the dashboard build script)
- `outputs/tra-database/SCHEMA.md` (schema doc that needs updating)

## Goal

Convert the database build and the dashboard build to read and write parquet instead of csv. Verify both still run end-to-end and the dashboard renders. Update SCHEMA.md to reflect parquet filenames and column types.

## Implementation actions (from ca-02-plan.md S4, expanded with context)

1. **Edit `scripts/build_tra_database.py`** to write parquet outputs in place of csv:
   - Change all `.write_csv(...)` calls to `.write_parquet(...)`.
   - Rename the output filenames from `*.csv` to `*.parquet`. The three outputs are `tras.csv`, `events.csv`, `stock_by_date.csv`.
   - Preserve column ordering and schema. With parquet, `cik` and `ciks` retain string type natively (parquet stores type metadata), so the existing build doesn't need explicit schema-overrides on the write side.

2. **Edit `scripts/build_dashboard.py`** to read parquet:
   - Change `pl.read_csv(...)` calls to `pl.read_parquet(...)`. Update the three filename references from `.csv` to `.parquet`.
   - The current `schema_overrides={"cik": pl.String, "ciks": pl.String}` argument is csv-specific; parquet stores dtype natively. Remove those overrides on the parquet path. If the build_dashboard.py script does any explicit string casting beyond schema_overrides, leave that alone.

3. **Run `pixi run -- python scripts/build_tra_database.py`** from the project root and confirm the three parquet files are written to `outputs/tra-database/`. Expected row counts: `tras.parquet=360`, `events.parquet=1635`, `stock_by_date.parquet=8415`.

4. **Run `pixi run -- python scripts/build_dashboard.py`** from the project root and confirm `outputs/tra-database/dashboard.html` is rebuilt. The dashboard is a self-contained HTML file with embedded JSON; the file size should be in the 1.5-2 MB range. Compare against the prior build's size as a sanity check.

5. **Delete the old csv outputs.** After confirming the parquet build round-trips through both scripts, remove `outputs/tra-database/{tras,events,stock_by_date}.csv` so the directory doesn't carry stale duplicates. Use `rm`, not `git rm` (we're not in a git repo yet; s6 initializes git).

6. **Investigate `outputs/tra-database/dashboard.qmd`.** The s3 reviewer flagged that two render paths to `dashboard.html` coexist: the `dashboard.qmd` + Quarto path, and the `dashboard.template.html` + `scripts/build_dashboard.py` path. Read `dashboard.qmd` briefly. If it reads the old csv inputs, decide whether to (a) update it to read parquet, (b) flag it for deletion as a stale alternate path, or (c) leave it untouched and note in DEVIATIONS. Pick what makes the cleanest repo state and document the choice.

7. **Update `outputs/tra-database/SCHEMA.md`** to reflect parquet filenames:
   - Section "File 1", "File 2", "File 3" headers: rename csv to parquet (e.g., `## File 1: tras.parquet` instead of `## File 1: tras.csv`).
   - "Regenerating" section at the bottom: confirm the pixi command still works (it does); update the description of what files are written.
   - The "Conventions" section: revisit the bullet about csv schema_overrides for `cik` / `ciks` — with parquet, the dtype is preserved natively, so loading with polars no longer needs an override. Update accordingly.
   - Leave all column-level documentation untouched; the schemas don't change.

## Success criteria (ca-02-plan.md S4 checklist)

- `outputs/tra-database/tras.parquet`, `events.parquet`, `stock_by_date.parquet` exist.
- Row counts match the prior csv outputs (360, 1635, 8415).
- `cik` and `ciks` columns retain their string type (leading zeros preserved) in the parquet output. Verify with `pl.read_parquet("outputs/tra-database/tras.parquet").schema`.
- `scripts/build_dashboard.py` reads parquet and produces a `dashboard.html` of comparable size to the prior csv-based build.
- `outputs/tra-database/SCHEMA.md` is updated to reference the parquet filenames.

## DEVIATIONS

Append a new dated S4 section to `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md` only if you had to make a judgment call (the `dashboard.qmd` resolution is the obvious candidate). Routine edits don't need DEVIATIONS.

## Return

Reply with:
- Confirmation that the three parquet files exist with the expected row counts.
- Output size of the rebuilt `dashboard.html` and a note on what was visually verifiable from the rebuild step (the HTML file is self-contained; you can read it as text to confirm it has the expected structure).
- The schema returned by `pl.read_parquet("outputs/tra-database/tras.parquet").schema` so I can confirm cik/ciks types.
- Your decision on `dashboard.qmd` and the reasoning.
- Path to the updated SCHEMA.md.

### Response



---

## 2026-05-19T03:34:03-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for step S6 of the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Step: S6 — Git init and private GitHub push

Read first:
- `coauthor/2026-05-18-git-good/ca-02-plan.md` (S6 implementation actions + S6 review specs)
- `.gitignore` at `/home/sulli/research/tra/.gitignore` (created in s3; verify contents before commit)
- `README.md` at `/home/sulli/research/tra/README.md` (created in s5)

## Goal

Initialize a git repo at the project root, commit the cleaned baseline state, create a private GitHub repo named **`tra-database`** under the user's GitHub account, and push.

## User decisions on this step

- **Repo name:** `tra-database` (not `tra`).
- **Push timing:** Full setup. Initialize, commit, create the private repo, and push in one s6 dispatch. The cleaned baseline should be on GitHub when s6 returns.

## Implementation actions

1. **Pre-flight check.** Confirm cwd is `/home/sulli/research/tra/`. Run `ls -la` and `cat .gitignore` to verify the gitignore is present and includes `.pixi/`, `.tra_history_cache/`, `sec-data-pqt/`, `TRA-contracts/`.

2. **Sensitive-data sweep.** Before any `git add`, grep for credential-shaped strings under the project root (excluding the gitignored paths):
   - `grep -rIE '(api[_-]?key|secret|token|password|bearer)' /home/sulli/research/tra/ --exclude-dir={.pixi,.tra_history_cache,sec-data-pqt,TRA-contracts,.git,node_modules,__pycache__,dashboard_files} 2>/dev/null | head -30`
   - If anything looks like a real credential (not just a documentation example, not just a parameter name in code), halt and write DEVIATIONS. Otherwise proceed.
   - Also confirm there is no `.env`, `credentials.json`, `config.local.json`, or similar at the project root: `ls -la /home/sulli/research/tra/ | grep -E '\\.env|credentials|secret'`.

3. **Verify gh authentication.** Run `gh auth status` and confirm the user is logged in. If not, halt and write DEVIATIONS asking the user to run `gh auth login` manually.

4. **Git init and stage.**
   - `cd /home/sulli/research/tra/` (or stay there)
   - `git init`
   - `git add -A` (the `.gitignore` filters out the large caches and the corpus)
   - `git status` and confirm: `TRA-contracts/`, `.pixi/`, `.tra_history_cache/`, `sec-data-pqt/` are NOT in the index. The output should show staged files for `.claude/` (without `coauthor/`), `.gitignore`, `README.md`, `coauthor/`, `notebooks/build_sec_parquet.ipynb`, `outputs/tra-database/*.parquet`, `outputs/tra-database/*.html`, `outputs/tra-database/SCHEMA.md`, `outputs/tra-database/dashboard.template.html`, `pixi.toml`, `pixi.lock`, `scripts/`. Confirm before the commit.

5. **Commit.** Use this commit message via heredoc (preserve formatting):

   ```
   Initial baseline: cleaned TRA pipeline + database

   First clean baseline after a single-day cleanup pass under the
   2026-05-18-git-good coauthor project:

   - Relocated six skills (tra-download-filings, tra-process-filings,
     tra-build-timeline, tra-htm-to-md, tra-packet, sec-edgar) from
     ~/.claude/skills/ into .claude/skills/ so they auto-load when
     Claude Code opens the project root.
   - Retired the XBRL exploration pipeline (build_tra_history.py,
     extract_tra.py, 2025_11_notes/, tests/) along with its dependent
     CSVs (ipo_date_candidates.csv, tra_deferred_review.csv,
     tra_review_status.csv, tra_events_review.xlsx, tra_panel.parquet).
   - Removed exploratory underscore-prefixed scripts and stale empty
     directory stubs (docs/, findings/).
   - Converted the three database outputs from csv to parquet
     (tras.parquet, events.parquet, stock_by_date.parquet) and
     updated build_tra_database.py / build_dashboard.py to match.
   - Gitignored the large local caches (.pixi/, .tra_history_cache/,
     sec-data-pqt/) and the TRA-contracts/ corpus, which is
     regenerable from the EDGAR pipeline.
   - Wrote README.md documenting workflow, environment, outputs,
     and skill catalog.

   Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
   ```

6. **Create the private GitHub repo and push.** Use `gh`:

   ```bash
   gh repo create tra-database --private --source=. --remote=origin --push --description "Reproducible TRA database build from SEC filings"
   ```

   The `--push` flag pushes the current branch (should be `main`; if it's `master`, rename to `main` first with `git branch -M main`). Confirm the push succeeded.

7. **Verify.** After the push, run:
   - `git log --oneline -5` — confirm the initial commit exists.
   - `git remote -v` — confirm `origin` points at the private repo.
   - `gh repo view --json url,visibility -q '.url, .visibility'` — confirm the remote is private.
   - `gh api /repos/<owner>/tra-database/contents | jq -r '.[].path' | head -20` — confirm `TRA-contracts/` is NOT in the remote tree.

8. **DEVIATIONS append.** Append a new dated S6 section to `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md` if you had to make any judgment call (e.g., picking the default branch name, handling an unexpected git state). Routine init + push doesn't need DEVIATIONS; only flag actual divergences.

## Constraints

- **Do not commit anything containing real credentials.** If the credential sweep finds a hit, halt.
- **Do not push to public.** The repo must be private. Verify with `gh repo view`.
- **No interactive flags.** Anything that prompts the user mid-script (e.g., `gh auth login`) is a halt condition; report and let the user finish manually.
- **Do not amend or force-push.** This is a brand-new repo; use a single fresh commit.
- **Do not skip git hooks.** No `--no-verify`.

## Return

Reply with:
- The GitHub URL of the private repo (e.g., `https://github.com/<owner>/tra-database`).
- Confirmation that `git log` shows exactly one commit on `main` tracking `origin/main`.
- Confirmation that the remote tree does NOT contain `TRA-contracts/`.
- The sensitive-data sweep result (briefly: number of hits, whether any looked real).
- Any judgment calls flagged in DEVIATIONS.

### Response



---

## 2026-05-19T05:20:27-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for step S7a of the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Step: S7a — Build `tra-find-candidates` skill

Read first:
- `coauthor/2026-05-18-git-good/ca-02-plan.md` (S7a implementation actions + S7a review specs)
- `.claude/skills/sec-edgar/SKILL.md` (your input — the FTS, archives, and forms functions you'll call)
- `.claude/skills/tra-download-filings/SKILL.md` (house style reference: the search-with-retry wrapper, the SEC quirks documented there, the ALLOWED_FORMS handling. You're not copying behavior; you're inverting the flow.)
- `.claude/skills/tra-process-filings/SKILL.md` (downstream consumer of the candidates this skill produces)

## Goal

Build a new skill at `.claude/skills/tra-find-candidates/` that sweeps EDGAR full-text search globally for the four TRA phrase variants across all time in sub-annual windows, unions the hits, filters to filings carrying `EX-10.*` documents, and pulls only those exhibits to a candidates tree keyed by CIK. Output: a directory tree at `candidates/<CIK>/<accession>_<filename>` plus a manifest CSV.

## Implementation (verbatim from ca-02-plan.md S7a + expanded context)

1. **Design `.claude/skills/tra-find-candidates/SKILL.md`.**

   Trigger phrases: "find TRA candidate firms", "sweep EDGAR for TRA exhibits".

   Action sequence:
   - (i) Query the EDGAR full-text search index for each of the four TRA phrase variants:
     - `"tax receivable agreement"`
     - `"tax receivable agreements"`
     - `"tax receivables agreement"`
     - `"tax receivables agreements"`
   - (ii) Paginate by sub-annual time window. Default: monthly. The 10,000-result FTS API ceiling is exceeded by annual windows on common years for the TRA queries. The script iterates over `(year, month)` pairs from 2001-01 (earliest FTS coverage) through current month, calling `search_filings(q=..., startdt="YYYY-MM-01", enddt="YYYY-MM-<last-day>")` for each. If a single month query returns `meta["relation"] == "gte"` (i.e., the 10K cap was hit), halve to bi-weekly windows for that month and retry.
   - (iii) Union the four queries' results on `adsh` keeping one row per filing (keep the snippet from the first matching variant).
   - (iv) For each filing in the union, fetch its document index. The full-text search result row already carries the `primary_doc` field (the matching document); but we want every EX-10.* document in the filing, not just the matching primary. Use `fetch_filing(cik, adsh)` (which returns `(body, idx_lf)`) to get the full document list, then filter the index LazyFrame to rows where `name` matches the `EX-10.*` pattern (case-insensitive: `^ex[-_]?10[.\-_]\d+`).
   - (v) Pull each matching exhibit via `fetch_document(cik, adsh, name)` and save under `candidates/<CIK>/<accession>_<filename>` keyed by CIK. The `<accession>` is the dashed form (e.g., `0001775625-21-000004`).
   - (vi) Write `candidates/manifest.csv` with one row per saved exhibit:
     ```
     cik,accession,filename,filing_date,form,fts_snippet,phrase_variants_matched
     ```
     `phrase_variants_matched` is a pipe-joined list of which of the four variants matched (a single filing can match multiple variants).

   Document each section per house style: Purpose, Universal constraints, Inputs, Outputs, Workflow, What this skill does not do.

   Universal constraints to include (lifted from `tra-download-filings/SKILL.md`):
   - All SEC interaction goes through `scripts/sec_edgar/` invoked as `PYTHONPATH=scripts pixi run python ...` from project root. (NOTE for you: this path will change to `.claude/skills/sec-edgar/scripts/` in s7f; write the skill against the CURRENT path and s7f will catch and update it. Do not pre-anticipate s7f's relocation.)
   - `EdgarClient` enforces the 10 req/sec rate cap; do not add a second throttle layer.
   - Wrap every `search_filings()` call with a 5xx retry wrapper (search module doesn't retry internally). Copy the `search_with_retry` snippet from `tra-download-filings/SKILL.md`.
   - Never write output filenames starting with `report`, `summary`, `findings`, or `analysis`.
   - Do not use the acronym "EFTS"; write "EDGAR full-text search" or "full-text search".

   Inputs section: documents the `output_dir` (default: `candidates/` at project root) and the `start_window`, `end_window` parameters (defaults: 2001-01 through current month). Optional `window_size` parameter (default: monthly; can be set to bi-weekly explicitly for high-volume periods).

   What this skill does not do:
   - Classify exhibits as TRA / not-TRA (that is s7b, the manual classification step).
   - Pull anything besides EX-10.* documents (no primary filing, no other exhibits, no 8-K body text).
   - Download filings for already-confirmed TRA CIKs (that is the revised `tra-download-filings` after s7c).

2. **Implement the helper script** at `.claude/skills/tra-find-candidates/scripts/find_candidates.py`. The script is invoked as:

   ```bash
   PYTHONPATH=scripts pixi run python .claude/skills/tra-find-candidates/scripts/find_candidates.py \
     --output-dir candidates/ \
     --start 2024-06 \
     --end 2024-06
   ```

   Key implementation details:
   - Use `polars` for the union and dedup (consistent with the rest of the project).
   - The four queries run inside a single `EdgarClient` context so they share the rate-limit token bucket.
   - Idempotency: if `candidates/<CIK>/<accession>_<filename>` already exists, skip the fetch.
   - Append to `candidates/manifest.csv` rather than overwrite, so re-running on a different window adds rows without losing prior windows. Dedup the CSV on `(cik, accession, filename)` at the end.
   - Log progress per month-window: queries run, hits found, exhibits pulled. Stdout is fine.
   - The script exits 0 on success, 1 on unrecoverable error (e.g., persistent HTTP 5xx after retry). Errors in individual month-windows should be logged but not halt the run.

3. **Add `candidates/` to `.gitignore`** since the exhibit downloads can be many small files and aren't part of the repo. Edit `/home/sulli/research/tra/.gitignore` to add `candidates/` after the existing entries.

4. **Verify on a small time window.** Run:
   ```bash
   PYTHONPATH=scripts pixi run python .claude/skills/tra-find-candidates/scripts/find_candidates.py \
     --output-dir candidates/ \
     --start 2024-06 \
     --end 2024-06
   ```
   Expected: a non-trivial number of FTS hits per query (low hundreds to low thousands for a single month given TRA-mention frequency), a smaller union size after dedup, an even smaller count carrying EX-10.* exhibits, and that count's worth of exhibits saved.

5. **Document trial-run counts.** Write the trial-run stats to your return message: count of FTS hits per query, union size, count of filings carrying EX-10.* documents, count of exhibits pulled.

## Constraints

- Do not pull the parent filing's primary document. Only EX-10.* exhibits.
- Do not pre-anticipate s7f's script relocation. Use `PYTHONPATH=scripts` in the SKILL.md and the script. s7f will catch and update.
- Do not delete or modify any existing skill. This step adds a new skill alongside the existing six.
- Save the verification trial-run output (a small candidates/ tree from 2024-06) on disk so the reviewer can inspect.

## DEVIATIONS

Write a new dated S7a section to `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md` if you have to make a judgment call. Examples worth flagging: an FTS query for a month exceeds 10K even after halving (the script's defensive case), the EX-10.* regex needs adjustment to match SEC's actual naming variants, or a fetch_filing call returns a `None` body for a malformed accession.

## Return

Reply with:
- Path to `.claude/skills/tra-find-candidates/`.
- Trial-run counts: hits per query, union size, EX-10.* filing count, exhibits pulled.
- Any anomalies encountered (rate limits, malformed indexes, EX-10.* regex edge cases).

### Response



---

## 2026-05-19T11:19:45-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for an interactive task on the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Task

The user wants step 1 of the new workflow (the global EDGAR full-text-search sweep) executed and saved to `data/edgar-query/full-text.parquet`. The exhibit pull (step 2) is deferred. The existing `find_candidates.py` couples the sweep and the exhibit pull; this task splits them.

## Implementation

1. **Edit `.claude/skills/tra-find-candidates/scripts/find_candidates.py`** to add a `--no-exhibits` flag plus a `--save-union-parquet PATH` flag.

   When `--no-exhibits` is set:
   - Skip the `fetch_filing_index` + EX-10 regex + extension allow-list + exhibit-pull steps.
   - Skip writing the per-exhibit `candidates/<CIK>/<accession>_<filename>` files.
   - Skip appending rows to `candidates/manifest.csv`.

   When `--save-union-parquet PATH` is set:
   - After unioning the four phrase-variant query results on `adsh` (the deduplicated union; one row per matching filing across all four queries), write the union LazyFrame to that parquet path. Create parent directories as needed.
   - The parquet's columns should be the LazyFrame's schema as returned by `search_filings` (`adsh`, `primary_doc`, `ciks`, `form`, `display_names`, `file_date`, `snippet`, `period_of_report`, `file_description`) plus a `phrase_variants_matched` column carrying the pipe-joined set of variants that matched the row.
   - Preserve `cik` and `ciks` as `pl.String` / `pl.List(pl.String)` (the existing schema already does this).

2. **Update `.claude/skills/tra-find-candidates/SKILL.md`** to document both new flags in the Workflow section. Add one sentence each. Keep the rest of the SKILL.md unchanged.

3. **Run the full sweep** from project root:

   ```bash
   PYTHONPATH=scripts pixi run python .claude/skills/tra-find-candidates/scripts/find_candidates.py \
     --start 2001-01 \
     --end 2026-05 \
     --no-exhibits \
     --save-union-parquet data/edgar-query/full-text.parquet
   ```

   Expected duration: 30-60 minutes wall clock (~1220 FTS API calls minimum at 9 req/s with caching; cold-cache calls dominate the first run).

   Progress logging should stream to stdout per month-window: queries run, raw hits per variant, union size. Stderr captures errors.

4. **Save the run's stdout/stderr** to `data/edgar-query/run.log` so the user can inspect after the fact.

5. **After the run completes:**
   - Confirm `data/edgar-query/full-text.parquet` exists.
   - Report total union size (row count), date range covered, and any month-windows that triggered the bi-weekly halving fallback (the script's defensive case for FTS queries that exceed the 10,000-result ceiling).
   - Report any month-windows that errored out (e.g., persistent HTTP 500s after retry).

6. **Append a new dated section to `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md`** describing:
   - The split of `find_candidates.py` into sweep-and-pull (default) versus sweep-only (`--no-exhibits`) modes.
   - Any month-windows that needed bi-weekly halving (concrete evidence the defensive case is real).
   - Any errors that the run couldn't recover from.

## Constraints

- `data/edgar-query/full-text.parquet` is the canonical artifact. Do not also write a redundant manifest CSV when `--no-exhibits` is set; the parquet is the deliverable.
- The two new flags do not break the existing default behavior (sweep + exhibit pull). Reviewers will check that running without the flags still works.
- The FTS cache at `.tra_history_cache/edgar_search/` should already have the June 2024 hits from s7a's trial run. Subsequent runs hit the cache for that month; only the other 304 months hit the network cold.
- Do not refactor `find_candidates.py` beyond what's needed for the two flags. Other improvements (e.g., snippet extraction from document bodies) are out of scope here.

## Return

Reply with:
- Path to `data/edgar-query/full-text.parquet` and its row count.
- Date range covered (the actual min and max `file_date` in the parquet).
- Any month-windows that triggered bi-weekly halving.
- Any errors that the run couldn't recover from.
- The two new flags added to the script.

### Response



---

## 2026-05-19T12:10:14-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for a one-off recovery task on the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Task

The full-history EDGAR full-text-search sweep produced `data/edgar-query/full-text.parquet` with 20,721 rows, but ten month-windows dropped entirely due to persistent HTTP 500s from `efts.sec.gov`. Retry those ten months and append the recovered rows to the parquet, dedup on `adsh`.

## Ten missing months

```
2008-05  2008-06  2012-01  2015-11  2017-11
2019-12  2020-08  2020-11  2022-05  2022-08
```

## Implementation

Reuse `.claude/skills/tra-find-candidates/scripts/find_candidates.py` with `--no-exhibits --save-union-parquet <tmp>` per month, then concat into the main parquet.

Cleanest path: write a one-off retry script (or run a Python one-liner via `PYTHONPATH=scripts pixi run python -c "..."`):

1. Read the existing `data/edgar-query/full-text.parquet` into a polars DataFrame.
2. For each of the ten months, call `union_month` (the inner function in `find_candidates.py`) directly, or call `search_filings` with the four phrase variants for that month and union the results yourself. The `search_with_retry` wrapper from `find_candidates.py` should be used so transient 500s get a second chance.
3. Concat the recovered rows with the existing parquet, dedup on `adsh` (keep first), and write back to `data/edgar-query/full-text.parquet`.
4. If any of the ten months still error out on retry, log them but continue. Do NOT crash; partial recovery is better than no recovery.

## Constraints

- Do not modify `find_candidates.py` itself. This is a recovery script, separate from the canonical skill.
- Preserve the exact schema and dtypes of the existing parquet. Use `pl.concat(..., how="diagonal_relaxed")` if dtype quirks come up.
- Idempotency: if every month succeeds, the row count goes from 20,721 to roughly 21,000-21,500 (judging by adjacent months in the run log). If some still fail, the row count rises by less.

## Return

Reply with:
- Final row count in the parquet.
- Which of the ten months recovered.
- Which still failed after retry.

### Response



---

## 2026-05-19T12:48:56-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You are the **coder** for a small refactoring task on the active coauthor project `2026-05-18-git-good` at `/home/sulli/research/tra/coauthor/2026-05-18-git-good/`.

## Task

The `.claude/skills/tra-find-candidates/` work is deterministic (no agent navigation, no LLM judgment); it should be plain scripts under `scripts/` alongside `build_tra_database.py`, not a skill. Refactor accordingly and add the previously-proposed `pull_exhibits.py` companion.

## Implementation

1. **Move and simplify `find_candidates.py`:**
   - `mv .claude/skills/tra-find-candidates/scripts/find_candidates.py scripts/find_candidates.py`.
   - Strip the exhibit-pull paths out: remove `extract_ex10_documents`, `download_exhibits`, `append_manifest`, `dedup_manifest` functions and their call sites.
   - Remove the `--no-exhibits` flag (sweep-only is now the only behavior).
   - Keep `--save-union-parquet` but make it default to `data/edgar-query/full-text.parquet`.
   - Keep `--output-dir` only if it's still used for anything; otherwise remove.
   - Keep all the sweep/retry/halving logic (`search_with_retry`, `union_month`, `run_query_with_halving`, `month_iter`, `biweekly_bounds`).
   - The simplified script's behavior: run the sweep over `--start` through `--end`, write the parquet, exit.

2. **Build new `scripts/pull_exhibits.py`:**
   - Reads a parquet of filing references (default: `data/edgar-query/full-text.parquet`).
   - Iterates rows. For each row, calls `fetch_filing_index(cik, adsh)` (the index helper, not the full filing fetch).
   - Filters the index to EX-10.* document names using the broadened regex `(?:^|[^a-z])d?ex(?:hibit)?[-_]?10[._\-]?\d` plus the extension allow-list `{.htm, .html, .txt}`. These are the same filters `find_candidates.py` used; lift the regex compilation into this script directly. (Or import from a shared module if you'd rather, but no skill folder anymore, so it has to live under `scripts/`.)
   - Downloads each matching exhibit to `data/edgar-query/exhibits/<CIK>/<accession>_<filename>` via `fetch_document(cik, adsh, filename)`.
   - Idempotent: skip exhibits already on disk.
   - Writes / appends to a manifest at `data/edgar-query/exhibits/manifest.csv` with columns `cik, accession, filename, filing_date, form, phrase_variants_matched` (the last three carried over from the input parquet row).
   - Flags: `--parquet PATH` (default `data/edgar-query/full-text.parquet`), `--output-dir DIR` (default `data/edgar-query/exhibits/`), `--limit N` (optional cap for testing).
   - Logs progress per filing: CIK, accession, EX-10 docs found, downloaded.

3. **Delete the now-empty skill:**
   - `rm -rf .claude/skills/tra-find-candidates/`.

4. **Update README.md:**
   - Remove the `tra-find-candidates` row from the skill catalog table. (The skill never made it into the README catalog — it was added in s7a — but check and remove if it's there.)
   - In the Workflow section, the steps that involve candidate discovery and exhibit pull are now scripts. Add or update text so step 1 (sweep) and step 2 (exhibit pull) point at `scripts/find_candidates.py` and `scripts/pull_exhibits.py` respectively, with the exact `pixi run -- python ...` commands.

5. **Verify on a trial:**
   - Run `pixi run -- python scripts/find_candidates.py --start 2024-06 --end 2024-06 --save-union-parquet data/edgar-query/trial-2024-06.parquet`. Confirm it runs to completion and writes the parquet.
   - Run `pixi run -- python scripts/pull_exhibits.py --parquet data/edgar-query/trial-2024-06.parquet --output-dir data/edgar-query/trial-exhibits --limit 5`. Confirm five filings' EX-10 exhibits land on disk.
   - Delete the trial outputs (`data/edgar-query/trial-2024-06.parquet`, `data/edgar-query/trial-exhibits/`) after the verification passes.

## Constraints

- Do NOT touch `data/edgar-query/full-text.parquet` (the real 22,251-row artifact we just built). The pull-exhibits trial uses a separate trial parquet.
- The scripts import from `sec_edgar` via `PYTHONPATH=scripts pixi run python ...` (s7f hasn't run yet; `scripts/sec_edgar/` is still the import target).
- Preserve the existing `find_candidates.py` retry / halving / per-month logic exactly; only the surrounding shell + the exhibit-pull paths change.
- The two scripts share the `sec_edgar` client setup. They don't need to share a helper module (lift the regex constants into each script directly).

## DEVIATIONS

Append a new dated S7a section update to `coauthor/2026-05-18-git-good/deviations/DEVIATIONS-coder.md` recording the skill-to-script refactor. Note that the original S7a plan specified building a skill at `.claude/skills/tra-find-candidates/`; this refactor moves to plain scripts under `scripts/`. The plan will be amended next; the deviation note is the bridge.

## Return

Reply with:
- Final paths of both scripts (`scripts/find_candidates.py`, `scripts/pull_exhibits.py`).
- Confirmation that `.claude/skills/tra-find-candidates/` is gone.
- Trial run output (parquet row count, exhibit count).
- README diff summary.

### Response



---

## 2026-05-19T12:51:46-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

Run `scripts/pull_exhibits.py` against the full filings parquet to download every EX-10.* exhibit referenced.

```bash
PYTHONPATH=scripts pixi run python scripts/pull_exhibits.py \
  --parquet data/edgar-query/full-text.parquet \
  --output-dir data/edgar-query/exhibits/ \
  > data/edgar-query/pull-exhibits.log 2>&1
```

Inputs:
- 22,251 unique filings in the parquet, across 2,407 unique CIKs.
- The script is idempotent; if exhibits already exist on disk it skips them. A trial run earlier downloaded ~32 exhibits across a small sample window; those files are gone (trial cleaned up after).
- The script writes a manifest at `data/edgar-query/exhibits/manifest.csv` with one row per downloaded exhibit.

Expected wall clock: 60-120 minutes. The bulk is per-filing index fetches (22,251 cold-cache calls at 9 requests per second). EX-10 document downloads add maybe another 10,000-20,000 fetches.

Monitor for HTTP 500 errors. The script (per its implementation) should retry transient 5xx; if not, log them and continue. Persistent failures get reported in the run log; don't crash the whole run.

After the script exits, report:
- Final manifest.csv row count (= total EX-10 exhibits downloaded).
- Unique CIK count among rows that contributed at least one exhibit.
- Count of filings in the parquet that produced zero EX-10 documents.
- Any persistent errors that prevented some filings from being processed.

If `pull_exhibits.py` doesn't have retry logic for transient 5xx, edit it to add a wrapper similar to `search_with_retry` in `scripts/find_candidates.py` (3 attempts with 1.5s back-off) before launching the long run. Document the edit briefly in DEVIATIONS if you make it.

### Response



---

## 2026-05-19T20:06:23-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

You're working in the TRA research project at `/home/sulli/research/tra/` (this is $PROJECT_ROOT; the pixi manifest is at `~/research/pixi.toml`). Run Python with `pixi run -- python ...` from the project root.

## Background

This project builds a corpus of Tax Receivable Agreements (TRAs) from SEC EDGAR. A prior step pulled 15,035 EX-10.* exhibits from EDGAR full-text search into `data/edgar-query/exhibits/<CIK>/*.htm`. EX-10 is the SEC "material contracts" exhibit class, so most of these are employment agreements, credit agreements, leases, etc.; only a minority are actual TRAs. The next step filters that haystack down to documents that plausibly ARE TRAs, so a human only manually reviews a small set.

The confirmed-TRA reference corpus from earlier work lives at `TRA-contracts/<firm>/` (per-firm directories). These directories hold ALL downloaded filings per firm (10-Ks, 8-Ks, and more, not only TRA contracts); each firm's `contract_log.md` records which documents are the actual TRA contract exhibits.

## Your task

Build a skill at `/home/sulli/research/tra/tmp/TRA-classify/` consisting of a `SKILL.md` and a `scripts/` subfolder of Python scripts. Given a source directory, the skill recursively finds every `.htm` file, drops the ones definitely not TRAs, and returns the list of files still needing a human to check.

### Phase 1 — learn what a TRA looks like

1. Read the section about what a Tax Receivable Agreement looks like in `.claude/skills/tra-process-filings/SKILL.md` (heading is roughly "What a Tax Receivable Agreement looks like").
2. Read `.claude/skills/tra-htm-to-md/scripts/clean_and_link.py` and `.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` (if the filenames differ slightly, find them under `.claude/skills/tra-htm-to-md/`). They handle SEC HTML; reuse their parsing utilities where it helps rather than writing your own.
3. Pick 5 reference TRAs from `TRA-contracts/*/*.htm`, each under 200 kB (`find TRA-contracts -name '*.htm' -size -200k`). Use the per-firm `contract_log.md` files to confirm the 5 you pick are actual TRA contract documents, not 10-Ks that merely mention a TRA. Read them.
4. Pick a random sample (15-20) of `.htm` files from `data/edgar-query/exhibits/*/*.htm` as the contrast set, mostly non-TRA EX-10 contracts. Read enough to see what separates them from the reference TRAs.

Structural hint from the user: a contract document opens with a centered line (or several centered lines, ending at the first left-aligned block of text) stating what the contract is, and sometimes who the parties are. For a TRA that centered title block contains "TAX RECEIVABLE AGREEMENT". This is a strong, cheap signal; check the centered text near the top of the document.

WSL crash warning: never load a large HTML file fully into memory. Filter by file size first, and when reading HTML for the title check read only the first chunk (50-100 kB) rather than the whole file.

### Phase 2 — write the skill

Write `tmp/TRA-classify/SKILL.md` and `tmp/TRA-classify/scripts/*.py`. The script(s):
- Accept a source directory as a command-line argument.
- Recursively glob every `.htm` file under it.
- Classify each file as "definitely not a TRA" (drop) or "needs manual review" (keep).
- Be conservative on dropping: drop a file only when confident it is not a TRA. A false drop discards a real TRA, the costly error; a false keep just adds one file to the manual list. Favor recall.
- Write the keep-list to a file under `tmp/TRA-classify/` (a CSV with file path plus the signal columns you computed) and print a summary: total `.htm` found, dropped, kept.

Encode the signals from Phase 1: the centered-title check, the keyword cues from the "what a TRA looks like" section, file-size bounds, presence or absence of the phrase "tax receivable agreement". Keep the scripts straightforward; no one-off helpers for things used once.

Set any random seed from today's date (2026-05-19), not 42.

### Phase 3 — validate and report

- Run the script so all 5 reference TRAs survive as "needs review" (zero false drops). Put the 5 in a temp dir if that is easier than pointing at the full corpus.
- Run it against your random non-TRA sample; most should drop.
- Run it against the full `data/edgar-query/exhibits/` and report the reduction (15,035 to how many kept).

Return in your response: (a) the distinguishing features you found, (b) the filter logic you encoded and why, (c) validation results (false-drop count on the 5 references, drop rate on the non-TRA sample), (d) the final reduction count on the full exhibits set, (e) any genuinely ambiguous files.

This is an ad-hoc task, not a `ca-02-plan.md` step: no DEVIATIONS file needed, put everything in your response.

### Response



---

## 2026-05-19T22:30:23-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

review the proposed skill/script in `tmp/TRA-classify/`, search for any errors, and write a few bullet points on its findings. Each bullet point should be one sentence only and they should be ordered by importance.

### Response



---
