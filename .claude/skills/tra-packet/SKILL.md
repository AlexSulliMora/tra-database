---
name: tra-packet
description: >-
  Assemble a per-firm evidence packet for manual review of a Tax Receivable
  Agreement (TRA) status across SEC filings. Use this skill when a single
  company has been flagged for TRA review (active, amended, terminated,
  expired, transferred, or unknown) and a human reviewer needs an
  organized, source-cited timeline plus a TOC-navigable list of every
  TRA-mentioning filing. Typical trigger: "investigate the TRA status for
  CIK X / firm Y and write a packet". Pair with the sec-edgar skill for
  filing fetches; this skill handles the firm-level evidence-assembly
  workflow on top.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# TRA evidence-packet skill

## Purpose

For one firm flagged with an ambiguous TRA status, build a single
markdown packet that gives a human reviewer enough source-cited
material to decide what happened to the TRA without re-reading the
firm's entire filing history. The packet is the artifact the reviewer
reads; it is not a classifier output.

The skill exists because regex-only verification across filings
(method used by `scripts/sec_edgar/resolve_deferred_ciks.py`) produced
too many `requires_manual_followup` rows. The packet trades full
automation for high-recall evidence assembly the reviewer trusts.

## Two-stage workflow

The packet is built in two distinct stages with different actors:

1. **Mechanical assembly** (deterministic Python helpers). Pulls the
   firm's full filing history, filters to the relevant form types,
   detects which filings mention "tax receivable agreement",
   precomputes plain-text excerpts and TOC anchor indexes per
   filing, collects unique TRA-contract exhibits, fetches the XBRL
   TRA-liability time series, and writes the packet markdown with
   structured sections plus placeholders for the headline, TRA event
   timeline, per-filing notes, and open questions.

2. **Reviewer-agent fill-in** (a fresh-context LLM agent). For each
   TRA-mentioning filing in the timeline, the reviewer agent loads
   the cached excerpts file and the cached TOC index, navigates to
   the TRA-relevant sections, reads them, and records findings in the
   per-filing-notes block. The agent then fills in the TRA event
   timeline at the top of the packet, writes the headline summary,
   and writes the open questions.

Reasoning for the split: the mechanical stage is cheap and rerunnable
deterministically; the reviewer stage is expensive (LLM time,
navigating tens of filings) and benefits from a fresh context per
firm.

## Inputs

- A single CIK (integer or zero-padded string).
- The firm's row from `tra_deferred_review.csv` (or any equivalent
  registry of pre-existing manual notes the skill should treat as
  primary input rather than re-derive).
- Optional: a packet output directory (default:
  `coauthor/2026-05-12-edgar-scrape/findings/packets/<slug>/`).

## Output

`coauthor/2026-05-12-edgar-scrape/findings/packets/<slug>/<slug>.md`,
plus a `coauthor/.../packets/<slug>/exhibits/` subdirectory holding
any TRA-contract exhibits identified. The packet directory holds the
markdown plus the exhibits directory; per-filing helper artifacts
(cached excerpts, cached TOC indexes) live alongside the cached
filing bodies under `.tra_history_cache/edgar_archives/`.

The packet's structure is fixed:

1. **Headline summary** (one short paragraph at the top; placeholder
   in the mechanical packet, filled by the reviewer agent).
2. **Existing pipeline signals** (CSV columns, verbatim).
3. **Prior manual note** (verbatim) if present.
4. **TRA event timeline** (structured event table; placeholder in
   the mechanical packet, filled by the reviewer agent).
5. **TRA exhibits** (manifest of unique TRA-contract documents,
   deduped by content hash, populated mechanically).
6. **XBRL TRA-liability series** (Company Concept API time series,
   populated mechanically; or a note that no standard concept
   resolved if the firm custom-tagged).
7. **Filing timeline** (table: filed, form, accession, tra_mention,
   items, doc).
8. **Per-filing notes** (one entry per TRA-mentioning filing;
   placeholder in the mechanical packet, filled by the reviewer
   agent. Each entry carries the path to the cached excerpts file
   and the cached TOC index for that filing).
9. **Open questions for the reviewer** (placeholder; filled by the
   reviewer agent).

## Stage 1: mechanical assembly

### Step 1: load the firm row

Read the CSV row for the target CIK from `tra_deferred_review.csv`.
Keep every column. The columns named `Manual Check`, `Source:`, and
`Source context:` (when populated) are the reviewer's prior work; they
go into the packet verbatim and frame the open questions later. Do
not re-derive what the reviewer has already concluded.

### Step 2: pull the filing history

Use the `sec-edgar` skill's `fetch-by-CIK` operation (function:
`sec_edgar.submissions.fetch_submissions`). Filings are immutable
once accepted, so the cache freshness window can be treated as
infinite for this purpose; pass `cache_max_age_s=None` to do so.

### Step 3: filter to the packet's filing list

Use `tra_packet.timeline.build_filing_list(submissions_lf)`. The
filter covers the firm's full lifetime:

- Every 10-K and 10-K/A.
- Every 10-Q and 10-Q/A.
- Every 8-K and 8-K/A. No item-code filter; the reviewer agent needs
  full coverage to develop firm-specific knowledge.
- Every DEF 14A.
- The earliest S-1 / S-1/A only.

Forms intentionally omitted: 4 (insider transactions), 144 (Rule 144
sales), SC 13G / SC 13D (beneficial ownership), 25 (delisting), 6-K,
20-F (foreign issuers; handle separately if encountered), and
prospectus variants other than S-1.

### Step 4: detect TRA mentions and precompute helpers per filing

For each filing in the list:

a. Fetch the primary document with
   `sec_edgar.archives.fetch_document(cik, accession, primary_doc)`.
b. Evaluate `tra_packet.sections.has_tra_mention(body)`.
c. If True: precompute the helpers and write them to the cache
   alongside the HTML body.

The two helper files saved per TRA-mentioning filing:

- `<filename>.tra_excerpts.txt`: one plain-text excerpt per TRA
  mention. Each excerpt is a ~600-character window stripped of HTML
  tags. Each is annotated with `in_table=True|False`; matches inside
  non-GAAP reconciliation tables (Adjusted EBITDA, Reconciliation of
  ..., Non-GAAP Measures) are flagged so the reviewer can skip them.
  Functions: `tra_packet.excerpts.extract_tra_excerpts(body)` plus
  `tra_packet.excerpts.write_excerpts_to_cache(...)`.

- `<filename>.toc.tsv`: TSV with columns
  `heading, char_offset, anchor_id, source`. Source values: `h_tag`
  (semantic `<hN>` heading), `named_anchor` (`<a name="X">` plus
  following text), `typographic` (large-font or bold heading
  candidate). The reviewer agent loads this TSV to navigate; an
  empty TSV means the agent falls back to text search inside the
  body. Functions: `tra_packet.toc.extract_toc(body)` plus
  `tra_packet.toc.write_toc_to_cache(...)`.

### Step 5: collect TRA-contract exhibits

Call `tra_packet.exhibits.collect_tra_exhibits(cik_unpadded, filings,
exhibits_dir, client)`. The helper walks every filing's full-submission
SGML wrapper, identifies `EX-10.*` documents, fetches each candidate,
and keeps only those that (a) contain the TRA phrase at least three
times and (b) include a contract-shape marker (WHEREAS, NOW THEREFORE,
ARTICLE I, Section 1.01, etc.). Exhibits are saved under
`packets/<slug>/exhibits/<filing-date>_<accession>_<slug>.htm` and
deduped by SHA-256 content hash so a contract re-attached to a
subsequent 10-K does not produce a second copy.

### Step 6: fetch the XBRL TRA-liability series

Call `sec_edgar.concept.fetch_tra_liability_series(cik)`. The helper
walks a fallback chain of standard us-gaap concepts:
`LiabilitiesUnderTaxReceivableAgreements`,
`LiabilitiesUnderTaxReceivableAgreementCurrent`,
`LiabilitiesUnderTaxReceivableAgreementNoncurrent`,
`DeferredTaxLiabilitiesNoncurrent`. The first to return data wins.

When one of the first three (TRA-specific) tags hits, the returned
series carries `requires_verification = False`: the values are the
TRA liability directly. When the walk falls through to
`DeferredTaxLiabilitiesNoncurrent` (a generic noncurrent deferred-tax
liability, not TRA-specific), every row carries
`requires_verification = True` and the meta-dict's `tag_used` differs
from its `tag_requested`. The mechanical packet then prefixes the
XBRL section header with a `(FALLBACK TAG: ...)` warning so the
reviewer agent knows the values may represent a different liability
category.

If all four return 404, the firm used a filer-specific custom tag;
the packet records the fallback walk and the reviewer agent reads
the liability directly from the periodic filings' tax footnotes.

### Step 7: write the mechanical packet

Call `tra_packet.timeline.write_packet(ctx, timeline_rows,
headline_summary, saved_exhibits=..., concept_meta=...)`. The function
writes the markdown at the canonical path and returns the `Path`. The
mechanical packet ships with placeholder content in the headline
summary, TRA event timeline, per-filing notes, and open questions
sections; the reviewer agent fills these in next.

## Stage 2: reviewer-agent fill-in

The mechanical packet hands off to a fresh-context LLM reviewer
agent. The agent receives: (a) a path to the mechanical packet, and
(b) the firm's CIK and CSV row. It produces an updated packet with
the placeholder sections filled in.

### Reviewer workflow

For the firm:

1. Read the mechanical packet's pipeline signals, prior manual note,
   filing timeline, exhibits manifest, and XBRL TRA-liability series.
   The XBRL series is the first place to look: it will often answer
   the question "when did the TRA liability hit zero" directly,
   without reading any narrative.

   **Verify before citing the XBRL series.** If the XBRL section
   header carries the `(FALLBACK TAG: ...)` warning, every row in
   that series has `requires_verification = true`: the values come
   from `DeferredTaxLiabilitiesNoncurrent`, a general
   noncurrent-deferred-tax balance, and may differ from the firm's
   actual TRA liability. Open the firm's most recent 10-K balance
   sheet, find the TRA line item, and confirm the figure before
   citing the XBRL row in any summary or open question. If the
   figures disagree, the XBRL series is a generic deferred-tax
   figure and only the 10-K line item is authoritative for TRA work.

2. For each TRA-mentioning filing in the timeline (top to bottom by
   filing date):
   - Load the cached excerpts file
     (`<filename>.tra_excerpts.txt`). Skip blocks with
     `in_table=True`; they are non-GAAP boilerplate.
   - Load the cached TOC index (`<filename>.toc.tsv`). Use the
     heading column to locate TRA-relevant sections: "Tax Receivable
     Agreement" (subsection of tax notes), "Related Party
     Transactions", "Risk Factors", "Liquidity and Capital Resources",
     "Contractual Obligations", "Item 1.01" / "Item 1.02" for 8-Ks.
   - If the TOC is empty, fall back to in-document text search for
     "tax receivable agreement" inside the cached HTML body.
   - Record in the per-filing-notes entry:
     - Section names where TRA appears (verbatim section headings).
     - A short summary of what the filing says about the TRA.
     - Extraction hints for future agents: anchor names, TOC entries,
       search terms, navigation steps.

3. Fill in the TRA event timeline at the top of the packet. One row
   per material event affecting the TRA. Event types: Registration
   (pre-IPO), Execution (IPO), Amendment, Transfer (M&A),
   Termination, Bankruptcy, Up-C collapse, and other. The "brief
   summary" column expects concrete content: what an amendment
   amended; whether a restructure related to anything besides the
   Up-C; what a termination payment was for.

4. Write the headline summary at the top: one to three sentences
   stating what the evidence indicates, the strongest source, and
   the residual uncertainty.

5. Write the open questions at the bottom. Open questions are
   reserved for items needing human judgment. If the skill or agent
   can verify something via Company Concept data or by reading a
   specific filing, the agent does so rather than punting to a
   question. Specifically:
   - "Verify payment landed" type questions: check the Company
     Concept time series; do not punt.
   - Vague residual counterparty pool questions: if the agent cannot
     phrase the question concretely, drop it.
   - "This unflagged 8-K may have touched the TRA" type questions:
     fetch and check the 8-K; do not punt.

### Why TOC navigation, not full-text reading

Filings are large (10-Ks often exceed 100 pages, 1.5+ MB of HTML).
Reading every word would consume the agent's context window before
even reaching the TRA section. The TOC index is the navigational
table that lets the agent jump to the few sections that matter; the
cached excerpts file gives the agent the local window around each TRA
mention without re-stripping HTML. The agent's job is targeted
reading.

## Banned writing patterns inside the packet

The project's standing rules apply to all packet content:

- No em-dashes outside sentences that already contain a comma or
  semicolon.
- No banned terms: p-r-o-s-e, d-e-l-v-e, l-e-v-e-r-a-g-e as a verb,
  c-o-m-p-r-e-h-e-n-s-i-v-e, r-o-b-u-s-t outside statistical
  contexts, s-u-r-f-a-c-e as a verb, "smoke test".
- Avoid the "X, not Y" sentence pattern; state the positive claim
  directly.
- The headline summary uses one to three short sentences. The packet
  has no closing-summary paragraph; the open questions close it.

## Cost estimate

Per firm: roughly 1 Submissions JSON + 1 S-1 + 5 to 30 periodic
filings + 5 to 150 8-Ks + 0 to 20 DEF 14As + 1 Company Concept call
+ 1 SGML envelope per filing + however many EX-10.* documents pass
the contract-shape filter (typically 1 to 5 unique TRA exhibits
across the firm's lifetime). At 9 requests per second, the cold-cache
network time per firm is a few minutes; reruns hit the cache.

For a 23-firm sweep downstream, expect on the order of 3,000 to
8,000 cold-cache fetches in aggregate, comfortably under SEC's 10/sec
hard cap.

## Cross-links

- `~/.claude/skills/sec-edgar/SKILL.md`: filing fetch primitives this
  skill builds on, including the Company Concept API at
  `scripts/sec_edgar/concept.py`.
- `coauthor/2026-05-12-edgar-scrape/findings/deferred_review_methodology.md`:
  the planning document this skill operationalizes.

## What the skill does not do

- Cross-firm summarization (the aggregator step downstream).
- Verdict capture in `tra_deferred_review.csv` (the user populates
  the verdict columns after reading the packet).
- Optical character recognition on image-only PDFs.
- Section excerpting in the packet markdown itself. The mechanical
  packet ships with the structured tables and placeholder per-filing
  notes; the agent navigates via the cached helper files and
  authors the notes.
