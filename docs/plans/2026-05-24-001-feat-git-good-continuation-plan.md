---
title: "feat: Finish the git-good TRA-pipeline cleanup project"
type: feat
status: active
date: 2026-05-24
origin: docs/brainstorms/git-good-continuation-requirements.md
---

# feat: Finish the git-good TRA-pipeline cleanup project

## Summary

Execute the remaining work for the in-flight git-good TRA-pipeline cleanup in four sequential phases: verify the already-completed S1–S6 work and rewrite the README to match the post-S7a per-document EDGAR rework; develop a new `tra-classify` skill through iterative human-in-the-loop dialogue with a Claude reviewer subagent for uncertain documents; execute S7c–S8 (narrowed `tra-download-filings`, markdown-read `tra-process-filings`, retired `tra-packet`, relocated skill-internal scripts, new `tra-refresh` skill, systematic rerun); migrate to Windows as the replicability test before the WSL tree is deleted.

---

## Problem Frame

The git-good project reached S7a partially when the prior session ended; the EDGAR acquisition was reworked into a per-document shape that diverged from the frozen plan, and the classification step built in `tmp/TRA-classify/` was rejected because phrase-presence does not discriminate TRA contracts from documents that mention TRAs. Several upstream steps (S2 skill relocation, S6 GitHub push, S4 parquet conversion) were marked complete but not re-verified, the README still describes the retired per-filing acquisition path and the doomed `tra-packet` skill, and `scripts/sec_edgar/` plus `scripts/tra_download.py` were never relocated despite the brainstorm assuming they were. The two priorities for this corpus — correct TRA classification and fresh-clone replicability for academic publication — both require the open items resolved before the systematic rerun (S8) can produce a corpus anyone trusts. See `docs/brainstorms/git-good-continuation-requirements.md` for the full requirements detail.

---

## Requirements

- R1. Re-execute the database and dashboard builds from the cleaned tree and confirm the recorded parquet row counts (360 / 1635 / 8415) plus a rendering `dashboard.html`.
- R2. Verify the six skills are present at `.claude/skills/` and absent from `~/.claude/skills/`.
- R3. Verify the GitHub push outcome (private remote at `AlexSulliMora/tra-database`, no `TRA-contracts/` on the remote, no credentials in committed files).
- R4. Resolve the silent-deletion record for `scripts/sec_edgar/resolve_deferred_ciks.py` by restoring the file or amending `coauthor/2026-05-18-git-good/inventory.md`, after grepping the working tree for callers.
- R5. Resolve the `tra-packet/SKILL.md` reference to deleted `tra_deferred_review.csv` (folds into S7e in Phase C; no F1 work needed beyond awareness).
- R6a. Rewrite `README.md` for the per-document EDGAR acquisition; remove references to the three-query union and the allow-list post-filter.
- R6b. After S7e retires `tra-packet`, remove the catalog entry and sweep remaining references.
- R7. Install `tra-classify` as a project-local skill at `.claude/skills/tra-classify/`, auto-loaded by Claude Code and invokable as a standalone deterministic program.
- R8. The skill emits exactly one of {yes, no, uncertain} per EX-10 document and writes `data/edgar-query/classifications.csv` with `cik, accession, filename, classification, classifier_version, signals_matched`.
- R9. When classification is `uncertain`, the Claude reviewer subagent (A4) reads the document and writes `reviewer_verdict ∈ {yes, no}` plus a one-sentence `reviewer_rationale` to the same row.
- R10. On user-reported misclassification at iteration N, classifier version N+1 either classifies correctly or routes to `uncertain` where A4 agrees with the user; if A4 contradicts the user, the disagreement escalates back to the user. The accepted version is recorded in `data/edgar-query/classifier_acceptance.md`.
- R11. The confirmed-TRA-document set is the union of A3-yes rows and A3-uncertain rows with `reviewer_verdict = yes`; the confirmed-TRA-CIK list is the unique CIK set across that document set. The accepted classifier is re-run end-to-end over the full corpus before the union is computed (uniform `classifier_version` across rows).
- R12. The rewritten `tra-download-filings` takes the confirmed-TRA-CIK list and pulls only filings of form `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}` plus their exhibits; IPO-prospectus selection rule preserved.
- R13. S7d (process-filings markdown read), S7e (tra-packet retired), S7f (skill-internal scripts relocated) execute per the brainstorm.
- R14. `tra-refresh` reads the prior cutoff from `outputs/tra-database/last_refresh.json` (or falls back to the max `file_date` in `data/edgar-query/full-text.parquet` when missing), uses the same narrow form set as R12, supports `--dry-run`, and calls `tra-classify` on any new EX-10 candidates.
- R15. The S8 systematic rerun produces fresh parquet outputs, regenerated `dashboard.html`, and a baseline `last_refresh.json` written by the live `tra-refresh` run at the end.
- R16a. After S8 commits and pushes, a `git clone` on Windows + `pixi install` + pipeline rerun produces parquet row counts matching the WSL build (within `tra-refresh`-delta tolerance when applicable).
- R16b. After R16a passes and the user accepts the S8-regenerated `classifications.csv`, the WSL tree may be deleted at user discretion.

**Origin actors:** A1 (User), A2 (Coder agent), A3 (Classify skill), A4 (Claude reviewer subagent — implemented as a custom agent at `.claude/agents/tra-reviewer.md` per the user's standing preference for judgment-heavy custom agents).

**Origin flows:** F1 (Deep verification), F2 (Classifier iteration loop), F3 (Remaining pipeline + migration).

**Origin acceptance examples:** AE1 (covers R1), AE2 (covers R8, R9), AE3 (covers R10), AE4 (covers R14), AE5 (covers R16a).

---

## Scope Boundaries

- Carrying-values / TRA-liability time series remain deferred (origin out-of-scope, prior project's S6 successor work).
- No analytical changes to the dashboard beyond pointing it at refreshed parquet inputs.
- Academic paper drafting is out of scope.
- Migration of prior coauthor artifacts (`coauthor/2026-05-18-git-good/ca-*.md`, prior project subfolders) into compound-engineering shape is out of scope.
- Public release of the GitHub repository (stays private).
- No formal pytest harness is added. The `tests/` directory was removed in S3 and remains absent. Test scenarios documented per-unit serve as the implementer's checklist; verification is "run the pipeline and inspect outputs."
- Widening the S7c form set beyond `{8-K, 10-K, 424B1-5}` (10-Q, proxies, S-1, etc.). The narrow set is preserved from the frozen prior plan; widening would require an amendment loop back to ce-brainstorm.

### Deferred to Follow-Up Work

- Seeding `docs/solutions/` with the F1 / F2 / F3 learnings the project will accumulate (analyst-recommended; cheap, post-publication maintenance work).
- F2 iteration upper cap and F1-vs-F3 row-count drift tolerance (deferred to implementation per the Open Questions section below).

---

## Context & Research

### Relevant Code and Patterns

- **Skill house style:** `.claude/skills/sec-edgar/SKILL.md`, `.claude/skills/tra-download-filings/SKILL.md`, `.claude/skills/tra-build-timeline/SKILL.md`. YAML frontmatter (`name`, `description`, optional `allowed-tools`), body sections in order: `## Purpose`, `## Universal constraints`, `## Inputs`, `## Outputs`, `## Workflow` with numbered `### Step N:` subsections, `## Running the skill`, `## What this skill does not do`, optional `## Troubleshooting`. New `tra-classify` and `tra-refresh` skills follow this shape.
- **sec_edgar public API:** `scripts/sec_edgar/__init__.py` exports `fetch_submissions`, `list_filings_by_form`, `fetch_filing`, `fetch_filing_index`, `fetch_document`, `search_filings`. `EdgarClient` (`scripts/sec_edgar/client.py`) enforces 10 req/sec via token bucket. Passing `forms=` with slash-bearing codes silently returns 0 hits — omit `forms` and post-filter.
- **Per-document EDGAR shape:** `scripts/find_candidates.py` and `scripts/pull_exhibits.py` produce one row per matched EX-10 document; columns include `adsh, primary_doc, ciks, form, file_type, file_date`. The classifier and `tra-refresh` operate on the same shape.
- **Parquet schema preservation:** `scripts/build_tra_database.py` carries `cik_from_firm_slug` (regex against trailing `_<10-digit>`) and the convention to keep `cik` / `ciks` as `pl.String` with 10-digit zero-padding. CIK list handling in F2 and F3 must preserve this end-to-end.
- **Prior classifier (rejected):** `tmp/TRA-classify/SKILL.md` and `tmp/TRA-classify/scripts/classify_tras.py`. Keep: bounded reads (80 KB title window, 400 KB scan window), random seed from date, .htm/.html/.txt/.pdf extension handling. Drop: phrase-presence keep rule (the conceptual flaw), stale headline numbers, two-variant regex.
- **Frozen prior plan:** `coauthor/2026-05-18-git-good/ca-02-plan.md` — S7c–S8 specifications carried forward.

### Institutional Learnings

- None. `docs/solutions/` does not exist for this project; the only solutions tree under `~/research/` (etf-claude) contains one unrelated entry. Capturing F1 / F2 / F3 learnings is deferred follow-up work.

### External References

- Not used — local patterns are sufficient for every unit in this plan. External pixi-Windows documentation is consulted at execution time during U14 if the install attempt fails.

---

## Key Technical Decisions

- **A4 (Claude reviewer subagent) as a custom agent definition.** Implemented at `.claude/agents/tra-reviewer.md` with `model: claude-opus-4-7` and the `tra-classify` skill preloaded, per the user's standing preference (`feedback_judgment_tasks_custom_agent.md`). The custom agent is the per-invocation verdict-producing endpoint: each dispatch produces one JSON `{verdict, rationale}` for one document and holds no persistent state between calls. The dispatch driver — `classify.py --mode review-uncertain` — owns the A4 verdict cache (`data/edgar-query/a4_verdicts_cache.csv`), the retry / error-marker logic, and the cache-hit-vs-fresh-dispatch decision. Alternative (per-document ad-hoc `Agent` dispatches outside the driver) was rejected because it scatters cache logic and re-loads the SKILL.md on every dispatch.
- **A4 verdict caching: hybrid.** F2 acceptance freezes A4's verdicts on the 3,025-document set (cache file committed to the repo, keyed on document content hash). `tra-refresh` reads the cache for known documents (deterministic) and makes fresh A4 calls for new EX-10 candidates (some non-determinism on new documents only, bounded by the refresh delta). Per user decision in Phase 2.
- **Irreducibly-ambiguous escape: hardcoded `forced_uncertain.csv`.** Documents the deterministic classifier cannot resolve without reading the body get listed in `data/edgar-query/forced_uncertain.csv` keyed on `(cik, accession, filename)`; the classifier routes them to `uncertain` regardless of signals, where A4 (and ultimately A1) handles them. Per user decision in Phase 2.
- **`classifications.csv` versioning per iteration.** Each iteration writes `data/edgar-query/classifications-v<N>.csv`. The accepted version is symlinked (or copied) to `data/edgar-query/classifications.csv`. Diff between consecutive iterations is computable; A1's spot-review at iteration N+1 has the prior round's verdicts available.
- **Resume-on-interrupt for the classifier run.** The classifier writes the per-row output incrementally; a restart over a partially-populated `classifications-v<N>.csv` resumes from the last processed row, keyed on `(cik, accession, filename, classifier_version)`. Matches the idempotency property the prior S7b plan required for manual classification.
- **A4 retry policy.** Three retries with exponential back-off on transient failure (network, rate limit). On persistent failure: row marked `reviewer_verdict = ERROR_UNAVAILABLE` and treated as escalated to A1. On malformed output (verdict outside `{yes, no}`, missing rationale): one retry, then `reviewer_verdict = ERROR_MALFORMED` and escalate. The user-global rule "fail loudly over failing quietly" anchors this.
- **F3 dependency DAG (explicit, not `parallel-with`).** S7c → S7f (S7c edits `scripts/tra_download.py`, S7f relocates it). S7d and S7e are independent of S7c / S7f. S7g depends on all four plus F2's `tra-classify`. S8 depends on everything. The frozen plan's loose `parallel-with` column is tightened here.
- **htm-to-md ordering: drop the "move to TRA-*/" step from `tra-process-filings`.** Have `tra-htm-to-md` operate on `<accession>/` exclusively, then `tra-process-filings` reads markdown from there. The frozen plan flagged the two-pass htm-to-md hack as one option; this is the cleaner alternative. Reconciles G9 from the flow analysis.
- **README updates split across phases.** F1's R6a rewrite covers the acquisition / workflow section (the part affected by S7a's rework) but does not touch the skill catalog. F2 closes with a one-line skill-catalog insertion for `tra-classify`. F3's S7e closes with a skill-catalog removal of `tra-packet` and insertion of `tra-refresh`. This keeps the README accurate to the working-tree state at every phase boundary.
- **`last_refresh.json` fallback source.** When `last_refresh.json` is missing, `tra-refresh` falls back to the max `file_date` in `data/edgar-query/full-text.parquet` (the per-document acquisition output), not `events.parquet`. The latter carries timeline-bullet dates from the YAML body, which are not filing dates. **Deviation from origin:** the origin's R14 specifies `events.parquet`'s `filingDate` column; that column does not exist in `events.parquet` (verified). The plan-canonical source is `data/edgar-query/full-text.parquet`'s `file_date` column (verified present). R14 in this plan reflects the corrected reference.
- **`pixi.toml` platforms edit pulled into Phase A.** The current manifest pins `platforms = ["linux-64"]`; Windows reproducibility (R16a) requires adding `win-64`. U2's verification pass does the edit and runs `pixi install` to regenerate the cross-platform lockfile; surfaced-and-fixed early rather than discovered at migration.
- **WSL deletion gate has three preconditions, not one.** R16b is gated on: (i) R16a Windows reproducibility passes, (ii) A1 signs off on the S8-regenerated `classifications.csv` (re-acceptance step), (iii) F2 is closed (no pending classifier revisions from the S8 reveal). Rollback shape if any precondition fails: revert the S8 commit, re-enter F2 with the new corpus, re-run S8 after re-acceptance, force-push to GitHub (chosen over revert-commit for cleaner history; this is the only commit on the repo besides the baseline).

---

## Open Questions

### Resolved During Planning

- **A4 determinism across refresh runs:** Hybrid cache (Phase 2 user decision).
- **Irreducibly-ambiguous documents:** Hardcoded `forced_uncertain.csv` (Phase 2 user decision).
- **A4 malformed output:** Retry once, then `ERROR_MALFORMED` and escalate to A1.
- **A4 transient unavailability:** Three retries with exponential back-off, then `ERROR_UNAVAILABLE` and escalate.
- **classifications.csv persistence across iterations:** Per-iteration files; symlink to accepted.
- **Resume on interrupt:** Incremental writes + idempotent restart keyed on `(cik, accession, filename, classifier_version)`.
- **F3 dependency DAG:** S7c → S7f; S7d, S7e independent; S7g depends on F2 + all S7 prior; S8 depends on everything.
- **htm-to-md ordering:** Drop "move to TRA-*/" from process-filings; htm-to-md operates on `<accession>/` only.
- **README sequencing:** Split across phases (R6a in F1, skill catalog updates in F2 and F3).
- **`tra-classify` ↔ `tra-refresh` API contract:** CLI takes `--input-dir <path>` (directory of EX-10 documents) and `--output-csv <path>` (where to write classifications). `tra-refresh` calls `tra-classify --input-dir data/edgar-query/exhibits-refresh-<date>/ --output-csv data/edgar-query/classifications-refresh-<date>.csv`.
- **`last_refresh.json` fallback:** Max `file_date` from `data/edgar-query/full-text.parquet`.
- **WSL deletion preconditions:** Three gates (R16a, S8 corpus re-acceptance, F2 closed).
- **S8 rollback shape:** Force-push to GitHub (clean history; minimal commits on the repo).
- **pixi.toml platforms edit:** Pulled forward to Phase A.

### Deferred to Implementation

- **F1 vs F3 dashboard row-count drift tolerance.** Default: same order of magnitude (per the frozen plan's S8 check). Tighter threshold can be set during execution if a strict baseline matters.
- **F2 iteration upper cap.** No hard cap; the F2 stopping rule (user sign-off on a stable sample) provides natural termination. If the loop appears non-convergent during execution, A2 surfaces the situation for a user-decision.
- **Initial v0 classifier signals beyond centered title.** Discovered during F2 iteration by sampling confirmed TRAs and non-TRAs. Starting set: centered-title detection for "TAX RECEIVABLE AGREEMENT" (any case), four-variant phrase presence (singular + plural × receivable + receivables), defined-term presence (`Exchange Basis Adjustment`, `Realized Tax Benefit`, `Tax Asset`), signature-block presence. Refined per iteration.
- **A4 calibration sample size for iteration 1.** Default: A1 reviews 100% of A4's verdicts in iteration 1, measures agreement, adjusts policy for subsequent iterations. Specific sample size only matters if iteration 1 has > ~200 uncertain documents.
- **Confirmed-TRA-CIK list granularity (per-CIK vs per-(CIK, accession)).** Default: per-CIK for the S7c download (mirrors the frozen plan). If a CIK has both true and false TRA documents attributed and the false-positive's filings are pulled, address by tightening to per-(CIK, accession) during execution.
- **Windows reproducibility test shape (origin R16a footnote).** Decide whether U14 runs the live `tra-refresh` step (accept row-count delta documented in `last_refresh.json`) or rebuilds strictly from existing on-disk exhibits (strict row-count match). The origin's R16a footnote names this as the question that settles which mode is canonical for AE5; the plan defers the choice to U14 execution. Default if unspecified at execution time: live `tra-refresh` with the delta documented, since it exercises more of the pipeline.

---

## Output Structure

New files this plan creates (existing structure not shown):

```
.claude/
├── agents/
│   └── tra-reviewer.md           # A4 custom agent definition
└── skills/
    ├── tra-classify/             # F2 deliverable
    │   ├── SKILL.md
    │   ├── references/
    │   │   └── signal-catalog.md  # signals the classifier checks (versioned)
    │   └── scripts/
    │       └── classify.py
    ├── tra-refresh/              # F3 deliverable (S7g)
    │   ├── SKILL.md
    │   └── scripts/
    │       └── refresh.py
    ├── sec-edgar/
    │   └── scripts/
    │       └── sec_edgar/         # relocated from scripts/sec_edgar/ (S7f)
    └── tra-download-filings/
        └── scripts/
            └── tra_download.py    # relocated from scripts/ (S7f)
data/
└── edgar-query/
    ├── classifications-v1.csv    # per-iteration; final accepted symlinked to classifications.csv
    ├── classifications.csv       # symlink to accepted version
    ├── classifier_acceptance.md  # versions + user sign-off log
    ├── a4_verdicts_cache.csv     # content-hash → verdict cache (frozen on F2 acceptance)
    └── forced_uncertain.csv      # (cik, accession, filename) escape-hatch list
outputs/
└── tra-database/
    └── last_refresh.json         # written by tra-refresh at end of S8
docs/
└── plans/
    └── 2026-05-24-001-feat-git-good-continuation-plan.md  # this file
```

The implementer may adjust the structure if implementation reveals a better layout; per-unit `Files` sections remain authoritative.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Phase structure and dependencies:**

```{mermaid}
flowchart TD
    subgraph PhaseA["Phase A — Verify & cleanup (F1)"]
        U1[U1: Build pipeline rerun]
        U2[U2: Skill + remote + pixi-platforms verification]
        U3[U3: R4 resolve_deferred_ciks.py disposition]
        U4[U4: R6a README rewrite]
    end
    subgraph PhaseB["Phase B — Classifier development (F2)"]
        U5[U5: tra-classify skill scaffold]
        U6[U6: A4 custom agent + cache]
        U7[U7: Iteration mechanics + acceptance]
        U7B[F2 iteration runs until A1 accepts]
    end
    subgraph PhaseC["Phase C — Remaining pipeline (F3 part 1)"]
        U8[U8: S7c rewrite tra-download-filings]
        U9[U9: S7d process-filings markdown read]
        U10[U10: S7e retire tra-packet]
        U11[U11: S7f relocate skill-internal scripts]
        U12[U12: S7g build tra-refresh]
        U13[U13: S8 systematic rerun]
    end
    subgraph PhaseD["Phase D — Windows migration (F3 part 2)"]
        U14[U14: R16a Windows clone + reproducibility test, R16b WSL deletion]
    end
    PhaseA --> PhaseB
    PhaseB --> PhaseC
    U8 --> U11
    U8 --> U12
    U9 --> U12
    U10 --> U12
    U11 --> U12
    U12 --> U13
    PhaseC --> PhaseD
```

**F2 classifier iteration loop (per round):**

```{mermaid}
flowchart LR
    Start[Start round N] --> A3[A3: classify all 3025 docs]
    A3 --> Yes[yes rows]
    A3 --> No[no rows]
    A3 --> Unc[uncertain rows]
    Unc --> A4[A4 reviewer subagent]
    A4 --> A4Yes[A4 verdict: yes]
    A4 --> A4No[A4 verdict: no]
    A4 --> A4Err[ERROR_MALFORMED or ERROR_UNAVAILABLE]
    Yes --> Sample[A1 spot-reviews sample]
    No --> Sample
    A4Yes --> Sample
    A4No --> Sample
    A4Err --> A1Esc[A1 must resolve]
    Sample --> Decide{Misclassifications?}
    A1Esc --> Decide
    Decide -->|Yes| A2Revise[A2 revises classifier → round N+1]
    Decide -->|No| Accept[A1 signs off; freeze classifier_version; freeze A4 cache]
```

---

## Implementation Units

### U1. Re-run build pipeline; verify parquet row counts

**Goal:** Confirm the database and dashboard builds reproduce the recorded outputs from the cleaned tree.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: none (verification only)
- Read: `scripts/build_tra_database.py`, `scripts/build_dashboard.py`, `outputs/tra-database/{tras,events,stock_by_date}.parquet`, `outputs/tra-database/dashboard.html`

**Approach:**
- Execute `pixi run -- python scripts/build_tra_database.py` and capture the row-count output.
- Execute `pixi run -- python scripts/build_dashboard.py` and verify `outputs/tra-database/dashboard.html` is regenerated.
- Compare row counts against the recorded baseline (`tras=360`, `events=1635`, `stock_by_date=8415`).
- Spot-check parquet column dtypes (`cik` and `ciks` should remain `pl.String` with leading zeros preserved).

**Patterns to follow:**
- Build pipeline invocation per `coauthor/2026-05-18-git-good/ca-03-deviations.md` (the prior S3 sanity check followed the same shape).

**Test scenarios:**
- Happy path: `build_tra_database.py` exits 0; output reports `tras=360 events=1635 stock_by_date=8415`.
- Happy path: `build_dashboard.py` exits 0; `dashboard.html` is regenerated within seconds of the run.
- Edge case: column dtypes hold — `pl.read_parquet("outputs/tra-database/tras.parquet").schema["cik"]` is `Utf8` (or `String` in current Polars); sample `cik` value retains 10-digit zero-padding.

**Verification:**
- Row counts match the baseline exactly. Dashboard renders in a browser without console errors.

---

### U2. Verify skill relocation, GitHub remote, and pixi platforms

**Goal:** Confirm the work recorded as done in S2 and S6 actually reflects the current working tree, and prepare `pixi.toml` for Windows by adding `win-64` to `platforms`.

**Requirements:** R2, R3, plus the pre-Phase-D `pixi.toml` platforms edit

**Dependencies:** None

**Files:**
- Modify: `pixi.toml` (add `win-64` to `[workspace] platforms`)
- Modify: `pixi.lock` (regenerated by `pixi install` after the platforms change)
- Read: `.claude/skills/` directory listing; `git remote -v` output; `git log --all` for credential-shaped strings

**Approach:**
- Confirm six skill directories exist under `.claude/skills/`: `sec-edgar`, `tra-download-filings`, `tra-process-filings`, `tra-build-timeline`, `tra-htm-to-md`, `tra-packet`. Confirm none exist under `~/.claude/skills/`.
- Run `git remote -v` and confirm `origin` points at `https://github.com/AlexSulliMora/tra-database.git`.
- Verify `TRA-contracts/` is not in the pushed tree: `git ls-tree -r --name-only origin/main | grep -c '^TRA-contracts/'` returns 0.
- Sweep for credential leaks: `git log --all -p | grep -iE '(SECRET|API_KEY|TOKEN|PASSWORD|AWS_)'` should return no matches outside test fixtures.
- Edit `pixi.toml`: change `platforms = ["linux-64"]` to `platforms = ["linux-64", "win-64"]`. Run `pixi install` to regenerate `pixi.lock` for both platforms. If a package fails to resolve on `win-64`, halt and surface the package name (this is the early-detection point for the Windows migration risk).

**Patterns to follow:**
- Pixi platforms documentation referenced in `pixi.toml` comments if present.

**Test scenarios:**
- Happy path: six skills present at `.claude/skills/`; zero at `~/.claude/skills/`.
- Happy path: `git remote -v` shows the private repo URL.
- Edge case: `TRA-contracts/` absent from `origin/main`; `.gitignore` lists `TRA-contracts/`.
- Error path: `pixi install` after platforms edit either succeeds (lockfile carries both platforms) or fails loudly with a named package. If it fails, U2 halts and the user resolves before Phase D.

**Verification:**
- All six skills present at `.claude/skills/`; remote is the private repo; `pixi.lock` includes `win-64` entries (verifiable by grepping for `platform = "win-64"` in the lockfile or by running `pixi info` on Windows later).

---

### U3. Resolve `scripts/sec_edgar/resolve_deferred_ciks.py` disposition

**Goal:** Resolve the silent-deletion record from S3 by either restoring the file or amending the signed-off inventory.

**Requirements:** R4

**Dependencies:** None

**Files:**
- Modify: either `scripts/sec_edgar/resolve_deferred_ciks.py` (restore) or `coauthor/2026-05-18-git-good/inventory.md` (amend with a `delete` row and cascade rationale)
- Read: working tree for callers via `grep -rn "resolve_deferred_ciks" .` excluding `.git`, `.pixi`, `TRA-contracts`, `data/edgar-query/exhibits`

**Approach:**
- Run the grep; if any surviving script references `resolve_deferred_ciks`, restore the file from git history (`git log --all --diff-filter=D -- scripts/sec_edgar/resolve_deferred_ciks.py` to find the deletion commit, then `git show <commit>^:scripts/sec_edgar/resolve_deferred_ciks.py > scripts/sec_edgar/resolve_deferred_ciks.py`).
- If no callers exist, append a row to `inventory.md` under the appropriate `delete` section: `scripts/sec_edgar/resolve_deferred_ciks.py | delete | Cascade: defaulted to deleted tra_deferred_review.csv (S3); no surviving callers confirmed by grep on 2026-05-24.`

**Patterns to follow:**
- Inventory format from existing `inventory.md` rows.

**Test scenarios:**
- Happy path: grep returns zero hits; inventory amended with the cascade rationale row.
- Edge case: grep returns a hit in active code; file restored from git history; restoration commit references the original deletion context.

**Verification:**
- Either the file exists on disk and the grep hit is satisfied, or the inventory carries the amendment row and no script in the working tree references the missing symbol.

---

### U4. Rewrite `README.md` for per-document EDGAR acquisition (R6a)

**Goal:** Update the workflow / acquisition sections of `README.md` to describe the pipeline as it actually runs after S7a's rework. Skill catalog is left untouched in this unit (updated in U7 close and U10).

**Requirements:** R6a

**Dependencies:** None

**Files:**
- Modify: `README.md`

**Approach:**
- Read the current `README.md`.
- Identify and rewrite the EDGAR acquisition section: replace any per-filing-three-query-union description with the per-document EX-10 search (`scripts/find_candidates.py` queries four phrase variants in monthly windows; `scripts/pull_exhibits.py` downloads matched documents per row to `data/edgar-query/exhibits/<CIK>/`).
- Update the workflow section's command sequence to reflect the new acquisition shape.
- Remove references to the retired three-query union, allow-list post-filter, and S-1/S-4/424B completeness pass.
- Do NOT remove the `tra-packet` skill catalog entry in this unit (handled in U10 / S7e).
- Do NOT add `tra-classify` or `tra-refresh` to the catalog in this unit (added in U7 / U12).
- Add a one-sentence note at the top of the workflow section: a fresh checkout has no `TRA-contracts/` (gitignored, regenerable); the full pipeline (S7a candidate sweep through S8 build) must run before `build_tra_database.py` has inputs.

**Patterns to follow:**
- Existing `README.md` section structure.

**Test scenarios:**
- Happy path: README workflow section names `find_candidates.py` and `pull_exhibits.py` explicitly; no remaining references to the three-query union or allow-list post-filter.
- Edge case: every command in the workflow section is runnable on a fresh checkout (after `pixi install`), modulo the corpus-regeneration warning.

**Verification:**
- `grep -E "three-query|allow.list|completeness pass" README.md` returns no matches. `grep -E "find_candidates|pull_exhibits" README.md` returns at least one match each.

---

### U5. Build `tra-classify` skill scaffold (v0)

**Goal:** Install the new `tra-classify` skill at `.claude/skills/tra-classify/` with three-way output and the forced-uncertain escape hatch in place.

**Requirements:** R7, R8 (partial — the schema and three-way emission; A4 integration in U6; iteration mechanics in U7)

**Dependencies:** U2 (skills auto-load confirmed)

**Files:**
- Create: `.claude/skills/tra-classify/SKILL.md`
- Create: `.claude/skills/tra-classify/scripts/classify.py`
- Create: `.claude/skills/tra-classify/references/signal-catalog.md` (versioned per iteration)
- Create: `data/edgar-query/forced_uncertain.csv` (header only at this stage: `cik,accession,filename,reason`)

**Approach:**
- SKILL.md follows house style. Frontmatter: `name: tra-classify`, description naming the trigger ("classify EX-10 documents for TRA-or-not"), `allowed-tools` if applicable.
- Body sections: Purpose (deterministic three-way classifier for TRA contracts vs documents that mention TRAs), Universal constraints (pixi-only, polars-lazy-first, bounded reads ≤ 80 KB title window + 400 KB scan window), Inputs (`--input-dir`, `--output-csv`, `--classifier-version`, optional `--forced-uncertain`), Outputs (`classifications-v<N>.csv` schema), Workflow steps (1: read forced-uncertain list; 2: per document, score signals; 3: apply thresholds → yes/no/uncertain; 4: write row), Running the skill, What this skill does not do (does not call A4 — that's the reviewer subagent's job; does not move documents on disk).
- `classify.py` implements the v0 signal set: centered-title detection for "TAX RECEIVABLE AGREEMENT" (case-insensitive, both inline-style and CSS-class centering), four-variant phrase presence (singular + plural × receivable + receivables, the gap the prior attempt missed), defined-term presence (`Exchange Basis Adjustment`, `Realized Tax Benefit`, `Tax Asset`), signature-block heuristic (presence of `_______________` lines or `Date: ____` patterns). Each signal scored 0 or 1; combined into yes / no / uncertain per a thresholded rule (e.g., centered title is sufficient for `yes`; absence of centered title + phrase presence → `uncertain`; absence of all signals → `no`).
- Forced-uncertain list read at startup: any (cik, accession, filename) on the list is routed to `uncertain` regardless of signals.
- Incremental write: each row appended to the output CSV as it's processed. Re-running over a partially-written CSV resumes from the last `(cik, accession, filename, classifier_version)` already present.
- Random seed from date (per python.md rule): `SEED = int(date.today().strftime("%Y%m%d"))`.

**Patterns to follow:**
- `tmp/TRA-classify/scripts/classify_tras.py` for bounded-reads and extension handling (`.htm/.html/.txt/.pdf` — PDFs auto-route to `uncertain` since no text-extraction layer exists yet).
- `.claude/skills/tra-download-filings/SKILL.md` for skill structure.

**Test scenarios:**
- Happy path: 100 known-TRA documents → at least 95 classified `yes` (rest `uncertain`); 100 known-non-TRA documents → at least 95 classified `no` (rest `uncertain`). Specific thresholds calibrate during iteration.
- Edge case: empty input directory → script exits 0 with empty output CSV (header only).
- Edge case: document with centered title in CSS class (not inline style) — caught by the second branch of the centered-title detector. Covers the prior attempt's missed-case G.
- Edge case: document on the forced-uncertain list → output row's `classification` is `uncertain` and `signals_matched` includes the marker `forced`.
- Edge case: re-run over partial CSV → resumes; no duplicate rows; final row count matches input file count.
- Error path: PDF without OCR → routed to `uncertain` with `signals_matched = pdf_no_text`. Matches the prior attempt's pragmatic handling.
- Integration: skill auto-loads in Claude Code (listed by `claude --skills` or equivalent); standalone CLI invocation works (`PYTHONPATH=.claude/skills/sec-edgar/scripts pixi run python .claude/skills/tra-classify/scripts/classify.py --input-dir data/edgar-query/exhibits --output-csv data/edgar-query/classifications-v1.csv --classifier-version 1`).

**Verification:**
- Skill loads as a project-local skill (`Claude Code` lists `tra-classify` in available skills).
- A trial run on 50 documents from `data/edgar-query/exhibits/` produces a `classifications-v1.csv` with one row per document, classification ∈ {yes, no, uncertain}, and `signals_matched` populated.

---

### U6. A4 Claude reviewer subagent (custom agent + cache)

**Goal:** Build the A4 reviewer pipeline: a custom agent definition that reads uncertain documents and writes verdicts, backed by a content-hash cache that becomes the deterministic source on F2 acceptance.

**Requirements:** R9, R10 (escalation path)

**Dependencies:** U5

**Files:**
- Create: `.claude/agents/tra-reviewer.md`
- Create: `data/edgar-query/a4_verdicts_cache.csv` (header: `content_hash,reviewer_verdict,reviewer_rationale,reviewed_at,model_id`)
- Modify: `.claude/skills/tra-classify/scripts/classify.py` (add `--mode review-uncertain` subcommand: reads classifications-v<N>.csv, dispatches A4 on uncertain rows, writes verdicts back and appends to the cache)

**Approach:**
- A4 custom agent definition (per user preference for judgment-heavy custom agents): `model: claude-opus-4-7`, brief system prompt describing the TRA-vs-mentions-TRA discrimination task with three illustrative examples (a clear TRA, a clear non-TRA, an ambiguous case), instruction to return a JSON object `{verdict: "yes"|"no", rationale: "<one sentence>"}` on every call. Preloads the `tra-classify` skill's `signal-catalog.md` so A4 knows what the deterministic layer checked.
- **Session restart required between U6 and U7.** Agent files written to `.claude/agents/` require a Claude Code session restart to become addressable as a subagent type. After creating `tra-reviewer.md`, restart the Claude Code session before U7 begins (the iteration run depends on dispatching the registered agent). For in-session iteration runs that must happen pre-restart (e.g., a same-session smoke test), use an in-session `Agent` dispatch with `model: "opus"` override and the skill content inlined into the prompt; this duplicates the agent definition's content but avoids the registration barrier.
- Driver: `classify.py --mode review-uncertain` reads `classifications-v<N>.csv`, filters to rows where `classification = uncertain`. For each row: compute the document content hash (SHA-256 of file bytes); look up the hash in `a4_verdicts_cache.csv`; if a hit, copy the cached verdict to the row. If a miss, dispatch the A4 custom agent with the document text (bounded read), parse the JSON response, write the verdict to the row AND append to the cache.
- Retry policy: three retries with exponential back-off on transient failure (network exception, HTTP 429, HTTP 5xx). On persistent failure: row gets `reviewer_verdict = ERROR_UNAVAILABLE`, treated as escalated to A1.
- Validation: JSON parse must yield `verdict ∈ {yes, no}` and a non-empty rationale. On malformed output: one retry with a corrective system message ("Return strictly the JSON object {verdict, rationale} with verdict in {yes, no}"). On second failure: `reviewer_verdict = ERROR_MALFORMED`, escalate to A1.
- A1 escalation: `classifications-v<N>.csv` carries two extra columns beyond R8's minimum schema — `needs_a1_review` (boolean) and `escalation_reason` (string). Rows needing A1 attention (ERROR_* rows + rows where A4 contradicts a prior A1 correction per R10) get `needs_a1_review = true` with the reason populated. A1 resolves these by editing the row in place before iteration N+1 starts; no parallel file.
- Cache freezing on F2 acceptance: when A1 signs off on iteration N (recorded in `classifier_acceptance.md`), the `a4_verdicts_cache.csv` is treated as frozen for the 3,025-document set. Future `tra-refresh` runs read this cache for known documents (deterministic) and make fresh A4 calls only for new content hashes.

**Patterns to follow:**
- `.claude/skills/tra-htm-to-md/SKILL.md` for bounded-read patterns.
- User-global `feedback_judgment_tasks_custom_agent.md` for custom agent shape (model:opus-4-7, skills preloaded).

**Test scenarios:**
- Happy path: a trial set of 10 uncertain documents → A4 returns yes/no for each; `classifications-v<N>.csv` rows updated with `reviewer_verdict` and `reviewer_rationale`; cache populated with 10 new entries.
- Happy path: re-run on the same 10 documents → zero A4 calls (all cache hits); rows updated identically.
- Edge case: A4 returns `{verdict: "maybe", rationale: "..."}` → one corrective retry; if still malformed, row marked `ERROR_MALFORMED`.
- Edge case: A4 call times out (HTTP timeout) → three retries with back-off; if all fail, row marked `ERROR_UNAVAILABLE`.
- Edge case: A4 returns valid JSON but contradicts a prior A1 correction (the row was marked yes in iteration N-1, A4 returns no in N) → row added to `escalations-v<N>.csv` for A1 to resolve.
- Integration: full pipeline U5 → U6 on 50 documents: classifier emits N uncertain → driver dispatches A4 → final classifications carry yes/no/uncertain (uncertain only on persistent ERROR rows that A1 hasn't resolved).
- Covers AE2.

**Verification:**
- `data/edgar-query/a4_verdicts_cache.csv` has one row per unique content hash A4 reviewed. Re-running `review_uncertain.py` on the same input dispatches zero new A4 calls.

---

### U7. Iteration mechanics + acceptance tracking

**Goal:** Wire the per-iteration outputs (versioned CSVs, classifier_acceptance.md, the symlink to the accepted version) so the F2 loop has a clean acceptance gate and the README catalog reflects the new skill.

**Requirements:** R10 (acceptance), R11 (uniform classifier_version + re-run before union)

**Dependencies:** U5, U6

**Files:**
- Create: `data/edgar-query/classifier_acceptance.md`
- Modify: `README.md` (add `tra-classify` to skill catalog)
- Modify: `.claude/skills/tra-classify/scripts/classify.py` (add `--mode finalize` subcommand: re-runs the accepted classifier end-to-end and emits the final `classifications.csv` with uniform `classifier_version`)

**Approach:**
- `classifier_acceptance.md` is a flat append-only log; one line per acceptance event in the format `YYYY-MM-DD | classifier_version=N | status=accepted | <user sign-off note>` (or `status=revised → iteration N+1` for non-accepted rounds). `classify.py --mode finalize` reads the last `status=accepted` line for the version. The user can also pass `--classifier-version N` on the CLI to skip parsing entirely (recommended for explicit invocations).
- `classify.py --mode finalize` reads `classifier_acceptance.md` for the most recent `accepted` iteration (or accepts `--classifier-version N` explicitly to skip parsing); invokes `--mode classify` end-to-end on `data/edgar-query/exhibits/` with that version; invokes `--mode review-uncertain` over the result (cache-hits-only on the accepted set); writes the final `data/edgar-query/classifications.csv` and ensures uniform `classifier_version` across all rows. Symlinks (or copies) `classifications.csv` to the canonical name.
- The script verifies the post-symlink file's `classifier_version` column is uniform; if not, halts with an error (this enforces R11's "single uniform classifier_version" constraint).
- README catalog update: insert one line after `tra-build-timeline` row: `| tra-classify | Classify EX-10 documents as TRA contracts / non-TRAs / uncertain; calls the tra-reviewer agent on uncertain cases. |`

**Patterns to follow:**
- Existing README skill catalog format.
- Acceptance-log shape (chronological, one section per iteration with consistent fields).

**Test scenarios:**
- Happy path: after a trial iteration is marked accepted, `finalize_acceptance.py` produces a `classifications.csv` with uniform `classifier_version = N` and row count equal to the input directory's document count.
- Edge case: the most recent acceptance log entry has status `revised` (not `accepted`) → script halts with an error message naming the most recent accepted version (or none).
- Error path: classifier_version mismatch between rows in the produced CSV → script halts and reports the offending rows.
- Integration: F2 round-trip on 100 trial documents: U5 emits → U6 reviews → user marks accepted → U7 finalizes → `classifications.csv` is the union-ready input for R11.
- Covers AE3 (the iteration-N+1 correction property is exercised by running U5 with a revised classifier_version after a manual edit and confirming the previously-flagged document classifies correctly or routes to uncertain with A4 agreeing).

**Verification:**
- `classifications.csv` exists, has uniform `classifier_version`, and the row count matches `data/edgar-query/exhibits/` document count. README catalog lists `tra-classify`.

---

### U8. S7c — rewrite `tra-download-filings` to the narrow form set

**Goal:** Update `tra-download-filings` to consume the confirmed-TRA-CIK list (from F2 acceptance) and pull only `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}` plus their exhibits.

**Requirements:** R12

**Dependencies:** F2 closed (confirmed-TRA-CIK list exists)

**Files:**
- Modify: `.claude/skills/tra-download-filings/SKILL.md`
- Modify: `scripts/tra_download.py` (still under `scripts/` at this point; relocated in U11)

**Approach:**
- Rewrite the SKILL.md `## Inputs` to name the confirmed-TRA-CIK list path (default `data/edgar-query/confirmed_tra_ciks.csv` — derived from `classifications.csv`).
- Rewrite `## Workflow`: (1) load the confirmed-TRA-CIK list; (2) for each CIK, call `list_filings_by_form(cik, form_type)` for each form in `{"8-K", "10-K", "424B1", "424B2", "424B3", "424B4", "424B5"}` — passing exact form strings, NOT a `forms=` parameter (avoids the slash-bearing-codes silent-zero bug); (3) for each filing, fetch every document in its `index.json`; (4) save under `TRA-contracts/<firm-slug>/<accession>/<filename>`; (5) per firm, select the single "final IPO prospectus" by taking the latest 424B* filed within 7 days of the IPO date, where the IPO date is inferred from the earliest 8-K with Item 1.01 mentioning IPO. **Detection mechanism:** the EDGAR submissions endpoint returns an `items` field per 8-K (e.g., `"1.01,5.02"`). Cheap path: filter the firm's 8-Ks by `items` containing `1.01`. For matching filings, fetch the document body via `fetch_document` and do a bounded text scan (first 100 KB) for any of `"initial public offering"`, `"IPO"`, `"pricing of the Company's common stock"`, `"Registration Statement on Form S-1"` (case-insensitive). The earliest filing whose body matches becomes the IPO date.
- Remove from the SKILL.md: three-query union, EDGAR full-text search per CIK, allow-list post-filter, S-1/S-4/424B completeness pass, corporate-events query, the wide ALLOWED_FORMS list.
- Update `tra_download.py` helper: drop the three-query union, drop the allow-list post-filter; keep the rate-limit retry wrapper. Per-firm directory creation logic stays.
- Add a one-paragraph note in the SKILL.md `## What this skill does not do` section: 10-Q (TRA payment disclosures in tax footnotes) and proxy filings (TRA-beneficiary compensation) are out of scope; analysis depending on those forms requires a separate acquisition pass.

**Patterns to follow:**
- `scripts/sec_edgar/forms.py` for `list_filings_by_form` usage.
- `.claude/skills/sec-edgar/SKILL.md` for the rate-limit + retry wrapper pattern.

**Test scenarios:**
- Happy path: trial on 3 confirmed-TRA CIKs → only filings of the named forms are fetched; each filing's `index.json` documents all saved; output tree mirrors `TRA-contracts/<firm-slug>/<accession>/<filename>`.
- Edge case: a CIK with no 8-K Item 1.01 (no IPO event detected) → no 424B selected for that firm; the SKILL.md notes this is acceptable (not every firm has an IPO).
- Edge case: a CIK with multiple 424Bs within the 7-day IPO window → the latest by `filingDate` wins; tie-break by `accessionNumber` ascending.
- Error path: a CIK that returns no filings from `list_filings_by_form` → skipped silently with a log line; not an error.
- Error path: SEC rate-limit retry triggers on at least one filing; the wrapper logs the back-off and succeeds.
- Integration: full trial on 3 firms produces a complete `TRA-contracts/<firm>/<accession>/` tree with both primary docs and exhibits. Row counts per form match expectations from `list_filings_by_form`'s LazyFrame.

**Verification:**
- A trial run on 3 firms produces only `{8-K, 10-K, 424B*}` filings; no 10-Q, S-1, S-4, proxy, etc. Manifest of downloaded files committable for diff against expected.

---

### U9. S7d — `tra-process-filings` reads markdown (drops "move to TRA-*/" step)

**Goal:** Switch `tra-process-filings` to read the markdown companions produced by `tra-htm-to-md`; drop the "move to TRA-*/" step so htm-to-md operates exclusively on `<accession>/` directories.

**Requirements:** R13 (S7d component)

**Dependencies:** None (independent of U8)

**Files:**
- Modify: `.claude/skills/tra-process-filings/SKILL.md`
- Modify: `.claude/skills/tra-htm-to-md/SKILL.md` (clarify that it operates on `<accession>/` exclusively)
- Modify: `.claude/skills/tra-build-timeline/SKILL.md` (rewrite for the flat-accession layout — see Approach below)

**Approach:**
- In `tra-process-filings/SKILL.md`: remove the "Strip HTML and read" step (Step 1 in the current version). Replace with: "Read the markdown companion produced by `tra-htm-to-md` for each filing's documents. The markdown lives next to the source HTML in the same accession directory."
- Remove the workflow step that moves contracts into a `TRA-*/` subdirectory. The per-firm directory becomes `TRA-contracts/<firm-slug>/<accession>/` with markdown + HTML side-by-side; no `TRA-2018-11-14/` subdirs.
- Classification logic (Steps 2-7 in the prior SKILL.md) stays unchanged; it now reads markdown instead of stripped-HTML.
- Update `tra-htm-to-md/SKILL.md` workflow ordering note: clarifies it runs over `<accession>/` directories before `tra-process-filings`; no second pass needed.
- Update the SKILL.md note at the top to reflect that the chain is now `tra-htm-to-md` → `tra-process-filings`, both operating on `<accession>/`.
- **Rewrite `tra-build-timeline/SKILL.md` for the flat-accession layout.** The current skill is built around `TRA-<date>[-<diff>]/` subdirectories (per-firm input contract names them; per-TRA summary filenames embed the date; multi-TRA disambiguation reads each subdirectory as one TRA). Replace the per-subdirectory mechanism with a logical TRA-id key inside `contract_log.md` (e.g., a `tra_id: <slug>-<date>` field per contract entry); the per-TRA summary filename becomes `<slug>_<tra_id>_summary.qmd` for multi-TRA firms (still `<slug>_summary.qmd` for single-TRA firms); update the `firm_dir` input spec to enumerate the per-firm flat structure (`<accession>/` directories + `contract_log.md` + `filing_notes.md`). Existing per-firm summaries must be regenerated under the new filename scheme during S8 (U13) for multi-TRA firms.

**Patterns to follow:**
- Existing `tra-process-filings/SKILL.md` step structure.

**Test scenarios:**
- Happy path: trial on a sample firm — `tra-htm-to-md` runs first, produces `<accession>/<doc>.md` next to each HTML; `tra-process-filings` reads the markdown and produces the expected classification output.
- Edge case: a filing with no markdown produced (e.g., PDF-only filing) → process-filings logs the skip and continues; not an error.
- Integration: F3 chain trial on 3 firms exercises the new ordering end-to-end without needing the two-pass htm-to-md hack the prior plan flagged.

**Verification:**
- Process-filings SKILL.md no longer references HTML stripping or the `TRA-*/` subdirectory move. A trial run on 3 firms produces classification output identical to (or compatible with) the prior HTML-reading shape.

---

### U10. S7e — retire `tra-packet`; sweep stale references

**Goal:** Delete the `tra-packet` skill and its scripts; remove all surviving references in skill files and README.

**Requirements:** R5 (covered by sweep), R6b (catalog removal), R13 (S7e component)

**Dependencies:** None (independent of U8 / U9)

**Files:**
- Delete: `.claude/skills/tra-packet/`
- Delete: `scripts/tra_packet/`
- Modify: `README.md` (remove `tra-packet` catalog row)
- Modify: any SKILL.md that references `tra-packet` (sweep)

**Approach:**
- `rm -r .claude/skills/tra-packet/`.
- `rm -r scripts/tra_packet/`.
- `grep -rn "tra-packet" --include="*.md" .` excluding `coauthor/` (historical project records stay as-is) and `.git`. For each match in a SKILL.md or README.md, edit out the reference.
- `grep -rn "tra_deferred_review.csv" --include="*.md" .` excluding `coauthor/` — should now return zero hits since the only known reference was in `tra-packet/SKILL.md`, which was just deleted. Confirm. (This is R5's resolution: the orphaned reference goes away with the skill itself.)
- README.md skill catalog: remove the `tra-packet` row.

**Patterns to follow:**
- `inventory.md` deletion-list style from the prior S3 cleanup.

**Test scenarios:**
- Happy path: `.claude/skills/tra-packet/` and `scripts/tra_packet/` no longer exist; `grep -r "tra-packet" --include="*.md" . --exclude-dir=coauthor` returns zero hits.
- Edge case: a stale reference in a non-`.md` file (e.g., a Python script) — sweep also covers `*.py` if needed.
- Edge case: `tra_deferred_review.csv` reference also disappears with the SKILL.md deletion; confirm via grep.

**Verification:**
- Both paths gone; zero grep hits for `tra-packet` outside `coauthor/`; zero grep hits for `tra_deferred_review.csv` anywhere outside `coauthor/`. README catalog no longer lists the skill.

---

### U11. S7f — relocate skill-internal scripts

**Goal:** Move `scripts/sec_edgar/` into `.claude/skills/sec-edgar/scripts/sec_edgar/` and `scripts/tra_download.py` into `.claude/skills/tra-download-filings/scripts/tra_download.py`. Update every `PYTHONPATH=scripts` invocation across the project.

**Requirements:** R13 (S7f component)

**Dependencies:** U8 (S7c's edits to `tra_download.py` land first; relocating before would have S7c editing a path that's already moved)

**Files:**
- Move: `scripts/sec_edgar/` → `.claude/skills/sec-edgar/scripts/sec_edgar/`
- Move: `scripts/tra_download.py` → `.claude/skills/tra-download-filings/scripts/tra_download.py`
- Modify: every SKILL.md with a `PYTHONPATH=scripts` reference (sec-edgar, tra-download-filings, tra-process-filings, tra-build-timeline, tra-htm-to-md, tra-refresh once it exists)
- Modify: `README.md` if it carries `PYTHONPATH=scripts` examples

**Approach:**
- `mkdir -p .claude/skills/sec-edgar/scripts/`
- `mv scripts/sec_edgar .claude/skills/sec-edgar/scripts/sec_edgar`
- `mkdir -p .claude/skills/tra-download-filings/scripts/`
- `mv scripts/tra_download.py .claude/skills/tra-download-filings/scripts/tra_download.py`
- `grep -rn "PYTHONPATH=scripts\|scripts/sec_edgar\|scripts/tra_download" .claude/skills/ README.md` — update each match. The new invocation pattern: `PYTHONPATH=.claude/skills/sec-edgar/scripts pixi run python -c "from sec_edgar import ..."` (or per-skill PYTHONPATH).
- Verify: `pixi run -- python scripts/build_tra_database.py` still runs end-to-end (it does not depend on `sec_edgar`).
- Verify: `PYTHONPATH=.claude/skills/sec-edgar/scripts pixi run python -c "from sec_edgar import fetch_submissions; print(fetch_submissions)"` resolves the import.

**Patterns to follow:**
- Existing skill-scripts subdirectory layout (`tra-htm-to-md/scripts/` already follows this).

**Test scenarios:**
- Happy path: both moves succeed; `scripts/` no longer contains `sec_edgar/` or `tra_download.py`; sample import resolves.
- Edge case: a previously-overlooked `PYTHONPATH=scripts` reference in an unrelated file → grep catches it; update.
- Integration: trial run of `tra-download-filings` via SKILL.md instructions works end-to-end with the new path.

**Verification:**
- `ls scripts/` shows only `build_tra_database.py`, `build_dashboard.py`, and any user-kept exploratory `tra_*.py` files; no `sec_edgar/`, no `tra_download.py`. All SKILL.md path references updated. Sample import resolves.

---

### U12. S7g — build `tra-refresh` skill

**Goal:** Install the new `tra-refresh` skill at `.claude/skills/tra-refresh/` that orchestrates the incremental refresh of the corpus and the database.

**Requirements:** R14

**Dependencies:** U7 (tra-classify exists), U8 (tra-download-filings rewritten), U9 (tra-process-filings markdown read), U10 (tra-packet gone), U11 (scripts relocated)

**Files:**
- Create: `.claude/skills/tra-refresh/SKILL.md`
- Create: `.claude/skills/tra-refresh/scripts/refresh.py`
- Modify: `README.md` (add `tra-refresh` to skill catalog)

**Approach:**
- SKILL.md follows house style. Trigger phrases in description: "refresh the TRA database", "check EDGAR for new TRA filings".
- `## Workflow` steps: (1) read `outputs/tra-database/last_refresh.json` for the prior cutoff date; if missing, fall back to the max `file_date` in `data/edgar-query/full-text.parquet`; (2) load the confirmed-TRA-CIK list from `data/edgar-query/classifications.csv` (where `classification = yes` OR `reviewer_verdict = yes`); (3) re-run `scripts/find_candidates.py` over the cutoff-to-today window to surface new EX-10 candidates per CIK (or per the full sweep if a CIK-set filter is supported); (4) run `tra-classify` over the new candidates with the accepted classifier version; (5) for each new yes (deterministic or A4-confirmed via cache), invoke the rewritten `tra-download-filings` (U8) for the affected CIKs over the cutoff-to-today window, fetching only filings of the narrow form set; (6) run `tra-htm-to-md` over the new accession directories; (7) run `tra-process-filings` over the affected firm directories; (8) run `tra-build-timeline` to refresh per-firm summaries; (9) re-run `scripts/build_tra_database.py` to regenerate parquets; (10) re-run `scripts/build_dashboard.py`; (11) write a new `outputs/tra-database/last_refresh.json` with `run_date`, `cutoff_date`, `firms_queried`, `new_filings_count`, `new_classifications_count`, `classifier_version`.
- `--dry-run` mode performs steps (1)-(4) only and reports counts without modifying any parquet or per-firm directory.
- Cache integration: when `tra-classify` returns `uncertain`, the A4 driver (U6) is invoked; for known content hashes the cache (frozen on F2 acceptance) returns the verdict deterministically; for new content hashes, a fresh A4 call is made and the result appended to the cache (a refresh extends the cache; the original F2-accepted entries are immutable).
- README catalog: insert `| tra-refresh | Incremental refresh of the TRA corpus and database from EDGAR since the last cutoff. |` after `tra-htm-to-md`.

**Patterns to follow:**
- `.claude/skills/sec-edgar/SKILL.md` for orchestrator skill shape (calls into other skills' helper scripts).
- The frozen prior plan's S7g specification for the workflow steps.

**Test scenarios:**
- Happy path: `tra-refresh --dry-run` on the current database (cutoff = max `file_date` from `full-text.parquet`) → reports `0 new filings` (since the cutoff is the most recent filing); no parquet writes.
- Happy path: synthesize a cutoff 30 days in the past → dry-run reports the count of filings in the last 30 days; no writes.
- Edge case: `last_refresh.json` missing → fallback to `full-text.parquet` max date; report that fallback was used in the dry-run output.
- Edge case: a new EX-10 candidate that A4 cache resolves to `yes` deterministically → no new A4 call; logged as cache-hit.
- Edge case: a new EX-10 candidate with a never-seen content hash → fresh A4 call; cache appended.
- Integration: live refresh after a synthesized cutoff: produces an updated `last_refresh.json` with correct fields; affected firms' summaries regenerate; parquet outputs row counts update.
- Covers AE4 (the dry-run reporting behavior).

**Verification:**
- `tra-refresh --dry-run` runs without error and reports counts. A live refresh writes a valid `last_refresh.json` with all required fields.

---

### U13. S8 — systematic rerun

**Goal:** Execute the full pipeline end-to-end against the confirmed-TRA-CIK list, regenerate the parquet outputs and dashboard, write the baseline `last_refresh.json`, commit and push.

**Requirements:** R15

**Dependencies:** U7 (F2 closed), U8, U9, U10, U11, U12

**Files:**
- Modify: `TRA-contracts/<firm-slug>/<accession>/` (per firm, populated by the rewritten download skill)
- Modify: `outputs/tra-database/{tras,events,stock_by_date}.parquet`
- Modify: `outputs/tra-database/dashboard.html`
- Create: `outputs/tra-database/last_refresh.json`
- New git commit on `main`

**Approach:**
- Sequence (executed by an orchestrating script or a human walking through the SKILL.md steps): (1) extract confirmed-TRA-CIK list from `data/edgar-query/classifications.csv` (unique CIKs from rows where `classification = yes` OR `reviewer_verdict = yes`); write to `data/edgar-query/confirmed_tra_ciks.csv`. (2) Run the rewritten `tra-download-filings` against the list — fetches narrow form set into `TRA-contracts/<firm-slug>/<accession>/<filename>`. (3) Run `tra-htm-to-md` over every new `<accession>/`. (4) Run `tra-process-filings` per firm (now reads markdown). (5) Run `tra-build-timeline` per firm to refresh `<firm>_summary.qmd` files. (6) Run `scripts/build_tra_database.py` → fresh parquets. (7) Run `scripts/build_dashboard.py` → fresh `dashboard.html`. (8) Run `tra-refresh` in live mode (with `--cutoff today`) to write the baseline `last_refresh.json` (a no-op refresh that just records the metadata).
- **Re-acceptance gate.** Before step (1)'s CIK extraction commits to the final list: if `find_candidates.py` is re-run as part of S8 and produces a regenerated `data/edgar-query/full-text.parquet` that differs from the F2-accepted set, run the accepted `tra-classify` over the regenerated set. Diff the new `classifications.csv` against the F2-accepted one. If new documents or new CIKs appear, surface the diff to A1 for sign-off before proceeding. This addresses Open Question item G11 from the brainstorm.
- Companion-metadata preservation (per the user's `feedback_destructive_corpus_operations.md` rule): the rerun must NOT overwrite existing `contract_log.md`, `filing_notes.md`, or `*_summary.qmd` files in `TRA-contracts/<firm>/`. If the same accession is re-fetched, the per-document files are overwritten (deterministic from EDGAR) but the per-firm annotations stay. If a firm-slug changes (CIK matched a different name), the firm directory is treated as new and the old one stays untouched — A1 reconciles after.
- **Slug-diff detection and acknowledgement gate.** Between step (2) (download) and step (6) (build_tra_database.py), emit `TRA-contracts/SLUG_DIFF_<rundate>.md` listing: CIKs with both an old-slug and new-slug directory present (rename candidates); CIKs in the new corpus with no prior directory (new firms); prior-corpus CIKs absent from the new corpus (dropped firms). The S8 orchestration script (or human walking through) blocks on A1 acknowledging the file — `touch TRA-contracts/SLUG_DIFF_<rundate>.acknowledged` — before step (6) `build_tra_database.py` runs. Mechanical detection prevents the silent-rename failure mode where the build picks up whichever `*_summary.qmd` survives without A1 noticing.
- Commit message: "Systematic rerun: regenerated corpus from confirmed-TRA-CIK list with the narrowed acquisition pipeline; baseline last_refresh.json written."
- Push to `origin/main`.

**Patterns to follow:**
- Frozen `ca-02-plan.md` S8 specification.
- User-global rules on destructive corpus operations.

**Test scenarios:**
- Happy path: full rerun completes; parquet row counts are of the same order of magnitude as the prior baseline (the new corpus may have fewer or more firms than 321, which is expected).
- Edge case: re-acceptance gate fires (S8 corpus differs from F2-accepted) → A1 sign-off recorded in `classifier_acceptance.md` before proceeding.
- Edge case: a previously-included firm now classifies `no` (the new classifier dropped a CIK that the prior corpus included) → the firm's directory in `TRA-contracts/` is NOT deleted; A1 decides whether to keep it as historical.
- Edge case: a new CIK enters the corpus (a firm the prior acquisition missed) → a fresh `TRA-contracts/<firm-slug>/` is created; no companion metadata yet (A1 adds during follow-up review).
- Error path: `build_tra_database.py` fails on a corrupt YAML frontmatter in a `*_summary.qmd` → halt loudly, surface the offending file; do not silently skip.
- Integration: end-to-end on the full confirmed-TRA-CIK list produces a self-consistent corpus + parquets + dashboard + last_refresh.json; commit + push succeed.

**Verification:**
- Three parquets exist with row counts matching the new confirmed-TRA-document set; `dashboard.html` renders; `last_refresh.json` carries valid fields; `git log -1` shows the rerun commit pushed to `origin/main`.

---

### U14. R16a Windows replicability test + R16b WSL deletion

**Goal:** Clone the repo on Windows, install pixi, run the pipeline end-to-end, confirm row counts match the WSL build (within `tra-refresh`-delta tolerance), then delete the WSL tree after user sign-off on the S8 corpus.

**Requirements:** R16a, R16b

**Dependencies:** U13 committed and pushed

**Files:**
- Create: `scripts/check_wsl_deletion_ready.sh` (or `.py` — mechanical precondition checker for R16b)
- (Windows side) Fresh clone at `C:\Users\Sulli\research\tra\`
- (WSL side) `~/research/tra/` — deleted after R16b gate clears

**Approach:**
- On Windows: `git clone https://github.com/AlexSulliMora/tra-database.git C:\Users\Sulli\research\tra\`.
- Install pixi on Windows per the official pixi Windows installer.
- `pixi install` in the cloned directory — verifies `pixi.lock` resolves with `win-64` (the U2 edit pulled `win-64` into the platforms list and regenerated the lockfile).
- Run the documented end-to-end commands from the updated `README.md`: candidate discovery (`pixi run -- python scripts/find_candidates.py ...`), classify (`pixi run -- python .claude/skills/tra-classify/scripts/classify.py ...`), download (the new narrowed `tra-download-filings`), htm-to-md, process-filings, build-timeline, build-database, build-dashboard, `tra-refresh` for the baseline metadata.
- Compare Windows-side parquet row counts to the WSL build's recorded counts. Acceptable: identical (build-from-disk path) or differing by the `tra-refresh` delta between WSL run and Windows run (any new EDGAR filings posted in that window, documented in `last_refresh.json`). Any unexplained divergence is treated as a replicability bug — fix in place, push, repeat the Windows rerun.
- Re-acceptance gate (the third of R16b's three preconditions): A1 reviews the Windows-produced `classifications.csv` (which is a regenerated set from the Windows-side `find_candidates.py` + classifier run); confirms no new misclassifications surfaced; signs off in `classifier_acceptance.md`.
- Before running the deletion, execute `scripts/check_wsl_deletion_ready.sh`: it mechanically verifies the three R16b preconditions and either prints the `rm -rf` command for A1 to copy-paste or names the failing precondition. Specifically it checks: (i) `data/edgar-query/classifier_acceptance.md`'s last line carries `status=accepted` and a `Windows-replicability-confirmed` marker; (ii) `outputs/tra-database/last_refresh.json` on `origin/main` exists and was written by the S8 commit (timestamp check); (iii) no draft `classifications-v<N>.csv` exists at a higher version than the accepted one. The script does NOT run the deletion itself — A1 copy-pastes only after the script prints the OK message.
- After all three R16b gates clear (R16a passes, S8 corpus re-acceptance signed, F2 closed) AND the check script prints OK: `rm -rf ~/research/tra/` on WSL. Cadence is user discretion; the deferred Open Questions item on cadence resolves at execution time.

**Patterns to follow:**
- Pixi Windows installation per the upstream pixi docs (consulted at execution time if needed).

**Test scenarios:**
- Happy path: Windows clone + `pixi install` succeeds; full pipeline rerun produces parquet row counts matching WSL build exactly (deterministic build-from-disk path) or within documented `tra-refresh` delta.
- Edge case: a Windows-only path-separator bug in a script → fix (replace `os.path.sep` hardcoding with `pathlib`); push; re-run.
- Edge case: a package fails to resolve on `win-64` despite U2's preflight → halt, regenerate the lockfile, re-push, re-clone on Windows, re-run.
- Edge case: row counts differ by an explainable amount (e.g., 12 new filings in the 3-day window between WSL run and Windows run) — A1 confirms the delta matches `last_refresh.json`; not a replicability bug.
- Integration: full Windows pipeline produces a `dashboard.html` that opens in a browser identically to the WSL-produced one.
- Covers AE5.

**Verification:**
- Windows-produced parquets match the WSL build's row counts (or differ by documented refresh delta). User signs off on the S8-regenerated `classifications.csv`. WSL tree deleted.

---

## System-Wide Impact

- **Interaction graph:** F2 introduces A4 (custom Claude agent) as a new actor in the pipeline; A4 reads documents and writes to `data/edgar-query/`. The A4 cache becomes shared state read by both F2's iteration loop and F3's `tra-refresh`. `tra-refresh` (U12) is the first orchestrator skill that chains four child skills (tra-classify, tra-download-filings, tra-htm-to-md, tra-process-filings, tra-build-timeline) — a pattern worth documenting in the skill catalog for future reference.
- **Error propagation:** A4 ERROR_* markers propagate from `review_uncertain.py` to `escalations-v<N>.csv` and pause the iteration until A1 resolves. Failures in the build pipeline (parquet read, YAML parse) fail loudly per the "fail loudly" rule; no silent skips that would leak into the published corpus.
- **State lifecycle risks:** classifier_version drift across `classifications-v<N>.csv` files — U7's `finalize_acceptance.py` enforces uniformity before R11's union. A4 cache invalidation if a document's content changes (EDGAR re-publication, amendment) — content-hash key catches this; the new hash misses the cache and triggers a fresh A4 call. `TRA-contracts/` companion-metadata preservation during S8 — the rerun is non-destructive of `contract_log.md`, `filing_notes.md`, `*_summary.qmd`.
- **API surface parity:** `tra-classify` and `tra-refresh` follow the same skill house style as the existing six; their CLIs use the same `pixi run --` pattern. The `sec_edgar` package's import path changes after U11 — every SKILL.md is updated atomically in the same unit so no skill is left referencing the old path.
- **Integration coverage:** the F2 round-trip (U5 → U6 → U7), the F3 chain (U8 → U9 → U10 → U11 → U12 → U13), and the full Windows replicability run (U14) are end-to-end integration tests by construction; no separate test harness needed.
- **Unchanged invariants:** the parquet schemas (`tras`, `events`, `stock_by_date`) and column dtypes are unchanged; the dashboard template's three placeholder tokens (`__TRAS_JSON__`, `__EVENTS_JSON__`, `__STOCK_JSON__`) substitution mechanism is unchanged; the existing `TRA-contracts/<firm>/<accession>/` directory structure is preserved (S7d drops the `TRA-*/` subdirectory layer, simplifying it).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Pixi lockfile incompatibility on Windows discovered only at U14 (Phase D) | U2 pulls the `pixi.toml` platforms edit forward to Phase A and runs `pixi install` to regenerate the cross-platform lockfile; surfaces lockfile failures within hours, not weeks. |
| F2 iteration loop fails to converge (user keeps reporting corrections; classifier never stabilizes) | U7's `classifier_acceptance.md` records each iteration's correction count; A2 surfaces the lack of convergence after iteration ~5 for user-decision (accept higher A4 burden, accept higher A1 burden, or widen `forced_uncertain.csv`). |
| A4 agreement with A1 is poor on the first calibration (A4 unreliable on TRA-vs-mentions-TRA) | U6's A4 driver writes verdicts; A1 reviews 100% of A4 verdicts in iteration 1; if agreement is low (e.g., < 90%), A2 either prompts-engineer the A4 system message or downgrades the design to "all uncertain → A1 directly, no A4 tier." |
| S8 corpus regeneration surfaces document shapes the classifier was never iterated against | U13's re-acceptance gate fires before the final CIK list is fed to S7c; A1 reviews the diff against F2-accepted; loop re-opens if needed. |
| `find_candidates.py` hits transient EDGAR 5xx storms during S8 (corpus rebuild gap) | Existing retry wrapper in `EdgarClient` handles transient 5xx; persistent failure halts the rerun loudly with the offending window logged. A1 re-runs after EDGAR recovers. |
| Windows-side pixi install fails silently (a package installs but a runtime import breaks) | U14 runs the full pipeline as the acceptance test, not just `pixi install`; any runtime failure surfaces as a row-count mismatch or a pipeline error. |
| WSL deletion (R16b) executed before R16a passes (premature deletion) | U14's R16b gate is procedural — three explicit preconditions in `classifier_acceptance.md`; the `rm -rf` is only run by A1 after all three are checked. |

---

## Documentation / Operational Notes

- `README.md` updates are staged across phases (U4 for the acquisition section, U7 for adding `tra-classify` to the catalog, U10 for removing `tra-packet`, U12 for adding `tra-refresh`). At every phase boundary the README is accurate to the current working-tree state.
- `data/edgar-query/classifier_acceptance.md` is a chronological log of the F2 iterations and acceptance decisions; future contributors reading the repo can reconstruct the classifier's development trajectory from this file.
- `data/edgar-query/a4_verdicts_cache.csv` is committed to the repo (small text file, deterministic gate). On `tra-refresh`, the cache grows; refresh commits include the new cache entries.
- The frozen `coauthor/2026-05-18-git-good/ca-*.md` files remain as historical record (origin-doc out-of-scope items name this explicitly). New compound-engineering artifacts (this plan, future review files) live under `docs/`.
- Migration to Windows (U14) ends the WSL phase; subsequent work on this corpus happens on Windows with Claude Desktop or Claude Code on Windows. The eventual-Windows-only goal is achieved here.

---

## Sources & References

- **Origin document:** [docs/brainstorms/git-good-continuation-requirements.md](docs/brainstorms/git-good-continuation-requirements.md) — the brainstorm carried R1-R16, F1-F3, A1-A4, AE1-AE5, plus 10 Open Questions appended on 2026-05-24 by ce-doc-review.
- **Frozen prior plan:** `coauthor/2026-05-18-git-good/ca-02-plan.md` — the S7c–S8 specifications carried forward; the F3 sequencing DAG in this plan reconciles the frozen plan's loose `parallel-with` annotations.
- **Prior project artifacts:** `coauthor/2026-05-18-git-good/{ca-01-scope.md, ca-03-deviations.md, ca-04-review.md, last-left-off-05-20-2026.md, inventory.md}` — historical record of S1-S7a execution.
- **Existing skills:** `.claude/skills/{sec-edgar, tra-download-filings, tra-process-filings, tra-build-timeline, tra-htm-to-md, tra-packet}/SKILL.md` — house-style references; tra-packet is retired in U10.
- **Existing pipeline scripts:** `scripts/{find_candidates.py, pull_exhibits.py, build_tra_database.py, build_dashboard.py, tra_download.py}`; `scripts/sec_edgar/` (package; relocated in U11).
- **Rejected prior classifier:** `tmp/TRA-classify/{SKILL.md, scripts/classify_tras.py}` — informs the v0 signal set and the discrimination problem the new classifier must solve.
- **User-global rules referenced:** `feedback_judgment_tasks_custom_agent.md` (A4 as custom agent), `feedback_destructive_corpus_operations.md` (S8 companion-metadata preservation), `feedback_large_data_files.md` (bounded reads in the classifier), `python.md` (pixi-only, polars-lazy-first, fail-loudly).

---

## Deferred / Open Questions

### From 2026-05-24 review

- **Content-hash cache key collision across accessions** — Key Technical Decisions; U6 (P1, adversarial, confidence 75)

  The A4 cache keys on SHA-256 of document bytes. The same TRA contract routinely re-files verbatim across accessions (parent + subsidiary LLC cross-filing; amendment-and-restatement re-attaching the original; 8-K Item 1.01 attaching an exhibit already filed as an S-1 exhibit). Under the current design the cache returns one verdict — desirable for yes/no — but `reviewer_rationale` carries one filing's context and may be wrong for the others. More seriously, if A4's verdict depended on filing context (e.g., an amendment retitling a non-TRA document as a TRA), the content-hash cache cannot distinguish the contexts. Choose: (a) document explicitly that content-hash caching means verdicts are context-free and any context-dependent reading is out of scope, OR (b) key the cache on `(content_hash, classifier_version)`, record the first-seen `(cik, accession)` in the cache row for audit, but do not let it gate the verdict.

  <!-- dedup-key: section="key technical decisions u6" title="content-hash cache key collision across accessions" evidence="the cache file committed to the repo keyed on document content hash" -->

- **classifier_version uniformity breaks if classify.py is edited post-acceptance** — R11, U7, U12 (P1, adversarial, confidence 75)

  R11 requires uniform `classifier_version`; U7 halts if violated. U12's `tra-refresh` runs the accepted classifier (version N) over new candidates and tags those rows `classifier_version=N`. As long as classify.py is never edited post-acceptance, this is consistent — but the plan does not pin the classifier source against the accepted version. If anyone edits classify.py between F2 acceptance and a later refresh (bug fix, new signal), refresh rows still carry `classifier_version=N` while running different code. The `--classifier-version` CLI arg is a manual label that can lie. Choose: (a) freeze the classifier source at acceptance — snapshot classify.py + signal-catalog.md under `.claude/skills/tra-classify/accepted/v<N>/` and have `--mode finalize` and `tra-refresh` invoke that snapshot path; OR (b) derive classifier_version from a content hash of the script + signal catalog and refuse to write if it doesn't match the accepted version recorded in classifier_acceptance.md.

  <!-- dedup-key: section="r11 u7 u12" title="classifier_version uniformity breaks if classifypy is edited post-acceptance" evidence="r11 requires uniform classifier_version u7 halts if violated u12s tra-refresh runs the accepted classifier" -->

- **forced_uncertain.csv growth governance** — Key Technical Decisions; U5 (P2, adversarial, confidence 75)

  The escape hatch is unbounded. During F2 iteration under user pressure (A2 trying to converge), the path of least resistance is to add failing documents to forced_uncertain.csv rather than improve a signal. Over rounds, the list absorbs everything hard; A4 becomes the de-facto classifier on a growing share of corpus; deterministic coverage shrinks; the project's stated motivation (phrase-presence does not discriminate) re-emerges as a different failure shape (A4 nondeterminism on a growing fraction). The Risks table mitigation routes convergence failure toward widening forced_uncertain — exactly the unguarded pressure direction. Decide: per-iteration budget cap (e.g., must stay below X% of corpus), required `reason` field beyond the header distinguishing "irreducibly ambiguous" from "we gave up on a signal", and surfacing the list's contents to A1 at acceptance as part of the acceptance review.

  <!-- dedup-key: section="key technical decisions u5" title="forced_uncertaincsv growth governance" evidence="documents the deterministic classifier cannot resolve without reading the body get listed in dataedgar-queryforced_uncertaincsv" -->

- **Re-acceptance rejection loop semantics** — U13; Risks (P2, adversarial, confidence 75)

  U13's re-acceptance gate says "surface the diff to A1 for sign-off before proceeding"; Risks table says "loop re-opens if needed." What "loop re-opens" means operationally is unspecified: full F2 re-iteration (A2 revises classifier) or A1 manually edits classifications.csv for new documents? F2 re-opening invalidates the frozen A4 cache; manual edits leave cache frozen but introduce non-classifier-derived verdicts violating R11's uniform-classifier_version constraint. Specify both branches: (a) if S8 diff is small (e.g., < 5 new documents AND no new CIKs), A1 may classify them inline by appending to forced_uncertain.csv + running A4, keeping F2 closed; (b) if larger or includes a new CIK that the v0–vN signals never saw, formally re-open F2 — increment classifier_version, unfreeze cache for new content hashes only (existing entries stay), run another iteration. Name the threshold rather than leaving "loop re-opens if needed" undefined.

  <!-- dedup-key: section="u13 risks" title="re-acceptance rejection loop semantics" evidence="u13s re-acceptance gate says surface the diff to a1 for sign-off before proceeding risks table says loop re-opens if needed" -->
