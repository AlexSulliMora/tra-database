---
date: 2026-05-25
topic: phase-1-design
focus: All of Phase 1 of the per-firm narrative pipeline (`docs/workflow-goal.qmd`)
mode: repo-grounded
---

# Ideation: Phase 1 of the TRA pipeline

## Grounding Context

Phase 1's job per `docs/workflow-goal.qmd`: end-to-end, populate `data/tra-mentions/<firm-slug>/` with every filing on EDGAR that meaningfully mentions a Tax Receivable Agreement. One EDGAR full-text search step, grouped by filer CIK, downloads the primary document of each TRA-mentioning filing plus the EX-10.\* exhibits that themselves mention TRAs. Filings whose only mention is boilerplate carve-outs are still downloaded; Phase 2 makes the substance call. The pre-pivot scripts and skills are raw material, not baseline:

* `scripts/find_candidates.py` — sweeps EDGAR full-text search by month for 4 phrase variants; halves to biweekly bounds on the 10k-result cap; unions on `(accession, primary_doc)`; *filters to EX-10.* exhibits only\* (drops body-doc hits); writes `data/edgar-query/full-text.parquet`.

* `scripts/pull_exhibits.py` — reads the parquet; fetches `<accession>_<primary_doc>` per row; does NOT fetch primary documents (10-K bodies, 8-K bodies); writes a narrow `manifest.csv`.

* `.claude/skills/tra-download-filings/` — per-CIK skill (legacy shape — assumes a CIK list exists). Runs three queries: 4 phrase variants, bare token "TRA", corporate-events phrases ("Chapter 11", "going-private", etc.). The workflow goal drops the corporate-events query; Phase 2's reader will get transaction context from the primary doc.

* `scripts/sec_edgar/` — rate-limited (10 req/sec target), cache-aware EDGAR client.

Hard EDGAR constraints: 10 req/sec rate cap; 10,000-result hard cap per query (`from + size <= 10000`); `forms` query parameter silently drops slash-bearing codes (`10-K/A`, `S-1/A`); CIK must be zero-padded to 10 digits; text index starts 2001; \~60s indexing lag; Submissions API exposes `formerNames` but does NOT link predecessor/successor CIKs across mergers (linkage comes from 8-K Item 2.01 narrative); some filings mention only the abbreviation "TRA" after defining it earlier.

External grounding: sec-api.io, edgartools, OpenEDGAR, EDGAR-CRAWLER (lefterisloukas), CourtListener/RECAP, OpenAlex harvest patterns, Notre Dame SRAF master.idx approach, Sigstore Rekor-Monitor, CouchDB `_changes` replication.

## Topic Axes

1. **discovery** — query design (phrases, abbreviations, event terms); unit of discovery (exhibit vs filing); 10k-cap handling; time-partitioning.
2. **acquisition** — per-hit download policy (matched doc only, primary doc plus matched EX-10s, all EX-10s); identifying TRA-mentioning EX-10s without fetching bodies; handling body-mention-only TRAs.
3. **identity-and-layout** — CIK to firm-slug mapping (formerNames, predecessor/successor across mergers); per-firm directory layout; idempotency.
4. **refresh** — Phase 5 hook: high-water mark, window overlap for indexing lag, detecting new firms, what state Phase 1 persists between runs.

## Ranked Ideas

### 1. Filing-level discovery (drop the EX-10-only filter)

**Description:** Discovery returns every TRA-mentioning filing accession, not just hits whose matched document was an EX-10 exhibit. The current `find_candidates.py` filters to EX-10.\* hits, dropping cases where a TRA is disclosed only in a 10-K MD\&A or 8-K body without a separate exhibit (e.g., a tax footnote disclosing a TRA liability with no contract re-attached). Filing-level discovery keeps those filings; the downstream acquisition step (idea 3) decides what to fetch.

**Axis:** discovery

**Basis:** `direct:` `find_candidates.py` comment "Keep only the documents that themselves matched the TRA phrase and are EX-10.\* exhibits"; `docs/workflow-goal.qmd` "downloads the primary document of each TRA-mentioning filing PLUS the EX-10.\* exhibits that themselves mention TRAs."

**Rationale:** Closes a systematic recall gap. Any TRA disclosed only in body text — payment amounts in a tax footnote, an amendment described in MD\&A, a settlement disclosed in subsequent-events — is currently invisible to the pipeline. The cost is more accessions to evaluate via index.json; the benefit is corpus completeness.

**Downsides:** Larger candidate set means more index-fetch overhead. Some body-only mentions will be boilerplate that Phase 2 discards, but Phase 2 already makes the substance call per the workflow goal.

**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

### 2. Include standalone-word "TRA" as a fifth phrase variant in the initial discovery query

**Description:** Add `TRA` as a standalone-word query alongside the 4 spelled-out phrase variants in the single-pass discovery sweep. EDGAR full-text search treats the bare token `TRA` as a token match, so this catches abbreviation-only filings — later 10-Ks, amendments, restatements that defined "TRA" earlier in their text and used only the abbreviation thereafter — without a separate per-CIK pass.

**Axis:** discovery

**Basis:** `direct:` hard constraint "Some filings mention only the abbreviation 'TRA' (no spelled-out phrase) after defining it earlier; phrase-only queries miss these." EDGAR full-text search supports standalone-word queries, so the bare token `TRA` can be added to the existing phrase-variant union without infrastructure changes.

**Rationale:** Closes the abbreviation-only recall gap with one additional phrase variant in the existing single-pass union. Simpler than a two-pass CIK-restricted design — no dependency between passes, no per-CIK query explosion.

**Downsides:** Quoted `"TRA"` matches only the exact standalone token — no substring matches like `transfer` or `transaction` — so the false-positive surface is narrow (rare standalone uses of "TRA" in unrelated SEC contexts, e.g., Trade Reform Act references in pre-1990s filing histories). Any residual noise is filtered at the EX-10 description-screen stage of acquisition (idea 3).

**Confidence:** 90%
**Complexity:** Low
**Status:** Unexplored

### 3. Index-first acquisition: primary doc, phrase-matched exhibits, and description-matched EX-10s only

**Description:** For every discovered accession, fetch the small per-accession index at `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-no-dashes>/index.json` first — one cheap request enumerates every document in the filing with `type`, `description`, and `size`. Then download exactly three classes of document: (a) the primary document unconditionally (Phase 2 needs it for transaction context); (b) every EX-10 that was a direct full-text search hit (its body matched the TRA phrase or the standalone-word `TRA`); (c) every EX-10 whose `index.json` description matches a TRA-keyword regex. Do not bulk-pull unmatched EX-10s — some EX-10s are hundreds-of-page credit agreements, and Phase 2 should not read them without a signal that they are TRA-relevant.

**Axis:** acquisition

**Basis:** `direct:` `pull_exhibits.py` fetches `<accession>_<primary_doc>` with no index round-trip and does NOT fetch primary documents. `external:` EDGAR per-accession index.json structure documented across SEC docs and `sec-api.io` / `edgartools` library docs. `external:` RECAP discovery-hydration separation (<https://deepwiki.com/freelawproject/courtlistener/2.2-recap-data-processing>).

**Rationale:** The primary document gets fetched so Phase 2 has transaction context. The phrase-matched-EX-10 plus description-matched-EX-10 union catches TRA-relevant exhibits with high precision while skipping irrelevant EX-10s (credit agreements, employment agreements, lease agreements) that would otherwise burden Phase 2 with hundreds of pages of unrelated material. The description-string match also gives a free per-exhibit confidence tier that survives to the manifest, useful for Phase 2 prioritization.

**Downsides:** One additional small HTTP request per accession (rate budget). Description-string heuristic can miss TRA-relevant exhibits filed under a generic description like "Material Contract" — those are recovered only when the EX-10 was itself a direct full-text search hit (class b). When neither (b) nor (c) applies, the exhibit is skipped; the primary document still carries any TRA context discoverable from the body.

**Confidence:** 90%
**Complexity:** Medium
**Status:** Unexplored

### 4. Canonical Phase 1 manifest as primary output

**Description:** Phase 1's authoritative output is `data/tra-mentions/manifest.parquet` with one row per fetched document and a fixed schema:

```
firm_slug, cik, accession, form, filed_date, doc_filename, doc_type,
doc_description, url, phrase_variants_matched, exhibit_match_source,
fetch_status, fetch_ts, byte_size
```

The on-disk file tree is a derived cache that can be rebuilt from the manifest plus EDGAR at any time. Every downstream phase reads the manifest, not the filesystem. `fetch_status` captures success / 404 / rate-limited / parse-error so coverage gaps are queryable without re-hitting EDGAR. `phrase_variants_matched` and `exhibit_match_source` (which query produced the hit) preserve evidential attribution.

**Axis:** acquisition

**Basis:** `direct:` existing `pull_exhibits.py` writes a narrow `manifest.csv` missing phrase-variant attribution, primary-document rows, and failure rows. `external:` RECAP discovery-hydration separation; CouchDB and npm replication pattern of treating the metadata log as the canonical artifact and the bytes as a derived cache.

**Rationale:** Highest-leverage idea in the set — every downstream phase inherits a stable, complete API. Phase 5 refresh becomes "find accessions not in the manifest"; Phase 2 reads filings in chronological order via a manifest query rather than walking the directory tree; Phase 3 weights cross-firm evidence via `phrase_variants_matched`. EDGAR documents are immutable (accession numbers are permanent), so re-fetchability is guaranteed and the byte cache can always be regenerated.

**Downsides:** Manifest schema is a one-way design door — adding columns later is easy, but removing or renaming forces Phase 2+ rewrites. Worth a deliberate schema review before the first write.

**Confidence:** 90%
**Complexity:** Medium
**Status:** Unexplored

### 5. CIK registry artifact with firm-slug derivation and merger table

**Description:** Phase 1 writes `data/cik-registry.parquet` with one row per discovered CIK: `(cik, current_name, slug, former_names, first_filing_date, last_filing_date, sic, state_of_inc)`, derived from the EDGAR Submissions API. `slug` is computed deterministically by slugifying the name active at first TRA filing, with a numeric suffix on collision. A small hand-curated `data/cik-mergers.csv` records predecessor/successor CIK linkages discovered in 8-K Item 2.01 narrative — the linkage EDGAR does not expose programmatically. All `data/tra-mentions/<slug>/` directories are named from the registry; no later phase re-derives slugs from raw names.

**Axis:** identity-and-layout

**Basis:** `direct:` hard constraint "Submissions API exposes `formerNames` but does NOT link predecessor/successor CIKs across mergers; that linkage comes from 8-K Item 2.01 narrative." `external:` `data.sec.gov/submissions/CIK##########.json` structure documented at <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>.

**Rationale:** Without a stable registry, a firm rename produces split directories and Phase 2's chronological read fragments across them. The merger CSV is small and cheap to maintain (only TRA-relevant mergers matter, on the order of dozens to low hundreds); it is the only way to handle true predecessor/successor linkage given API limits.

**Downsides:** Slug collisions are inevitable at scale (multiple firms named "Spinco Inc." post-spinoff); the disambiguation policy (CIK suffix? founding year?) needs an explicit decision. The merger CSV is human-maintained, which is a process commitment.

**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 6. Stateless Phase 1; refresh primitives owned by Phase 5

**Description:** Phase 1 is designed as a pure function over a date range: given `(start_date, end_date, query_set)`, it produces or extends the manifest plus file tree. It carries no refresh state, no high-water mark, no "what did the last run see." Phase 5 owns refresh primitives and may use any combination of:

* **Submissions-JSON polling per known CIK** for delta filings (cheap, narrow; catches new filings at known TRA-filers).

* **EDGAR daily-index files** at `/Archives/edgar/daily-index/` for a write-ahead-log-style scan of new accessions across all CIKs (catches new TRA-filer firms).

* **SEC RSS feed** at `sec.gov/structureddata/rss-feeds-submitted-filings` for near-real-time triggers.

Phase 5 invokes Phase 1 on the delta date range; idempotency from idea 4 makes overlap safe.

**Axis:** refresh

**Basis:** `external:` CouchDB `_changes` since-sequence and write-ahead-log patterns (<https://docs.couchdb.org/en/stable/replication/protocol.html>). SEC RSS feeds documented at <https://www.sec.gov/structureddata/rss-feeds-submitted-filings>. `reasoned:` Decoupling refresh from Phase 1 lets Phase 5 evolve independently (polling vs push, per-CIK vs cross-CIK) without forcing Phase 1 schema changes.

**Rationale:** Refresh is a structurally different problem from discovery+acquisition (real-time vs batch, narrow vs wide, known-CIK vs new-CIK) and benefits from a different design. Splitting the primitives lets each be sized to its actual cost rather than forcing one mechanism to cover all cases.

**Downsides:** Defers a real design question (refresh) to Phase 5 rather than answering it now. Risks a Phase 5 design that needs Phase 1 state Phase 1 does not expose.

**Confidence:** 70%
**Complexity:** Low (the choice is structural; the deferred implementation work is in Phase 5)
**Status:** Unexplored

## Rejection Summary

| #  | Idea                                                                          | Reason rejected                                                                                                                                                                                                      |
| :- | :---------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| H  | Group by contract identity, not CIK                                           | Phase 3 scope creep; Phase 1 does not know contract identity yet. Re-keying later from CIK-layout to contract-layout is cheap given the canonical manifest (idea 4).                                                 |
| M  | Phase 1 as three named substeps with separate artifacts                       | Duplicates idea 5 (canonical manifest already provides the substep boundary); adds organizational overhead without new capability.                                                                                   |
| S  | Seed CIK universe from bulk submissions.zip before any full-text search query | Too expensive for marginal recall: full-text search already discovers TRA-filer CIKs in the first phrase pass; the 1.5 GB bulk file pays a cost without changing what gets found.                                    |
| W  | Entrez ESearch handle pattern (parquet as append-only ID log)                 | Analogy does not transfer cleanly — EDGAR has no server-side handle, and `pull_exhibits.py` already treats the parquet as a work queue.                                                                              |
| X  | Zero-LLM deterministic title-band gate at Phase 1                             | Conflicts with the documented Phase 1/Phase 2 contract: "Filings whose only TRA mention is non-substantive boilerplate are still downloaded; Phase 2 makes the substance call." Do not pre-filter what Phase 2 owns. |
| Y  | Phrase-variant overlap analysis (merge redundant phrase variants)             | Below ambition floor for ideation — this is a tactical optimization to do inline in the find\_candidates.py implementation, not a design question worth team discussion.                                             |
