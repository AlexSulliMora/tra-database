---
name: tra-classify
description: >-
  Three-way deterministic classifier for SEC EX-10.* documents. Decides whether
  each document is a Tax Receivable Agreement (TRA) contract, a clearly-non-TRA
  document, or genuinely uncertain (routed to the tra-reviewer Claude subagent
  for a second-tier verdict, escalated to the user if still ambiguous). Use this
  skill when a task requires turning a pull of EX-10 candidate exhibits into a
  classifications.csv that downstream pipeline steps (tra-download-filings,
  tra-refresh) consume as the confirmed-TRA set. Typical triggers: "classify the
  EX-10 documents we pulled", "run the TRA classifier", "rebuild the
  classifications CSV for the current corpus".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# TRA Classify Skill

The `tra-classify` skill turns a directory of SEC EX-10.* documents into a row-per-document CSV with one of `yes` / `no` / `uncertain` per document, plus the deterministic signals that produced the decision. It is the first tier of a three-tier review pipeline: this classifier emits the verdict deterministically when signals are conclusive, routes ambiguous documents to the `tra-reviewer` Claude subagent (second tier, via `--mode review-uncertain`), and surfaces unresolved cases to the user (third tier) via the `needs_a1_review` column.

The classifier exists because phrase presence alone (the original `tmp/TRA-classify/` approach) conflates "mentions a TRA" with "is a TRA" — LLC agreements, credit agreements, registration-rights agreements, and 8-K item descriptions all reference TRAs without being one. The discriminating signal is the centered document title reading "TAX RECEIVABLE AGREEMENT". This skill encodes that distinction.

## Universal constraints

- **Pixi only.** Run via `pixi run -- python .claude/skills/tra-classify/scripts/classify.py ...`. Do not invoke bare `python`.
- **Bounded reads (WSL safety).** Documents are read in two windows: a leading ~80 KB title-block window for the centered-title detection, and a leading ~400 KB scan window for phrase / defined-term presence. Documents larger than these windows are not read fully; the classifier never opens a full document into memory.
- **Polars lazy-first.** Inputs and outputs use polars; the manifest at `data/edgar-query/exhibits/manifest.csv` is read as a LazyFrame and filtered before materialization.
- **Random seed from date.** The skill sets `SEED = int(date.today().strftime("%Y%m%d"))` per the project convention; no sampling currently uses it but it is set for any future stratified review work.
- **Fail loudly.** Malformed input (missing manifest, unreadable document, invalid forced-uncertain entry) raises an exception rather than silently dropping the document.

## Inputs

| Parameter | Type | Notes |
|---|---|---|
| `--input-dir` | path | Directory of EX-10 documents organized as `<CIK>/<accession>_<filename>`. Default: `data/edgar-query/exhibits/`. |
| `--output-csv` | path | Where to write per-document classifications. Default: `data/edgar-query/classifications-v<N>.csv` where N is the `--classifier-version` value. |
| `--classifier-version` | int | Iteration number; stamps every row's `classifier_version` column. Required for `--mode classify` and `--mode review-uncertain`; auto-resolved from `classifier_acceptance.md` (last `status=accepted` line) for `--mode finalize` unless overridden. |
| `--forced-uncertain` | path | CSV listing documents that should be routed to `uncertain` regardless of signal output. Default: `data/edgar-query/forced_uncertain.csv`. Empty header-only file is fine; the escape hatch fires only when a row matches. |
| `--mode` | `classify\|review-uncertain\|finalize` | What subcommand to run. `classify` (default) emits the deterministic verdicts; `review-uncertain` calls the `tra-reviewer` Claude subagent on `classification=uncertain` rows; `finalize` re-runs the accepted classifier end-to-end and emits `classifications.csv` with uniform `classifier_version`. |
| `--manifest` | path | Manifest from `pull_exhibits.py`. Default: `data/edgar-query/exhibits/manifest.csv`. Used to resolve `(cik, accession, filename)` from each on-disk file. |

## Outputs

```
data/edgar-query/
├── classifications-v<N>.csv   # one row per document; written by --mode classify
├── classifications.csv        # symlinked (or copied) to the accepted version by --mode finalize
├── a4_verdicts_cache.csv      # content-hash → A4 verdict cache; appended by --mode review-uncertain
├── classifier_acceptance.md   # flat append-only log of acceptance events
└── forced_uncertain.csv       # user-curated escape hatch (yours to edit)
```

`classifications-v<N>.csv` columns:

| Column | Type | Notes |
|---|---|---|
| `cik` | string | 10-digit zero-padded; matches the `<CIK>/` directory under `data/edgar-query/exhibits/`. |
| `accession` | string | Filing accession with dashes (e.g., `0001104659-19-001234`); matches the filename prefix on disk. |
| `filename` | string | The EX-10 document filename (no path). |
| `classification` | string | One of `yes`, `no`, `uncertain`. |
| `classifier_version` | int | The `--classifier-version` value used. |
| `signals_matched` | string | Pipe-delimited signal names (e.g., `centered_title|phrase|defined_term_realized_tax_benefit`). Empty when no signals matched. Special value `forced_uncertain` indicates the document was on the override list. |
| `needs_a1_review` | bool | True when the row needs A1 (user) attention: ERROR_* reviewer verdicts, or A4 contradiction of a prior A1 correction. Empty initially; populated by `--mode review-uncertain` and during F2 iteration. |
| `escalation_reason` | string | One-line reason populated alongside `needs_a1_review=true`. Empty otherwise. |
| `reviewer_verdict` | string | One of `yes`, `no`, `ERROR_UNAVAILABLE`, `ERROR_MALFORMED`. Empty until `--mode review-uncertain` runs on this row. |
| `reviewer_rationale` | string | One-sentence rationale from the A4 subagent. Empty until `--mode review-uncertain` runs. |

## Workflow

### Step 1: --mode classify

Inputs: `--input-dir`, `--manifest`, `--classifier-version`, `--forced-uncertain`, `--output-csv`.

For each file under `--input-dir`:

1. Resolve `(cik, accession, filename)` from the manifest.
2. If the row is already present in `--output-csv` (resume-on-interrupt), skip.
3. If `(cik, accession, filename)` is on the forced-uncertain list, emit `classification=uncertain`, `signals_matched=forced_uncertain`, advance.
4. PDF documents (`.pdf` extension) are routed to `classification=uncertain`, `signals_matched=pdf_no_text` — no in-skill text extraction.
5. Otherwise, read the bounded title window (80 KB) and bounded scan window (400 KB). Score the document on the signals defined in `references/signal-catalog.md` for the current `--classifier-version`.
6. Apply the classification rule (deterministic, version-stamped in the signal catalog) to produce `yes` / `no` / `uncertain` and the `signals_matched` string.
7. Append the row to `--output-csv` immediately (incremental write enables resume).

### Step 2: --mode review-uncertain

Inputs: `--output-csv` (from Step 1), `--cache-csv` (default `data/edgar-query/a4_verdicts_cache.csv`).

For each row where `classification=uncertain` and `reviewer_verdict` is empty:

1. Compute SHA-256 content hash of the document.
2. Look up the hash in the A4 verdict cache. On hit: copy the cached `reviewer_verdict` and `reviewer_rationale` to the row.
3. On miss: dispatch the `tra-reviewer` custom subagent (`.claude/agents/tra-reviewer.md`) with the document text (bounded read). Parse the JSON response `{verdict, rationale}`. On success: write to the row AND append to the cache.
4. Retry policy: 3 retries with exponential back-off on transient failure (network, HTTP 429/5xx). After persistent failure, set `reviewer_verdict=ERROR_UNAVAILABLE`, `needs_a1_review=true`, `escalation_reason=A4 unavailable after 3 retries`.
5. Validation: malformed JSON (verdict outside `{yes, no}`, missing rationale) → 1 retry with corrective message. After persistent failure, set `reviewer_verdict=ERROR_MALFORMED`, `needs_a1_review=true`, `escalation_reason=A4 returned malformed output twice`.
6. A4-vs-A1 contradiction: if A4's verdict on a previously-A1-corrected document contradicts A1's correction, set `needs_a1_review=true`, `escalation_reason=A4 contradicts prior A1 correction`.

### Step 3: --mode finalize

Inputs: `classifier_acceptance.md` (or `--classifier-version N`), `--input-dir`, `--manifest`.

1. Determine the accepted `classifier_version`: read the last `status=accepted` line from `classifier_acceptance.md` for the version, OR use the `--classifier-version N` CLI override (skips parsing).
2. Run `--mode classify` end-to-end against `--input-dir` with that version. Output: `data/edgar-query/classifications-v<N>.csv`.
3. Run `--mode review-uncertain` against the output. All cache lookups should hit (this is the accepted set; the cache is frozen for it).
4. Verify uniform `classifier_version` across all rows; halt loudly if violated.
5. Symlink (or copy if symlinks aren't supported on the platform) `classifications-v<N>.csv` to `classifications.csv` (the canonical R11 input).

## Running the skill

End-to-end iteration round:

```bash
# Step 1: classify all documents under iteration 1
pixi run -- python .claude/skills/tra-classify/scripts/classify.py \
  --mode classify \
  --input-dir data/edgar-query/exhibits/ \
  --output-csv data/edgar-query/classifications-v1.csv \
  --classifier-version 1

# Step 2: dispatch A4 on uncertain rows
pixi run -- python .claude/skills/tra-classify/scripts/classify.py \
  --mode review-uncertain \
  --output-csv data/edgar-query/classifications-v1.csv

# After user accepts iteration 1 (sign-off in classifier_acceptance.md):

# Step 3: finalize the accepted version
pixi run -- python .claude/skills/tra-classify/scripts/classify.py \
  --mode finalize \
  --classifier-version 1
```

For a single-document trial:

```bash
pixi run -- python .claude/skills/tra-classify/scripts/classify.py \
  --mode classify \
  --input-dir /tmp/trial-docs/ \
  --output-csv /tmp/trial-classifications.csv \
  --classifier-version 1
```

## What this skill does not do

- Does not call the A4 Claude subagent itself in `--mode classify`. Calling A4 is `--mode review-uncertain`'s job. This separation lets the deterministic pass run cheaply many times during iteration, with A4 dispatches only on the rows that need them.
- Does not extract text from PDF documents. PDFs are routed to `uncertain` without scoring; the A4 reviewer reads the PDF content via its own tooling if needed.
- Does not move or rename input documents. The skill is operationally read-only with respect to `data/edgar-query/exhibits/`.
- Does not write to `classifications.csv` directly. Only `--mode finalize` produces that file (via symlink to the accepted version).
- Does not invoke any external API (EDGAR, third-party). All signals are computed locally from document bytes.

## Troubleshooting

- **"Manifest row not found"** — A document on disk is not in `manifest.csv`. Either the manifest is stale (re-run `pull_exhibits.py`) or the file was added by hand outside the pipeline. The classifier halts loudly rather than silently classifying without a known `(cik, accession)`.
- **"Resume detected N rows already in output"** — The classifier is resuming an interrupted run. Verify the existing rows are from the same `--classifier-version`; if not, the output is corrupt and should be deleted before re-running.
- **"forced_uncertain.csv malformed"** — The override CSV must have header `cik,accession,filename,reason`. Empty file (header only) is valid.
- **A4 dispatch fails repeatedly** — Check that `.claude/agents/tra-reviewer.md` exists and was registered (a Claude Code session restart is required after creating or editing the agent file).
