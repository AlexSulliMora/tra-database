---
date: 2026-05-25
topic: phase-1-discovery-and-acquisition
---

# Phase 1: Discovery and Acquisition of TRA-Mentioning EDGAR Filings

## Summary

Build a one-shot, batch corpus builder that, given a date range, discovers every TRA-mentioning EDGAR filing, downloads the relevant documents per firm into `data/tra-mentions/<firm-slug>/`, emits a canonical manifest, and writes a done marker that Phase 2 reads from. Phase 1 is stateless over its date-range input; Phase 5 owns refresh.

---

## Problem Frame

The TRA database build (`docs/workflow-goal.qmd`) requires a per-firm corpus of every EDGAR filing that meaningfully mentions a Tax Receivable Agreement. The pre-pivot scripts (`scripts/find_candidates.py`, `scripts/pull_exhibits.py`) and skill (`.claude/skills/tra-download-filings/`) implement parts of this acquisition but in a different shape: they discover by EX-10 exhibit hit rather than by filing (missing TRAs disclosed only in 10-K MD&A or 8-K bodies), fetch only the matched document and never the primary doc (so downstream phases have no transaction context), key by CIK rather than firm-slug (so a firm rename or merger fragments per-firm chronological reads), and have no contract with downstream phases about completeness or readiness. Downstream phases (Phase 2's per-firm narrative reader, Phase 3's cross-firm consolidator, Phase 4's timeline and database builders) cannot consume that corpus shape without rework.

---

## Actors

- A1. **Phase 1 operator** — invokes Phase 1 (CLI or script call), monitors logs, investigates failures.
- A2. **Phase 2 reading agent** (downstream consumer) — reads `data/tra-mentions/<firm-slug>/` per firm in chronological order; reads only after the done marker fires.
- A3. **EDGAR** (external system) — provides full-text search, the Submissions API, and archive documents; subject to a 10 req/sec rate cap, a 10,000-result cap per query, and a ~60s indexing lag.
- A4. **Merger-CSV maintainer** (often the same person as A1) — updates `data/cik-mergers.csv` when Phase 2 surfaces a new predecessor/successor linkage from 8-K Item 2.01 narrative; updates affect future Phase 1 runs.

---

## Key Flows

- F1. **Historical build (first run)**
  - **Trigger:** Operator invokes Phase 1 with no prior run state on disk.
  - **Actors:** A1, A3.
  - **Steps:** (1) Run discovery sweep over the configured date range. (2) Build or update the CIK registry from the Submissions API for every CIK in discovery output. (3) For each accession in discovery output, fetch index.json. (4) Download the primary document plus TRA-matched EX-10s per the acquisition policy. (5) Append rows to the manifest as each document is fetched. (6) When every discovered accession has a terminal manifest row, write the done marker.
  - **Outcome:** `data/tra-mentions/<firm-slug>/` populated; manifest complete; done marker in place.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R8, R9, R10, R11, R12, R13, R14.

- F2. **Restart after interruption**
  - **Trigger:** Operator re-invokes Phase 1 after a crash, Ctrl-C, or OS interruption mid-run.
  - **Actors:** A1, A3.
  - **Steps:** (1) Delete any stale done marker. (2) Re-run discovery for the date range (the EdgarClient cache makes this cheap on a recent re-run). (3) For each accession in discovery output, skip fetches for accessions already in the manifest with a terminal fetch_status; fetch the rest. (4) When every discovered accession has a terminal manifest row, write the done marker.
  - **Outcome:** The new run consumes only the fetches that were missing or not yet attempted.
  - **Covered by:** R14, R15, R16.

- F3. **Merger CSV updated and run again**
  - **Trigger:** A4 adds or revises a predecessor/successor row in `data/cik-mergers.csv` after Phase 2 surfaces a new merger linkage; operator re-invokes Phase 1.
  - **Actors:** A1, A4 (often same person), A3.
  - **Steps:** (1) Phase 1 reads the updated `cik-mergers.csv` at run start. (2) For any CIK NOT already in the registry, Phase 1 derives the slug using the merger linkage (predecessor CIKs share the successor's slug). (3) CIKs already in the registry keep their existing slugs; their files do NOT move on disk. (4) The run continues per F1 or F2 for any newly-discovered CIKs.
  - **Outcome:** New CIKs are grouped under the right slug from the start. Existing-CIK reorganization is a Phase 2+ concern (read-time merger awareness), not a Phase 1 concern.
  - **Covered by:** R6, R7.

---

## Requirements

**Discovery**

- R1. Phase 1 sweeps EDGAR full-text search over a configurable date range, defaulting to 2001-01-01 through today (the EDGAR full-text index lower bound), for 5 query variants: the 4 phrase variants `"tax receivable agreement"`, `"tax receivable agreements"`, `"tax receivables agreement"`, `"tax receivables agreements"`, and the standalone-word variant `TRA`.
- R2. Discovery returns every filing whose primary document body or any attached exhibit matched any of the 5 query variants. The discovery output is not pre-filtered by document type — both filings with an EX-10 hit and filings with a body-only hit (10-K MD&A, 8-K body) are kept.
- R3. Discovery time-partitions queries by month. When a month-window query returns a hit count at the 10,000-result cap, Phase 1 treats this as overflow and re-issues the query against two biweekly sub-windows (1st-15th, 16th-end-of-month).
- R4. Discovery covers only filings whose `form` is in the inherited ALLOWED_FORMS list: 10-K, 10-K/A, 10-Q, 10-Q/A, 20-F, 40-F, 6-K, DEF 14A, DEFA14A, DEFM14A, PRE 14A, 8-K, 8-K/A, S-1, S-1/A, S-4, S-4/A, 424B1, 424B2, 424B3, 424B4, 424B5, DRS, DRS/A (21 forms). Form filtering is applied locally on the returned LazyFrame; the EDGAR `forms` query parameter is NOT used (it has a parser bug that silently drops slash-bearing codes).

**Identity and registry**

- R5. For every CIK appearing in discovery output, Phase 1 fetches the Submissions API and records the CIK in `data/cik-registry.parquet` with fields: `cik`, `current_name`, `slug`, `former_names`, `first_filing_date`, `last_filing_date`, `sic`, `state_of_inc`.
- R6. The slug is derived deterministically from the company name active at the time of the CIK's first TRA-related filing in the corpus. Once a CIK has a slug recorded in the registry, that slug is locked — subsequent runs do NOT recompute it, even if EDGAR's `current_name` changes or `data/cik-mergers.csv` is updated.
- R7. Phase 1 reads `data/cik-mergers.csv` (operator-maintained, may be absent or empty on a first run) at run start. Each row maps a predecessor CIK to a successor CIK. When Phase 1 encounters a CIK for the first time (no registry row yet), and that CIK appears as a predecessor in the merger CSV, the slug is taken from (or computed for) the successor CIK. Updates to the CSV affect only first-encounter slug derivation; existing registry entries are not retroactively re-keyed and existing files are not moved.

**Acquisition**

- R8. For each accession in discovery output, Phase 1 fetches the per-accession index at `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-no-dashes>/index.json` to enumerate documents with `type`, `description`, and `size`.
- R9. From each accession's index, Phase 1 downloads exactly three classes of document: (a) the primary document unconditionally; (b) every EX-10.* document that was itself a direct full-text search hit (its body matched any of the 5 query variants in discovery); (c) every EX-10.* document whose `description` field matches a case-insensitive TRA-keyword regex (`tax receivable` OR the standalone-word token `TRA` with word boundaries). EX-10.* documents matching neither (b) nor (c) and all non-EX-10 documents are skipped.
- R10. Downloaded files are written to `data/tra-mentions/<firm-slug>/<accession-no-dashes>/<doc_filename>`. The file tree is content-addressed by the (firm-slug, accession, filename) triple. Files already present on disk are not re-downloaded.

**Output and handoff**

- R11. Phase 1 maintains `data/tra-mentions/manifest.parquet` with one row per fetched (or attempted-and-failed) document. Schema:

  ```
  firm_slug, cik, accession, form, filed_date, doc_filename, doc_type,
  doc_description, url, phrase_variants_matched, exhibit_match_source,
  fetch_status, fetch_ts, byte_size
  ```

  The manifest is the authoritative output; the file tree is a derived cache that can be rebuilt from the manifest plus EDGAR at any time.

- R12. `fetch_status` captures one of: `success`, `not-found-404`, `redacted-403`, `rate-limited`, `parse-error`, `other-error`. Failed fetches are recorded with the appropriate status; they do not abort the run. The byte cache is written only for `fetch_status=success`.

- R13. `exhibit_match_source` captures why the document was downloaded: `primary-doc` (the primary document, fetched unconditionally), `phrase-match` (an EX-10 whose body matched discovery), `description-match` (an EX-10 whose index description matched the TRA keyword regex), or `both` when phrase-match and description-match both apply to the same EX-10.

- R14. When discovery completes for the requested date range AND every accession in discovery output has either a `success` fetch row or a terminal non-success row in the manifest, Phase 1 writes a done marker at `data/tra-mentions/.phase1-done`. The marker is a small file (YAML or JSON) carrying the run's date range, the final manifest revision or content hash, and the run completion timestamp. The done marker is the signal Phase 2 checks before reading any firm directory.

**Restart and idempotency**

- R15. Phase 1 may be interrupted and re-invoked at any time. On re-invocation: (a) any existing `.phase1-done` marker is deleted at run start; (b) discovery re-runs for the date range, reusing cached EDGAR search results via the EdgarClient cache; (c) for each accession in discovery output, Phase 1 skips fetches for accessions already in the manifest with a terminal `fetch_status`; (d) when every discovered accession has a terminal manifest row, the done marker is rewritten.
- R16. Re-running Phase 1 with identical inputs (same date range, same `cik-mergers.csv` content, same EDGAR-corpus state) produces the same manifest content (modulo any new filings EDGAR has indexed since the prior run).

---

## Acceptance Examples

- AE1. **Covers R3.** Given a discovery query for `"tax receivable agreement"` in October 2017 returns 10,000 hits, when Phase 1 detects the overflow (hit count at cap), the October 2017 window is split into `2017-10-01..2017-10-15` and `2017-10-16..2017-10-31` and each sub-window is re-queried.

- AE2. **Covers R7.** Given `data/cik-mergers.csv` contains a row `predecessor=0000111111, successor=0000222222`, and CIK `0000111111` is encountered for the first time in a run (no registry entry yet), when Phase 1 derives the slug for `0000111111`, the slug is taken from `0000222222`'s registry entry (or computed from `0000222222`'s name at first TRA filing if `0000222222` is not yet in the registry).

- AE3. **Covers R6, R7.** Given CIK `0000333333` is already in `data/cik-registry.parquet` with slug `acme-holdings`, and the operator subsequently adds `predecessor=0000333333, successor=0000444444` to `data/cik-mergers.csv`, when Phase 1 re-runs, `0000333333`'s files remain at `data/tra-mentions/acme-holdings/`. The merger linkage is recorded but does not move files; downstream phases consult `cik-mergers.csv` for merger-aware reading.

- AE4. **Covers R9.** Given an accession contains three EX-10 attachments — EX-10.1 was a direct full-text search hit, EX-10.2 has description "Material Definitive Agreement" (no TRA keywords), EX-10.3 has description "Tax Receivable Agreement Amendment No. 2" — when Phase 1 processes the accession, it downloads the primary document, EX-10.1 (`exhibit_match_source=phrase-match`), and EX-10.3 (`description-match`); EX-10.2 is skipped.

- AE5. **Covers R12, R14.** Given Phase 1 discovery returns 100 accessions, of which 98 fetch successfully, 1 returns HTTP 404 (withdrawn filing), and 1 returns HTTP 403 (redacted exhibit), when Phase 1 finishes processing, the manifest contains 98 rows with `fetch_status=success`, 1 row with `fetch_status=not-found-404`, 1 row with `fetch_status=redacted-403`, and the done marker is written.

- AE6. **Covers R15, R16.** Given Phase 1 is interrupted after writing 50 success rows of 100 discovered accessions to the manifest, when the operator re-invokes Phase 1 with the same date range, Phase 1 skips the 50 manifested-success rows and fetches only the remaining 50 (modulo any new filings EDGAR has indexed since the prior run).

---

## Success Criteria

- Phase 2's per-firm reader, given a firm directory at `data/tra-mentions/<firm-slug>/` and the done marker present, can iterate every TRA-relevant filing for that firm in chronological order (by `filed_date` in the manifest) without needing to re-discover or re-fetch anything from EDGAR.
- A downstream consumer (Phase 2-5, or a human auditor) can identify every coverage gap (HTTP 404, redacted, errored) by querying the manifest's `fetch_status` column without re-querying EDGAR.
- Re-running Phase 1 after a successful run, with no changes to inputs or EDGAR state, performs zero document fetches (all manifest rows present with terminal status; idempotency holds).
- A user can spot-check the corpus by opening `data/tra-mentions/<firm-slug>/<accession>/<filename>` directly — no database query or tool layer required to navigate the file tree.

---

## Scope Boundaries

- Phase 5 refresh primitives (Submissions-API polling per known CIK, daily-index walk for new CIKs, SEC RSS for real-time triggers) — Phase 1 is stateless over its date range; Phase 5 invokes Phase 1 with the right date range to extend the corpus.
- Pre-2001 filings — outside the EDGAR full-text search index lower bound. Capturing pre-2001 TRAs would require a separate bulk-index crawl design.
- Automated predecessor/successor CIK detection from 8-K Item 2.01 narrative — handled by Phase 2 (reader may flag candidates); operator updates `data/cik-mergers.csv` manually.
- HTML-to-markdown cleanup of fetched documents — handled by `.claude/skills/tra-htm-to-md/`, not Phase 1.
- Reading filings narratively (Phase 2's job), cross-firm contract consolidation (Phase 3), per-firm and per-TRA timelines plus structured database tables (Phase 4).
- Recursive bisection of overflow windows keyed on `total.relation == "gte"` plus a persistent windows table — dropped in HITL ideation review as over-engineering for the expected overflow rate; the heuristic 10k-hit-count halving in R3 is sufficient.
- Pre-filtering filings for TRA substance — Phase 1 saves any filing meeting the discovery query (including boilerplate carve-outs and negative-covenant references); Phase 2's reader makes the substance call per the workflow goal.
- Streaming per-firm handoff — Phase 1 is a batch (R14); Phase 2 reads only after the done marker fires for the whole corpus.
- Concurrent Phase 1 invocations against the same output directory — the EdgarClient rate cap requires single-process execution; concurrent processes would breach the 10 req/sec hard limit.

---

## Key Decisions

- KD1. **Filing-level discovery over EX-10-only filter.** Closes the recall gap on TRAs disclosed only in body text (10-K MD&A, 8-K body) at the cost of more index.json round-trips per accession.
- KD2. **Index-first acquisition with three exhibit classes (primary, phrase-match, description-match).** Catches TRA-relevant content without bulk-pulling unmatched EX-10s (credit agreements, employment agreements, lease agreements can be hundreds of pages each).
- KD3. **Standalone-word "TRA" as the fifth phrase variant in a single discovery pass.** Simpler than a two-pass CIK-restricted backfill; EDGAR full-text search treats quoted phrases as whole-token matches, so the standalone token does not collide with substrings like `transfer` or `transaction`.
- KD4. **Canonical manifest as the primary output; file tree is derived cache.** Every downstream phase reads the manifest, not the filesystem; EDGAR documents are immutable so the byte cache can always be regenerated.
- KD5. **CIK registry with deterministic slug from name at first TRA filing, plus operator-maintained merger CSV.** Stable slug per CIK over the lifetime of the corpus; merger linkages are explicit and human-curated rather than inferred.
- KD6. **Slug per CIK locked on first encounter; merger-CSV updates do NOT retroactively re-key existing files.** Avoids file-tree reorganization on later runs. Merger-aware reading is a downstream (Phase 2+) read-time concern, not a Phase 1 storage concern.
- KD7. **Stateless Phase 1 over date range; Phase 5 owns refresh.** Decouples discovery+acquisition from delta detection, lets each evolve independently.
- KD8. **Batch handoff over streaming per-firm.** Simpler contract; Phase 2 doesn't run partial state. Phase 2 polls the done marker before reading any firm directory.
- KD9. **Inherit existing ALLOWED_FORMS (21 forms) including foreign-issuer and confidential-draft forms.** Maximum recall; some forms (20-F, 40-F, 6-K, DRS) are rarely TRA-relevant but the cost of including them is small.
- KD10. **Date range 2001-01-01 to today as default.** EDGAR full-text index lower bound; pre-2001 TRAs are rare (the Up-C IPO structure became common mid-2000s) and capturing them would require a different discovery design.
- KD11. **Heuristic 10k-hit-count halving for overflow (not recursive bisection on `total.relation == "gte"`).** Operator-decided in HITL ideation review; over-engineering for the expected rate of overflow on TRA queries.
- KD12. **Manifest is the checkpoint; restart skips already-fetched accessions.** Standard append-only ETL idempotency. The manifest is the canonical "what's done" record across interrupted runs.

---

## Dependencies / Assumptions

- D1. EDGAR APIs are reachable and respect the documented 10 req/sec rate cap (enforced single-process via the existing `scripts/sec_edgar/` `EdgarClient`).
- D2. `data/cik-mergers.csv` is operator-maintained. On a first run it may be absent or empty; Phase 1 must handle this gracefully.
- D3. EDGAR's full-text search treats quoted phrases and bare tokens as whole-token matches (no substring matches), so the standalone-token `TRA` query does not match `transfer`, `transaction`, `treasury`, etc.
- D4. EDGAR's ~60s indexing lag is acceptable for Phase 1's purposes; freshly-accepted filings may not appear in a run that begins within a minute of their acceptance. Phase 5's refresh mechanism is responsible for closing this gap on subsequent runs.
- D5. Disk capacity is sufficient for the corpus on the order of hundreds of MB to a few GB (based on the existing `TRA-contracts/` benchmark).
- D6. The `EdgarClient` in `scripts/sec_edgar/` handles rate-limiting, transient-error retries, and response caching. Phase 1 must NOT add a second throttle layer or duplicate the cache logic.
- D7. The set of EDGAR `file_type` values returned for EX-10.* exhibits has been characterized empirically (per `scripts/find_candidates.py` `EX10_FILE_TYPE_PATTERN`): `EX-10`, `EX-10.1` through `EX-10.N`, `EX-10.A`, `EX-10.(A)`, `EX-10.HTM`, etc. Phase 1 inherits this pattern for EX-10 identification.

---

## Outstanding Questions

### Resolve Before Planning

(None — all blocking product decisions were resolved during dialogue.)

### Deferred to Planning

- [Affects R5, R6][Technical] Slug-derivation algorithm: which `slugify` implementation (e.g., `python-slugify`, custom), collision-suffix policy (numeric suffix? CIK-suffix?), treatment of company names with `&`, `/`, parentheses, or non-ASCII characters.
- [Affects R11][Technical] Manifest write cadence: per-fetch flush (most durable, slower), per-firm flush (batched commits), or per-N-fetches buffer? The choice affects restart granularity and crash-loss tolerance.
- [Affects R8, R9][Technical] index.json fetch parallelism within the 10 req/sec rate cap: sequential, limited-concurrency, or batched per firm? Should be planned against the existing `EdgarClient` concurrency model.
- [Affects R14, R15][Technical] Done-marker lifecycle: deleted at start of every run, written on success — what's the operator-visible signal that a run is in progress (vs successfully finished, vs crashed)?
- [Affects R10][Technical] File-tree write strategy: per-doc atomic write (write-to-tmp-then-rename within the firm directory) vs direct write? Concurrent runs against the same output directory are out of scope but partial-file-on-crash should be considered.
- [Affects R3][Technical] Halving behavior on multi-overflow: if both biweekly halves of a month also hit the 10k cap, what's the next level (weekly? daily?)? Likely a non-issue empirically for TRA queries given current volumes, but should be planned.
- [Affects R7][Needs research] Format and validation of `data/cik-mergers.csv`: column names, header row, validation on read (warn on bad CIKs vs fail vs skip), idempotency rules for duplicate predecessor entries.
- [Affects R12][Technical] Definition of "terminal" status for retry purposes: are `rate-limited` and `other-error` retryable in a single run (with backoff) before being recorded, or always recorded immediately?
