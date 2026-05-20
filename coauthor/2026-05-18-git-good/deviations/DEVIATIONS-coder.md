---
worker: coder
project_id: 2026-05-18-git-good
---

# DEVIATIONS — coder

## 2026-05-19 — S2 (Skill relocation): halted before move

**Status:** Halted. No files moved. Awaiting user decision on destination path.

**Plan said:** "`mkdir -p $PROJECT_ROOT/skills/` and move each source directory into it: `mv ~/.claude/skills/tra-* ~/.claude/skills/sec-edgar $PROJECT_ROOT/skills/`." Step 4 of the plan instructed: "If the global skill mechanism does not pick up project-local skills automatically, document that in DEVIATIONS-coder.md and stop; the user resolves before s3."

**What I found:** Per the official Claude Code skills documentation (`https://code.claude.com/docs/en/skills`), project-level skills are auto-loaded only from `.claude/skills/<skill-name>/SKILL.md` under the project root (and from parent directories up to the repo root). The documented load locations are:

| Scope | Path |
| --- | --- |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` |
| Project | `.claude/skills/<skill-name>/SKILL.md` |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` |
| Enterprise | Managed-settings path |

An arbitrary `skills/` directory at the project root (the plan's destination) is not on the auto-load list. Skills moved there would stop being discovered by Claude Code. That fails S2 success criterion 4 ("The relocated skills load from the project") and would block S6's README skill-catalog claim and S7's `tra-refresh` workflow.

**Source consulted:** WebFetch on `https://code.claude.com/docs/en/skills`, section "Where skills live" and "Automatic discovery from parent and nested directories."

**Why I halted instead of substituting:** The plan named `$PROJECT_ROOT/skills/` explicitly; the success criteria for S2 also name `skills/`. Silently rerouting to `.claude/skills/` would diverge from the frozen plan without user sign-off. The plan's own halt-and-flag instruction in S2 step 4 is the right path.

**Recommended resolution (for user):** Change the destination to `$PROJECT_ROOT/.claude/skills/` so the relocated skills auto-load as project skills. This requires an amendment to `ca-02-plan.md` (success criteria reference `skills/`; subsequent steps S3, S5, S7 also reference `skills/` and would need the same edit). Alternatively, accept that the skills will need to be invoked via a non-standard mechanism (e.g., kept in `skills/` but pointed at by an `--add-dir` invocation with a `.claude/skills/` subdirectory inside it, or referenced manually). The cleanest fix is `.claude/skills/`.

**No move performed.** All six source directories remain in place at `~/.claude/skills/`:

- `~/.claude/skills/tra-download-filings/`
- `~/.claude/skills/tra-process-filings/`
- `~/.claude/skills/tra-build-timeline/`
- `~/.claude/skills/tra-htm-to-md/`
- `~/.claude/skills/tra-packet/`
- `~/.claude/skills/sec-edgar/`

**Awaiting:** User decision on destination path before s3.

**Resolution (2026-05-19):** Plan amended; destination changed from `$PROJECT_ROOT/skills/` to `$PROJECT_ROOT/.claude/skills/` (Claude Code's documented project-skill auto-load path). Ran:

```
mkdir -p /home/sulli/research/tra/.claude/skills/
mv ~/.claude/skills/tra-download-filings ~/.claude/skills/tra-process-filings ~/.claude/skills/tra-build-timeline ~/.claude/skills/tra-htm-to-md ~/.claude/skills/tra-packet ~/.claude/skills/sec-edgar /home/sulli/research/tra/.claude/skills/
```

All six skill directories now live at `/home/sulli/research/tra/.claude/skills/` and each contains a `SKILL.md`. None remain at `~/.claude/skills/`. The system-reminder skill list at re-dispatch time confirmed Claude Code auto-loaded all six from the new project location.

**In-project references updated:** one — `scripts/tra_download.py` line 1 docstring changed from `~/.claude/skills/tra-download-filings` to `.claude/skills/tra-download-filings`. The other grep hits were historical (this DEVIATIONS file's own prior text, `ca-01-scope.md`, `ca-02-plan.md`, prior review files, and the `2026-05-12-edgar-scrape/transcript.html`); those record what was true at the time and should not be rewritten.

**Informational findings for s3** (intra-skill path references inside the relocated `SKILL.md` files that may need follow-up):

- `tra-htm-to-md/SKILL.md` references its bundled helper scripts via absolute paths `~/.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` and `~/.claude/skills/tra-htm-to-md/scripts/clean_and_link.py` (lines 59, 122, 153, 157). After the move, these paths no longer resolve; the skill is broken internally until s3 (or a follow-up) rewrites them to the new location (e.g. `.claude/skills/tra-htm-to-md/scripts/...`).
- `tra-download-filings/SKILL.md` line 218 mentions `scripts/tra_download.py` as the implementation, consistent with the methodology reviewer's S1 finding that the script and the skill are paired.
- `sec-edgar/SKILL.md`, `tra-build-timeline/SKILL.md`, `tra-process-filings/SKILL.md`, and `tra-packet/SKILL.md` reference the project's `scripts/sec_edgar/` package via project-relative paths (e.g. `scripts/sec_edgar/`, `PYTHONPATH=scripts`). Those references continue to work as long as the skills are invoked from the project root, which is the normal case.

## 2026-05-19 — S3 (Execute cleanup): completed

**Status:** Done. All inventory.md `delete` paths removed; `.gitignore` created; database build verified.

**Paths deleted (29 total):**

Root files (7):
- `build_tra_history.py` (116K)
- `extract_tra.py` (44K)
- `ipo_date_candidates.csv` (24K)
- `tra_deferred_review.csv` (36K)
- `tra_events_review.xlsx` (464K)
- `tra_review_status.csv` (24K)
- `tra_panel.parquet` (100K)

Directories (9):
- `.claude/coauthor/` (4K)
- `.pytest_cache/` (36K)
- `.vscode/` (8K)
- `2025_11_notes/` (2.0G)
- `docs/` (20K)
- `findings/` (8K)
- `outputs/snapshots/` (76K)
- `scripts/__pycache__/` (24K)
- `tests/__pycache__/` (316K)

Underscore-prefixed scripts (4):
- `scripts/_enrich_deferred_urls.py` (12K)
- `scripts/_merge_decisions.py` (4K)
- `scripts/_persist_phase1.py` (12K)
- `scripts/_rename_unprefixed_dirs.py` (4K)

Queued additional (1):
- `scripts/sec_edgar/resolve_deferred_ciks.py` (20K) — defaulted to deleted `tra_deferred_review.csv`.

Tests (9): `tests/conftest.py`, `tests/test_cli.py`, `tests/test_commit.py`, `tests/test_ipo_harvest.py`, `tests/test_panel_assembly.py`, `tests/test_panel_slice.py`, `tests/test_review_writer.py`, `tests/test_terminations.py`, `tests/test_transfers.py`. `tests/__init__.py` left in place.

Total reclaimed: approximately 2.0 GB (dominated by `2025_11_notes/`).

**`.gitignore` created** at `/home/sulli/research/tra/.gitignore` with:

```
# Local caches (regenerable; out of repo)
.pixi/
.tra_history_cache/
sec-data-pqt/

# TRA corpus (321 firm directories; regenerable from EDGAR pipeline)
TRA-contracts/
```

**Database build sanity check:** `pixi run -- python scripts/build_tra_database.py` succeeded. Output:

```
tras.csv          rows=  360  cols=18  -> outputs/tra-database/tras.csv
events.csv        rows= 1635  cols=7  -> outputs/tra-database/events.csv
stock_by_date.csv rows= 8415  cols=5  -> outputs/tra-database/stock_by_date.csv
```

Row counts (360 / 1635 / 8415) match the pre-cleanup baseline. Build unaffected by deletions.

**Inventory inconsistency noted:** `inventory.md` line 43 marks `.claude/` as `keep` while line 44 marks `.claude/coauthor/` as `delete`. The recommendation column was treated as the binding decision (per the brief); `.claude/coauthor/` was removed and `.claude/` itself (which still contains `skills/` and other live state) was preserved.

**No unexpected state encountered.** All deletion targets existed at the listed paths; no permission issues; no broken references that the build script tripped over.


## 2026-05-19 — S4 (Parquet conversion): two judgment calls

**Status:** Complete. Two discretionary choices recorded below.

**1. `outputs/tra-database/dashboard.qmd` deleted as stale alternate render path.**

The plan flagged that `dashboard.qmd` (Quarto dashboard format, reads csvs, renders to `dashboard.html` via `quarto render`) and `dashboard.template.html` + `scripts/build_dashboard.py` were two coexisting paths to the same output filename. I deleted the qmd path rather than updating it to read parquet. Reasoning: (a) the shipped `dashboard.html` is produced by `build_dashboard.py`, which is what `SCHEMA.md` documents as the build path; (b) the qmd path is not invoked by any script and requires a Quarto install at render time; (c) leaving both in the repo (especially after both target the same `dashboard.html`) invites silent overwrites in the future. I also removed the `dashboard_files/` sidecar (4.3 MB of Quarto-generated libs) since it was created by the qmd render and nothing else references it (`grep -c dashboard_files` against `dashboard.html`, `dashboard.template.html`, and `build_dashboard.py` returned 0 for all three).

**2. `stock_by_date.date` cast to ISO string at build time.**

After switching to parquet, the first `build_dashboard.py` run failed with `TypeError: Object of type date is not JSON serializable`. Root cause: `build_stock_by_date()` constructs the `date` column with `pl.date_range(...)`, which yields `pl.Date`. With csv, polars round-tripped that as a string; with parquet, the dtype is preserved, and `to_dicts()` then yields `datetime.date` objects that `json.dumps` rejects. Two viable fixes: (a) cast to ISO string at build time, (b) convert in `build_dashboard.py` before `to_dicts()`. I chose (a) and added `pl.col("date").dt.strftime("%Y-%m-%d")` to `build_stock_by_date()`. Reasoning: the SCHEMA.md "Dates as ISO strings" convention applies to all four date columns across the three files; doing the cast in the build script keeps the on-disk schema consistent with `creation_date`, `termination_date`, and `events.date` (all stored as `pl.String`). SCHEMA.md's Conventions section was updated to make the build-time cast explicit.

**Row counts and file integrity:**

- `tras.parquet`: 360 rows, 18 cols, all columns `pl.String`. `cik` and `ciks` retain leading zeros.
- `events.parquet`: 1635 rows, 7 cols, all `pl.String`.
- `stock_by_date.parquet`: 8415 rows, 5 cols. `date`, `dimension`, `group_value` are `pl.String`; `count` is `pl.UInt32`; `rank` is `pl.Int64`.
- `dashboard.html`: 1,804,164 chars (prior csv build was 1,804,180 chars — 16-byte delta is identical JSON content). All three placeholder tokens (`__TRAS_JSON__`, `__EVENTS_JSON__`, `__STOCK_JSON__`) substituted.

## 2026-05-19 — S6 (Git init and private GitHub push): minor judgment calls

**Status:** Completed. Private repo created at `https://github.com/AlexSulliMora/tra-database`, single initial commit on `main` tracking `origin/main`.

**Two discretionary calls worth recording:**

1. **Added `__pycache__/` and `*.pyc` to `.gitignore`.** The plan's gitignore list (from s3) covered `.pixi/`, `.tra_history_cache/`, `sec-data-pqt/`, and `TRA-contracts/`, but not Python bytecode. The first `git add -A` staged ~15 `__pycache__/*.pyc` files under `.claude/skills/tra-htm-to-md/scripts/` and `scripts/sec_edgar/` and `scripts/tra_packet/`. These are regenerated on every Python run and should not be in the repo. Appended a "Python bytecode" block to `.gitignore`, ran `git rm -r --cached` on the staged pyc/pycache entries, then restaged. Final stage: 95 files, no bytecode.

2. **Default branch rename from `master` to `main`.** `git init` produced a `master` branch (the host's git defaults are not configured to use `main`). The plan's commit message and the `gh repo create --push` flow both assume `main`, so I ran `git branch -M main` before committing. The remote was created with `main` as the default branch in one step.

**Sensitive-data sweep result:** 30 grep hits, all benign — every match in `scripts/tra_master_cik_list_reaggregate.py` uses "token" as a query-type name ("TRA-token query", "token_rows", "token_df"), and the only other hits were `asttokens` (a Python dependency) in `pixi.lock`. No real credentials, no `.env` / `credentials.json` / `secret*` files at the project root.

**Remote tree verification:** `gh api /repos/AlexSulliMora/tra-database/contents` returned only `.claude`, `.gitignore`, `README.md`, `coauthor`, `notebooks`, `outputs`, `pixi.lock`, `pixi.toml`, `scripts`. The four gitignored paths (`TRA-contracts/`, `.pixi/`, `.tra_history_cache/`, `sec-data-pqt/`) did not leak.

## 2026-05-19 — S7a (Build `tra-find-candidates` skill): EX-10 regex broadened twice and .jpg false positives filtered

**Status:** Complete. Skill at `.claude/skills/tra-find-candidates/` with SKILL.md and `scripts/find_candidates.py`. Verification run on 2024-06 saved 88 exhibits across 17 CIKs.

**Plan said:** "filter the index LazyFrame to rows where `name` matches the `EX-10.*` pattern (case-insensitive: `^ex[-_]?10[.\-_]\d+`)."

**Two judgment calls were forced by real SEC naming conventions observed in the verification run on 2024-06:**

1. **The anchored `^ex...` regex misses two of the three common SEC naming patterns.** Empirical inspection of `index.json` payloads for the 67 union filings in 2024-06 surfaced three distinct conventions for EX-10 exhibit filenames:
   - `ex10-1.htm`, `ex-10.1.htm`, `ex_10_1.htm`, `EX-10.1.HTM` (the pattern the plan's regex anticipates).
   - `exhibit101-sx1.htm`, `exhibit1037-sx4.htm` (full "exhibit" prefix; common in S-1/S-4 filings).
   - `d846178dex101.htm`, `d537159dex1019.htm` (filer-agent prefix + `dex` infix; Donnelly Financial and other filing agents).
   The plan's regex catches only the first family. Broadened to `(?:^|[^a-z])d?ex(?:hibit)?[-_]?10[._\-]?\d` (case-insensitive). The leading word-boundary clause prevents matching mid-word `ex10` substrings; the optional `d?` prefix admits the filer-agent convention; the optional `hibit` group admits the full "exhibit" form; the trailing `[._\-]?\d` rejects EX-21, EX-23, EX-99 and other exhibit categories that share the `dex` infix. Before the broadening, the 2024-06 verification run pulled exhibits from only 1 of 67 union filings (1.5%); after, 18 of 67 (27%) — closer to the order of magnitude the plan implies ("low hundreds to low thousands ... an even smaller count carrying EX-10.*").

2. **The EX-10-named-but-image-typed false positives.** With the broadened regex, 114 of 202 pulled documents were `.jpg` files (e.g. `exhibit101-plnt2024x1xam038.jpg`) — embedded images packaged alongside the exhibit, not contract text. The classifier in s7b would mark every one "no", and the bandwidth is wasted. Added a textual-extension allow-list (`.htm`, `.html`, `.txt`) applied after the regex. Net effect: 202 → 88 exhibits in the 2024-06 verification run, all of which are text/HTML candidates plausibly worth classification.

**Other notes:**

- **`fetch_filing_index` instead of `fetch_filing`.** The plan suggested `fetch_filing(cik, adsh)` to retrieve the index LazyFrame. `fetch_filing` first calls `fetch_submissions` to resolve the primary document name, which (a) makes an extra HTTP round-trip per filing and (b) fails when the registrant's Submissions JSON does not list the accession (cross-filer or older accession edge cases). I switched to `fetch_filing_index(cik, adsh)` directly, which is one HTTP call and returns the same LazyFrame. The plan's reference to "the index.json" is preserved.
- **No biweekly halving triggered in 2024-06.** All four monthly queries returned `relation = "eq"` (raw-hit counts 69, 15, 8, 2). The defensive halving logic is present in the script but did not fire on this window.
- **Manifest schema includes form and filing_date.** The plan's manifest spec listed `filing_date,form,fts_snippet` as required columns; implemented as written.
- **`candidates/` was added to `.gitignore`** under a labelled section, after `TRA-contracts/`.

**Verification trial-run counts (2024-06):**
- raw FTS hits: 69 / 15 / 8 / 2 (per variant)
- union on `adsh`: 67 filings
- filings carrying EX-10.* text exhibits: 18
- exhibits pulled to disk: 88
- output tree: 17 CIK directories under `candidates/` plus `candidates/manifest.csv` (88 data rows).

## 2026-05-19 — Step 1 (Global full-text-search sweep): split sweep from exhibit pull, ten unrecoverable months

**Status:** Complete. `data/edgar-query/full-text.parquet` written (20,721 unique filings; `file_date` range 2004-10-12 to 2026-05-19). Stdout/stderr archived at `data/edgar-query/run.log`.

**1. Script split into sweep-only vs sweep-and-pull modes.**

Two flags added to `.claude/skills/tra-find-candidates/scripts/find_candidates.py`:

- `--no-exhibits`: skip `fetch_filing_index` + EX-10.* regex + extension allow-list + `fetch_document` + per-CIK exhibit writes + `manifest.csv` append/dedupe. The full-text-search sweep still runs.
- `--save-union-parquet PATH`: after each month's `union_month` returns, accumulate the union into a per-run list; at end-of-run, concatenate (`how="diagonal_relaxed"`) and `write_parquet(PATH)`. Parent directories are created. When the run produces zero matching filings the script writes an empty parquet with an `adsh: pl.String` schema so the artifact still exists.

`union_month` itself was minimally extended to keep `display_names`, `period_of_report`, and `file_description` in the aggregation (the original only kept five fields). The two new flags do not affect the default sweep + exhibit pull behavior; without them the script behaves exactly as before.

SKILL.md gained one paragraph in the Workflow section documenting both flags. The rest of the SKILL.md is unchanged.

**2. No bi-weekly halving fallback fired.**

`grep -c "CAP HIT" data/edgar-query/run.log` returns 0. Over all 305 month-windows (2001-01 through 2026-05) and all four phrase variants, no single monthly query came back with `meta["relation"] == "gte"`. The 10K-cap halving branch is reachable in principle (the script enters it only when a variant's monthly result count is capped at 10,000 with a `gte` relation flag); empirically, the highest per-variant monthly count in the EDGAR full-text-search corpus for these four phrases sits well below the cap. The defensive code path is present and exercised only at the unit level, not by this run.

**3. Ten month-windows hit unrecoverable HTTP 500s.**

After three retry attempts with 1.5 s back-off (per `search_with_retry`), the following months still failed and were skipped by `union_month`'s outer try/except. All ten errors are HTTP 500s from `efts.sec.gov`, not client-side issues:

| Month | Failing variant | Pagination offset |
|---|---|---|
| 2008-05 | `"tax receivable agreements"` | from=0 |
| 2008-06 | `"tax receivable agreement"` | from=0 |
| 2012-01 | `"tax receivables agreement"` | from=0 |
| 2015-11 | `"tax receivable agreement"` | from=100 |
| 2017-11 | `"tax receivables agreements"` | from=0 |
| 2019-12 | `"tax receivables agreements"` | from=0 |
| 2020-08 | `"tax receivables agreements"` | from=0 |
| 2020-11 | `"tax receivable agreement"` | from=200 |
| 2022-05 | `"tax receivable agreement"` | from=400 |
| 2022-08 | `"tax receivable agreement"` | from=0 |

When `union_month` catches an exception from a variant query it drops the entire month from the union (the loop continues to the next month), so even the variants that succeeded for that month are not contributed to the parquet. The `from=N>0` failures indicate the SEC 500'd a mid-pagination page; the earlier successful pages are still cached on disk but were not retained in this run's output. Re-running the failed months individually (`--start YYYY-MM --end YYYY-MM`) will pull from cache for already-succeeded pages and retry only the 500-failing ones; the parquet would then need to be re-built from the cache or unioned with the gap-fill run's output.

**4. Verified parquet schema.**

```
adsh: String
primary_doc: String
ciks: List[String]
form: String
display_names: List[String]
file_date: String
snippet: Null
phrase_variants_matched: String
period_of_report: Null
file_description: String
```

`snippet` and `period_of_report` came through as fully null (typed `Null` by polars because no row carried a non-null value). The EDGAR full-text-search hit body's `snippet` field is populated when a `q=` query uses the loose word match; with phrase queries (the four `"..."` variants) the API returns hits without snippets. `period_of_report` is populated for periodic-report forms but not for the registration / current-report forms that dominate TRA-mentioning filings. `display_names` carries the registrant + filer-agent name strings. `ciks` preserves leading zeros as required by the contract.

---

## 2026-05-19 — S7a update: skill-to-script refactor

The original S7a plan specified building a Claude Code skill at `.claude/skills/tra-find-candidates/` (with `SKILL.md` plus `scripts/find_candidates.py` under it). On review, the work is deterministic: no agent navigation, no LLM judgment, no per-firm reasoning. It is a plain Python sweep over EDGAR full-text search followed by a plain Python download of EX-10.* exhibits. Packaging it as a skill added a `SKILL.md` instructions wrapper around what should be two CLI scripts.

This step refactors S7a's output to two plain scripts under `scripts/`:

- `scripts/find_candidates.py`: simplified to sweep-only. Removed `extract_ex10_documents`, `download_exhibits`, `append_manifest`, `dedup_manifest`, and the `--no-exhibits` flag (sweep-only is now the sole behavior). `--save-union-parquet` defaults to `data/edgar-query/full-text.parquet`. The retry / 10K-cap halving / month-iter / biweekly-bounds logic is preserved verbatim.
- `scripts/pull_exhibits.py`: new companion script. Reads a parquet of filings (default `data/edgar-query/full-text.parquet`), fetches each filing's `index.json`, filters to EX-10.* text exhibits (regex and extension allow-list lifted into the script directly), and downloads to `data/edgar-query/exhibits/<CIK>/<accession>_<filename>`. Idempotent on disk; writes a `manifest.csv` keyed on `(cik, accession, filename)`. Flags: `--parquet`, `--output-dir`, `--limit`.
- Deleted `.claude/skills/tra-find-candidates/` entirely.
- Updated `README.md`: the Workflow grew from seven steps to eight (the old step 1 "Collect a CIK seed list" became two scripted steps for the sweep + exhibit pull). The skill catalog table never carried `tra-find-candidates`, so no row deletion was needed. Renumbered the existing steps 2-7 to 3-8 and updated all in-text step references.

`ca-02-plan.md`'s S7a entry still describes the skill form; an amendment pass will bring the plan in line with the scripts. This deviation note is the bridge.

**Trial run.**

```
PYTHONPATH=scripts pixi run python scripts/find_candidates.py \
  --start 2024-06 --end 2024-06 \
  --save-union-parquet data/edgar-query/trial-2024-06.parquet
```

returned 67 unique-adsh rows (raw hits: 69 / 15 / 8 / 2 across the four phrase variants). 

```
PYTHONPATH=scripts pixi run python scripts/pull_exhibits.py \
  --parquet data/edgar-query/trial-2024-06.parquet \
  --output-dir data/edgar-query/trial-exhibits --limit 25
```

returned 32 exhibits downloaded across 5 of the 25 filings (the other 20 had zero EX-10.* text documents in their indexes). The 5 productive filings exercised all three filename conventions covered by the regex: the `d...dex10X.htm` filer-agent convention dominated, with `exhibit101-<name>.htm` also appearing. The initial `--limit 5` produced zero downloads because none of the first five filings carried an EX-10.* text exhibit, which is just a fact about the parquet's row order rather than a script defect. Trial outputs (`data/edgar-query/trial-2024-06.parquet`, `data/edgar-query/trial-exhibits/`) were deleted after verification. The real `data/edgar-query/full-text.parquet` (22,251 rows) was not touched.
