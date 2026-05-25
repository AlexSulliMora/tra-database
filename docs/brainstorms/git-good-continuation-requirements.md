---
date: 2026-05-24
topic: git-good-continuation
---

# Git-Good Continuation: Verify, Classify, Ship

## Summary

Continue the in-flight git-good TRA-pipeline cleanup project to completion: deep-verify the work already done, develop a deterministic TRA classifier through iterative human-in-the-loop dialogue (with a Claude reviewer for uncertain cases) until the user accepts its yes/no calls, then execute the remaining download/process/build/refresh chain to ship a fresh-clone-reproducible private repository.

---

## Problem Frame

The git-good project (`coauthor/2026-05-18-git-good/`) reached step S7a partially before the prior session ended with two unresolved items.

First, the EX-10 candidate-pull was reworked during execution into a per-document shape (3,025 EX-10 documents on disk, one row per matched document instead of one row per filing), diverging from the frozen S7a plan. The rework is on disk and accepted but not folded back into the plan or the project's downstream assumptions.

Second, the classification step was built in `tmp/TRA-classify/` and not accepted: its phrase-presence filter conflates "mentions a TRA" with "is a TRA" — LLC agreements, credit agreements, and registration-rights agreements all reference TRAs routinely. The user identified the centered document title as the real discriminator but has not committed to a deterministic specification of what makes a document a TRA contract; that specification has to be discovered iteratively by running candidate classifiers against documents the user knows the answer to.

Several upstream steps marked complete in the project record have not been re-verified against the current working tree (S2 skill relocation, S6 GitHub push, the row counts after the parquet conversion in S4). The README at the project root still describes the retired per-filing acquisition path and the `tra-packet` skill that was scheduled for deletion. A previously-flagged inventory gap (silent deletion of `scripts/sec_edgar/resolve_deferred_ciks.py`) remains open.

Two priorities order the remaining work: correct classification and recording of every real TRA, then fresh-clone reproducibility for academic-publication use. The verification pass exists to clear the second-priority bar before the systematic rerun (S8) can produce a corpus anyone trusts.

---

## Actors

- A1. User: Provides ground-truth TRA judgments by reviewing flagged documents and reporting misclassifications; signs off on destructive operations; makes the final acceptance call on the classifier.
- A2. Coder agent: Executes pipeline edits, runs verification scripts, implements the classify skill and its iterations, runs the systematic rerun.
- A3. Classify skill: Deterministic program that scores each input EX-10 document into one of {yes, no, uncertain}.
- A4. Claude reviewer subagent: Reads documents A3 scored `uncertain` and casts a yes/no with rationale before escalating to A1.

---

## Key Flows

- F1. Deep verification pass
  - **Trigger:** Project resumed after this requirements doc lands.
  - **Actors:** A2.
  - **Steps:**
    1. Re-execute `pixi run -- python scripts/build_tra_database.py` from the current working tree; record row counts.
    2. Re-execute `pixi run -- python scripts/build_dashboard.py`; confirm `outputs/tra-database/dashboard.html` renders.
    3. Verify S2 outcome: six skills present at `.claude/skills/`, none at `~/.claude/skills/`.
    4. Verify S6 outcome: `git remote -v` shows the private GitHub repo; the remote tree does not contain `TRA-contracts/`; no credentials in commit history.
    5. Reconcile the open issues recorded in `coauthor/2026-05-18-git-good/ca-04-review.md`: the silent deletion of `scripts/sec_edgar/resolve_deferred_ciks.py` and the `tra-packet/SKILL.md` reference to deleted `tra_deferred_review.csv`.
    6. Rewrite `README.md` to reflect the per-document EDGAR acquisition (S7a as actually built) and the retired `tra-packet`.
  - **Outcome:** Working tree state matches a verifiable record; all open issues from prior reviews resolved; README accurate to the pipeline as it actually runs.
  - **Covered by:** R1, R2, R3, R4, R5, R6a.

- F2. Classifier iteration loop
  - **Trigger:** A2 produces a candidate version of the `tra-classify` skill.
  - **Actors:** A1, A2, A3, A4.
  - **Steps:**
    1. A3 runs over `data/edgar-query/exhibits/` and writes one row per document to `data/edgar-query/classifications.csv` with a classification of `yes`, `no`, or `uncertain` plus the signals it matched.
    2. For each `uncertain` row, A4 reads the document and writes a yes/no verdict plus a one-line rationale to the same row.
    3. A1 spot-reviews a sample of A3's `yes` and `no` calls plus the A4 verdicts on the uncertain set.
    4. A1 reports misclassifications (false positives, false negatives, drift cases) to A2 with document identifiers.
    5. A2 revises the classifier — new signals, threshold adjustments, refined heuristics — and the loop repeats from step 1. The loop terminates when A1 accepts the classifier's output without overrides on a stable user-reviewed sample.
  - **Outcome:** A classifier whose yes/no output A1 accepts as the confirmed-TRA-document set. The union of A3's `yes` rows and A4's yes-verdict rows on A3's `uncertain` becomes the input to F3.
  - **Covered by:** R7, R8, R9, R10, R11.

- F3. Remaining pipeline execution (S7c–S8)
  - **Trigger:** F2 produces a confirmed-TRA-CIK list.
  - **Actors:** A2.
  - **Steps:**
    1. Execute S7c (rewrite `tra-download-filings`), S7d (markdown-read switch in `tra-process-filings`), S7e (retire `tra-packet`), S7f (relocate skill-internal scripts), S7g (build `tra-refresh` skill).
    2. Execute S8: run the new acquisition chain end-to-end against the confirmed-TRA-CIK list, regenerate the database and dashboard, write `last_refresh.json`.
    3. Commit and push the regenerated outputs to the private GitHub repo.
    4. Migration acceptance: `git clone` the repository on Windows, install pixi on Windows, run the pipeline end-to-end, verify the same parquet row counts as the WSL build.
  - **Outcome:** Regenerated corpus, parquet outputs, dashboard, and refresh metadata on the private remote; Windows clone reproduces the pipeline; WSL working tree can be deleted.
  - **Covered by:** R6b, R12, R13, R14, R15, R16a, R16b.

---

## Requirements

**Deep verification pass**

- R1. The database build (`scripts/build_tra_database.py`) and dashboard build (`scripts/build_dashboard.py`) re-execute from the current cleaned tree and produce parquet outputs at the recorded row counts (360 / 1635 / 8415) plus a rendering `dashboard.html`.
- R2. The six relocated skills (`tra-download-filings`, `tra-process-filings`, `tra-build-timeline`, `tra-htm-to-md`, `tra-packet`, `sec-edgar`) are confirmed present under `.claude/skills/` and absent from `~/.claude/skills/`.
- R3. The GitHub push outcome is confirmed: `origin` points at the private repo `AlexSulliMora/tra-database`; the remote tree contains no `TRA-contracts/` directory; no credentials are present in any committed file.
- R4. The silent-deletion record for `scripts/sec_edgar/resolve_deferred_ciks.py` is resolved by either restoring the file or amending the signed-off `coauthor/2026-05-18-git-good/inventory.md` with a `delete` row and the cascade rationale. Before choosing the amendment path, A2 must grep the working tree for callers of `resolve_deferred_ciks`; if any surviving script references it, the file must be restored instead.
- R5. The `tra-packet/SKILL.md` reference to the deleted `tra_deferred_review.csv` is resolved (the reference is removed, or the skill itself is deleted per S7e). The previously-flagged `tests/__init__.py` orphan was already resolved on disk before this doc was written (verified: `tests/` directory absent); R5 carries no work for the orphan, only the SKILL.md reference.
- R6a. `README.md` at the project root describes the pipeline as it actually runs after the S7a rework: per-document EDGAR full-text search emitting one row per matched EX-10, then `pull_exhibits.py` downloading the primary documents. No reference remains to the retired three-query union or the allow-list post-filter. Executable during F1.
- R6b. After S7e retires `tra-packet`, the README skill catalog entry for `tra-packet` is removed and any remaining references swept. Executable at F3 start, dependent on S7e completing.

**TRA classifier**

- R7. The `tra-classify` skill is installed at `.claude/skills/tra-classify/` (project-local, auto-loaded by Claude Code) and is invokable as a standalone deterministic program by both the iteration loop (F2) and the future `tra-refresh` skill (S7g).
- R8. The skill emits exactly one of {yes, no, uncertain} per input EX-10 document and writes results to `data/edgar-query/classifications.csv` with the columns `cik, accession, filename, classification, classifier_version, signals_matched`.
- R9. When a document's classification is `uncertain`, the Claude reviewer subagent (A4) reads the document and writes a `reviewer_verdict ∈ {yes, no}` plus a `reviewer_rationale` (one short sentence) to the same row.
- R10. When the user (A1) reports a misclassification on iteration round N with a document identifier, the classifier in round N+1 either classifies that document correctly without entering `uncertain`, or routes it to `uncertain` where A4's verdict matches the user's correction. If A4's verdict on a previously-corrected document contradicts A1's correction, the disagreement escalates to A1 for final judgment; the loop does not advance until A1 confirms the correct classification. The accepted classifier_version is recorded in `data/edgar-query/classifier_acceptance.md` with the user's sign-off.
- R11. The confirmed-TRA-document set is the union of A3-yes rows and A3-uncertain rows where `reviewer_verdict = yes`; the confirmed-TRA-CIK list is the unique set of CIKs across that document set (each EX-10 document carries a list of CIKs per the per-document acquisition shape). The accepted classifier_version is re-run end-to-end over the full corpus before R11's union is computed, so `data/edgar-query/classifications.csv` contains a single uniform `classifier_version` value across all rows feeding the confirmed set.

**Remaining pipeline execution (S7c–S8)**

- R12. The rewritten `tra-download-filings` (S7c) takes the confirmed-TRA-CIK list as input and pulls only filings of form `{8-K, 10-K, 424B1, 424B2, 424B3, 424B4, 424B5}` plus the documents in each filing's index. The IPO-prospectus selection rule from the frozen plan (latest 424B within 7 days of the IPO 8-K Item 1.01 date) is preserved; edge cases are resolved during planning.
- R13. S7d (process-filings reads markdown), S7e (tra-packet retired), S7f (skill-internal scripts relocated under `.claude/skills/<skill>/scripts/`) execute as the frozen plan specifies.
- R14. The `tra-refresh` skill (S7g) reads the prior cutoff from `outputs/tra-database/last_refresh.json` (or falls back to the max `filingDate` in `events.parquet`), uses the same narrow form set as R12, and supports a `--dry-run` mode that reports counts without modifying the parquets. The skill calls `tra-classify` (R7) on any new EX-10 candidates surfaced by the refresh.
- R15. The S8 systematic rerun produces fresh `outputs/tra-database/{tras,events,stock_by_date}.parquet`, a regenerated `dashboard.html`, and a baseline `outputs/tra-database/last_refresh.json` written by the live `tra-refresh` run at the end.
- R16a. After S8 commits and pushes, a `git clone` of the repository on Windows followed by a Windows-side pixi install and pipeline rerun produces parquet row counts matching the WSL build (with deltas attributable to a live `tra-refresh` step documented in `last_refresh.json` if the rerun includes one — the Outstanding Question on test shape settles which mode is canonical). Any cross-platform divergence beyond the documented delta is treated as a replicability bug, fixed, and pushed.
- R16b. After R16a confirms reproducibility, the WSL working tree at `~/research/tra/` may be deleted at the user's discretion (cadence is an Outstanding Question — immediate or kept as fallback for some period).

---

## Acceptance Examples

- AE1. **Covers R1.** Given the current working tree, when `pixi run -- python scripts/build_tra_database.py` runs, the output reports `tras` rows=360, `events` rows=1635, `stock_by_date` rows=8415.
- AE2. **Covers R8, R9.** Given an EX-10 document the classifier scores as `uncertain`, when the Claude reviewer subagent runs, the document's row in `classifications.csv` gains `reviewer_verdict ∈ {yes, no}` and `reviewer_rationale` (one sentence describing the decision).
- AE3. **Covers R10.** Given the user flagged document X as a false negative in iteration round N, when classifier version N+1 runs on document X, the row in `classifications.csv` shows either `classification = yes` or `classification = uncertain` paired with `reviewer_verdict = yes`.
- AE4. **Covers R14.** Given `last_refresh.json` records cutoff date 2026-05-24 and a refresh runs on 2026-08-15, when the dry-run mode is invoked, the skill reports the count of new filings since 2026-05-24 without modifying any parquet.
- AE5. **Covers R16.** Given a fresh `git clone https://github.com/AlexSulliMora/tra-database.git` on Windows and a successful `pixi install`, when the documented end-to-end commands in `README.md` execute, the resulting parquet row counts match the WSL build's row counts exactly.

---

## Success Criteria

- The classifier's confirmed-TRA set is a list the user accepts as complete: no false negatives detected on the final user review pass over A3's `no` rows, no false positives in the input to S7c after the union with A4's verdicts.
- A fresh clone of the repository on Windows (or any system with pixi support) reproduces the pipeline end-to-end with parquet row counts matching the WSL build.
- The compound-engineering planning agent (`ce-plan`) consuming this doc decomposes the work without needing to invent classifier behavior, verification scope, classifier iteration mechanics, or migration semantics.
- The WSL working tree at `~/research/tra/` can be deleted after the Windows clone produces an identical pipeline output, completing the user's eventual-Windows-only migration goal.

---

## Scope Boundaries

- Carrying-values / TRA-liability time series remains deferred from the prior project's out-of-scope list. The S6 successor work (LLM extraction over confirmed contracts) is not part of git-good.
- Analytical changes to the dashboard beyond pointing it at refreshed parquet inputs are out of scope; the existing pages and metrics are preserved as-is.
- Academic paper drafting (the eventual publication this corpus supports) is out of scope; this doc establishes the data foundation only.
- Migration of prior coauthor artifacts (`coauthor/2026-05-18-git-good/ca-*.md`, `coauthor/2026-05-12-edgar-scrape/`, `coauthor/2026-05-18-tra-database/`) into compound-engineering shape is out of scope; they remain as historical record.
- Public release of the GitHub repository is out of scope; the repo stays private under the user's account.
- The S7a per-document EDGAR acquisition rework is not re-litigated; the on-disk state is treated as the starting point for downstream work.

---

## Key Decisions

- **Three-way classification (yes/no/uncertain) over binary.** Makes the uncertain-review tier explicit and lets the user calibrate the classifier's confidence threshold by adjusting what falls into `uncertain`. A binary classifier would force either a hard pre-filter (the rejected `tmp/TRA-classify/` shape) or no filter at all (the user reviewing all 3,025 documents).
- **Claude reviewer subagent (A4) handles uncertain cases before the user.** Reduces user-time burden while preserving zero-false-drop discipline; the user only sees documents the deterministic classifier and Claude reviewer both could not confidently decide.
- **Iterative classifier development with user-reported corrections drives the loop.** No deterministic specification of "is a TRA" exists; the specification emerges from the loop. Per the user's standing preference, the classifier iteration is judgment-heavy enough to warrant a custom agent rather than a generic dispatch (see `feedback_judgment_tasks_custom_agent.md` in user memory).
- **Migration to Windows happens after S8 ships.** Minimizes mid-project tree fragmentation; aligns the migration with the replicability-acceptance gate (the Windows rerun is the test of priority #2). The WSL tree is deleted after the Windows clone produces matching output.
- **Deep verification (re-run S1–S4) over light spot-check.** Publication-grade replicability requires fresh-tree reproducibility, not trust in prior claim records; running the build script is the cheapest way to catch silent regressions from the EDGAR rework or intervening edits.
- **The S7a per-document rework is the starting point for downstream steps.** Re-litigating it would re-open scope; the on-disk state (3,025 EX-10 documents at `data/edgar-query/exhibits/`) is the input the classifier and S7c-downstream consume.

---

## Dependencies / Assumptions

- The pixi environment reproduces on Windows. Pixi supports Windows natively, but `pixi.lock` may need regeneration if any locked package has no Windows wheel. This is unverified at scope-freeze and surfaces during the final migration step (R16) rather than blocking development.
- The 3,025 EX-10 documents at `data/edgar-query/exhibits/` are a stable corpus for classifier iteration. The systematic rerun (S8) regenerates this corpus from a fresh EDGAR full-text search; the regenerated set may differ slightly (new filings posted since the original pull), and the classifier must run on whichever set is current without re-tuning.
- The user has reviewed enough real TRA documents to recognize false positives and false negatives in classifier output by reading the flagged document. The user has stated this explicitly; the iteration loop's correctness depends on it.
- The Claude reviewer subagent (A4) reading a single document can reliably distinguish TRA contracts from documents that merely mention TRAs. This is unverified at scope-freeze and will be calibrated during the first F2 iteration; if A4 is unreliable, A1 takes a larger share of the review burden.
- The compound-engineering workflow files (`docs/brainstorms/`, `docs/plans/`, `docs/reviews/`) and the existing coauthor files coexist in the repo without conflict; the canonical operating rules for new work come from compound-engineering, the prior workflow's frozen artifacts are read-only historical record.
- The Windows host has `git`, internet access to GitHub, and write access to `C:\Users\Sulli\`. Pixi can be installed there per the standard pixi Windows instructions.

---

## Outstanding Questions

### Resolve Before Planning

(none at scope-freeze)

### Deferred to Planning

- [Affects R7, R8] [Technical] What signals should the v0 classifier use beyond centered-title detection for "TAX RECEIVABLE AGREEMENT"? Candidates include: defined-term presence (e.g., "Exchange Basis Adjustment", "Tax Asset"), section-header structure, document length distribution, signature-block presence, exhibit-number context (EX-10.1 vs EX-10.30). The right starting set is determined by sampling confirmed TRAs and confirmed non-TRAs during planning.
- [Affects R7, R8] [Technical] The prior `tmp/TRA-classify/` attempt used `TRA_PHRASE_RE = tax\s+receivable\s+agreement`, matching only the two singular phrase variants; `find_candidates.py` queries four variants, two spelled "tax receivables agreement" (plural). Any phrase-presence signal in the v0 classifier must cover all four variants or it will silently mis-classify documents the prior attempt missed.
- [Affects R7, R9] [Technical] What is the implementation shape of the Claude reviewer subagent (A4) — a standing custom agent definition with the classifier-skill context preloaded, a fresh Agent dispatch per uncertain document, or a batched dispatch over the uncertain set? Sample sizes from the first iteration inform this choice.
- [Affects R10] [Technical] How is the classifier_version recorded — semantic versioning, git SHA of the skill source, monotonic integer? The choice affects the audit trail in `classifications.csv` and `classifier_acceptance.md`.
- [Affects R12] [Needs research] The IPO-prospectus selection rule from the frozen plan (latest 424B within 7 days of the IPO 8-K Item 1.01 date) has edge cases (firms with no IPO 8-K Item 1.01, multiple 424Bs within the window, restated prospectuses). Resolve during planning by sampling the confirmed-CIK list.
- [Affects R16] [Needs research] Does the current `pixi.lock` reproduce cleanly on Windows, or does the Windows install require regenerating the lockfile for that platform? This is best answered by running `pixi install` on Windows once during the F3 migration step.
- [Affects F3] [User decision] Should the WSL tree at `~/research/tra/` be deleted immediately after the Windows clone produces matching output, or kept as a fallback for some period (one week, one month)? The doc currently treats deletion as the end state but the cadence is a user choice.

---

## Deferred / Open Questions

### From 2026-05-24 review

- **F2 stopping rule undefined** — Key Flows F2 step 5, R10 (P1, product-lens + adversarial, confidence 100)

  The loop terminates "when A1 accepts the classifier's output without overrides on a stable user-reviewed sample," but neither "stable sample" nor "without overrides" is defined. There is no sample size, no false-negative budget, no specification of which strata (yes / no / uncertain) the user must review, and no rule for how many consecutive clean iterations count as acceptance. Two reasonable readers will pick different stopping points, and a planner cannot decompose this into bounded work.

  <!-- dedup-key: section="key flows f2 step 5 r10" title="f2 stopping rule undefined" evidence="the loop terminates when a1 accepts the classifier's output without overrides on a stable user-reviewed sample." -->

- **A4 reliability is load-bearing but unverified** — Dependencies, Actors A4 (P1, product-lens + adversarial, confidence 100)

  The whole three-tier design rests on A4 reliably distinguishing TRA contracts from documents that mention TRAs — exactly the discrimination the deterministic classifier could not make. The doc acknowledges this is unverified and says it will be "calibrated during the first F2 iteration" but offers no calibration protocol (sample size, agreement threshold against A1 labels) and no fallback path if A4's agreement with A1 is poor.

  <!-- dedup-key: section="dependencies actors a4" title="a4 reliability is load-bearing but unverified" evidence="the claude reviewer subagent a4 reading a single document can reliably distinguish tra contracts" -->

- **S8 corpus regeneration invalidates classifier acceptance** — Dependencies, F3 step 2 (P1, product-lens + adversarial, confidence 100)

  The classifier is accepted (F2) against the 3,025 documents currently on disk; S8 re-runs the EDGAR acquisition, producing a different corpus (new filings, possibly removed filings, possibly new document shapes the classifier was never iterated against). The assumption "the classifier must run on whichever set is current without re-tuning" lets new documents enter the confirmed set with no human review. No re-acceptance step exists between S8 and S7c. The migration sequencing also lacks a branch for "S8 reveals classifier issues that re-open F2."

  <!-- dedup-key: section="dependencies f3 step 2" title="s8 corpus regeneration invalidates classifier acceptance" evidence="the 3025 ex-10 documents at dataedgar-queryexhibits are a stable corpus for classifier iteration" -->

- **F2 spot-check coverage cannot satisfy success criterion on `no` rows** — Success Criteria, F2 step 3 (P1, adversarial, confidence 75)

  The success criterion demands "no false negatives detected on the final user review pass over A3's `no` rows," but F2 step 3 only requires the user to "spot-review a sample of A3's `yes` and `no` calls." A spot-check sample of ~3000 `no` documents will not detect a low-rate false-negative tail (e.g., 5 missed TRAs out of 3000), yet missed TRAs are exactly the priority-#1 failure mode. Either weaken the criterion to a sample-based bound with explicit power calculation, or strengthen F2 to require a full pass over the `no` set at acceptance time.

  <!-- dedup-key: section="success criteria f2 step 3" title="f2 spot-check coverage cannot satisfy success criterion on no rows" evidence="the classifier's confirmed-tra set is a list the user accepts as complete no false negatives detected" -->

- **R10 acceptance test does not require generalization** — R10, AE3 (P1, adversarial, confidence 75)

  R10 only requires that previously-flagged document X classify correctly in round N+1. A classifier that memorizes reported documents (e.g., by adding their filenames to an allow/deny list) trivially satisfies R10 without generalizing — every iteration overfits to the user's prior corrections while leaving similar unseen documents wrong. The requirement does not separate training and evaluation samples.

  <!-- dedup-key: section="r10 ae3" title="r10 acceptance test is per-document not generalizing" evidence="when the user a1 reports a misclassification on iteration round n with a document identifier the classifier" -->

- **Windows reproducibility test shape unspecified** — R16a, AE5 (P1, adversarial, confidence 75)

  R16a demands the Windows clone produce parquet row counts matching the WSL build, but the pipeline includes a `tra-refresh` step that hits live EDGAR and writes a new `last_refresh.json`. If the Windows rerun includes the refresh step, it pulls any filings posted between the WSL build and the Windows run, producing different row counts deterministically — treating that as a "replicability bug" would be wrong. If the Windows rerun excludes the refresh step, R16a tests parquet read/write parity, not pipeline reproducibility. Pick one mode and name the specific commands the Windows side runs.

  <!-- dedup-key: section="r16a ae5" title="windows reproducibility test shape unspecified" evidence="after s8 commits and pushes a git clone of the repository on windows followed by a windows-side pixi install" -->

- **Three-way classifier `no`-bin is silently unguarded** — Key Decisions, R11 (P2, product-lens, confidence 75)

  The three-way scheme routes `uncertain` to A4 and `yes` to the confirmed set, but `no` rows go nowhere — they are silently dropped. Any false negative in the `no` bin is a permanent miss (priority #1). The design implicitly assumes the deterministic classifier achieves near-zero false-negative rate on `no` calls, which is exactly the property the rejected `tmp/TRA-classify/` filter failed to deliver. Options: (a) A4 also reviews a stratified sample of `no` rows (especially borderline-score) on each iteration; (b) raise the bar for routing to `no` so the `uncertain` bin absorbs the ambiguity at the cost of more A4 calls.

  <!-- dedup-key: section="key decisions r11" title="three-way classifier no-bin unguarded" evidence="the confirmed-tra-document set is the union of a3-yes rows and a3-uncertain rows where reviewer_verdict yes" -->

- **Early Windows pixi-install smoke test** — Key Decisions, R16a (P2, product-lens, confidence 75)

  Migration is deferred to after S8, and `pixi.lock` Windows reproducibility is unverified until then. If a locked package has no Windows wheel (a known pixi failure mode), the user discovers this only after F1+F2+F3 ship. A short `pixi install` test on Windows before classifier work starts would surface this risk early; deferring it to the acceptance gate is asymmetric (low cost to check early, high cost if it fails late). Decide whether to add an early-Windows-check task to F1.

  <!-- dedup-key: section="key decisions r16a" title="early windows pixi-install smoke test" evidence="the pixi environment reproduces on windows pixi supports windows natively but pixilock may need regeneration" -->

- **Confirmed-TRA-CIK list granularity** — F2 outcome, R11, R12 (P2, feasibility, confidence 75)

  R11 derives the confirmed-TRA-CIK list as the union of CIKs across confirmed-TRA documents, and R12 feeds that list into the rewritten `tra-download-filings`. Many EX-10 documents carry multiple CIKs (one filing can be cross-filed by a parent and operating LLC); flattening to a per-CIK list discards the per-document evidence that this CIK actually owns a TRA contract. Downstream would re-pull filings for entities whose only link to a TRA document was being a co-filer. Decide whether F3 input is per-CIK or per-(CIK, accession).

  <!-- dedup-key: section="f2 outcome r11 r12" title="confirmed-tra-cik list granularity" evidence="the confirmed-tra-cik list is the unique set of ciks across that document set each ex-10 document carries" -->

- **S8 reveals classifier issues re-opening F2 — migration branch missing** — Key Decisions, F3 step 4 (P2, adversarial, confidence 75)

  The migration decision presumes S8 ships before Windows migration. But S8 runs the accepted classifier against a potentially-changed regenerated corpus, which could expose classifier failures that re-open F2. The doc has no branch for "S8 reveals classifier issues" — it implicitly assumes S8 either succeeds or fails atomically. The WSL deletion plan would then become destructive of the only environment in which the iteration loop was developed. Defer WSL deletion (R16b) until after Windows reproduces matching output AND A1 signs off on the S8 corpus, not just on the original 3,025-document corpus.

  <!-- dedup-key: section="key decisions f3 step 4" title="s8 reveals classifier issues re-opening f2 migration branch missing" evidence="migration to windows happens after s8 ships minimizes mid-project tree fragmentation aligns the migration" -->
