---
name: tra-build-timeline
description: >-
  Given a firm directory produced by tra-process-filings, write a concise
  TRA summary file with YAML frontmatter (status, dates, tax-asset type,
  sharing ratio, companies, CIKs, plus optional role and trigger-event
  tags), a short event-grouped timeline, and a one-paragraph explanation
  of what happened with the TRA. The summary is the human-readable
  starting point for a later structured time-series build.
---

# TRA summary builder

## Purpose

For each firm whose filings have been processed by `tra-process-filings`,
write a short, focused TRA summary file. The summary answers: when did
the TRA begin, what happened over its life, and what is its current
state? It is concise enough to read without deep knowledge of the
events; readers who want more detail follow the references to
`contract_log.md` and `filing_notes.md`.

The summary is the human-readable starting point for the planned
structured time-series of TRAs.

## Universal constraints

- All SEC interaction goes through `scripts/sec_edgar/` (invoked as
  `PYTHONPATH=scripts pixi run python ...` from `<project root>`).
- The SEC 10 req/sec rate cap applies to any supplemental fetches.
- Never write output filenames starting with `report`, `summary`,
  `findings`, or `analysis`.
- Do not use the acronym "EFTS"; write "EDGAR full-text search" or
  "full-text search".

## Inputs

| Parameter | Type | Notes |
|-----------|------|-------|
| `firm_dir` | path | One per-firm directory containing `TRA-<date>/`, `contract_log.md`, `filing_notes.md`. |

## Outputs

One Quarto-markdown file per TRA, written into the firm directory:

- Single-TRA firms: `<slug>_summary.qmd`.
- Multi-TRA firms (parallel TRAs in distinct `TRA-<date>[-<diff>]/`
  subdirectories): one file per TRA, named
  `<slug>_TRA-<date>[-<diff>]_summary.qmd`.

The `.qmd` extension is intentional: these files can be rendered with
Quarto later if a polished output is needed. The frontmatter doubles as
the human-readable header and as a machine-readable index for the
downstream time-series build.

## File format

Each summary file has three parts.

### Part 1: YAML frontmatter

Required fields (every summary must include all of these; use an empty list / empty string when the field does not apply):

| Field | Type | Notes |
|---|---|---|
| `title` | quoted string | `"<Firm Name> TRA"` for the modal case. For multi-TRA firms: `"<Firm Name> TRA (<TRA-id>)"`. **For beneficiary-side files** (where `role` is not `PubCo`), append a clarifying parenthetical so the title distinguishes the beneficiary file from the obligor's: `"AMC Entertainment Holdings TRA (NCM beneficiary)"`. **Always quote** the title string because firm names often contain `&`, `:`, or other YAML-active characters (e.g., `"PG&E Corporation TRA"`). |
| `author` | string | `"tra-build-timeline skill"` when authored by the skill, or a human name when authored manually. |
| `date` | YYYY-MM-DD | Date the summary was written. |
| `company-names` | list of quoted strings | All public-company names involved across the TRA's life (original obligor, beneficiaries, acquirers, etc.). Quote each entry: `["Parsley Energy, Inc.", "Pioneer Natural Resources Company"]`. |
| `CIKs` | list of quoted strings | Zero-padded 10-digit CIKs corresponding to `company-names`, same order. **Always quote** so YAML does not parse them as integers and strip the leading zeros: `["0001594466", "0001038357"]`. |
| `status` | enum | One of `Ongoing`, `Terminated`, `Unknown`. |
| `creation-date` | YYYY-MM-DD | TRA execution date. |
| `termination-date` | YYYY-MM-DD or blank | Date the TRA effectively ended. Blank when status is `Ongoing` or `Unknown`. |
| `tax-asset-type` | list | **Always a list**, even with one entry: `[Basis Step-Up]`, `[NOL]`, or `[NOL, Basis Step-Up]`. Values: `Basis Step-Up`, `NOL`, `Other tax credit`. Basis Step-Up does NOT distinguish between Section 754 partnership exchanges, 338(h)(10) elections, 336(e) elections, Section 1012 cost-basis acquisitions, or Section 197 amortization of acquired intangibles; we care about basis vs non-basis only. When a TRA covers multiple constituent attributes, tag every constituent. Capital losses are tagged as `NOL` (group with loss carryforwards for this purpose). Section 197 amortization is tagged as `Basis Step-Up`. |
| `sharing-ratio` | string | The payment percentage. **Always a simple percent string** (`85%`, `50%`, `90%`, `100%`). When multiple rates apply to different tax-attribute categories, use a short string like `85% basis / 50% NOL`. Aggregate caps (e.g., PG&E's $1.35B cap), per-tranche structures, or other non-percent qualifications go in the `notes` field, NOT in `sharing-ratio`. |
| `parallel-tras` | list of quoted strings | TRA IDs of any parallel TRAs at the same firm. **Always present**; use an empty list `[]` when this is the only TRA. |

Recommended additional fields (use when applicable):

| Field | Type | Notes |
|---|---|---|
| `role` | enum | The current firm's role with respect to the TRA: `PubCo`, `Beneficiary`, `Acquirer`, `Financing-arm`. Matches the role taxonomy in `tra_summary.csv`. |
| `trigger-event-type` | enum | What created the underlying tax asset: `IPO`, `Asset purchase`, `Merger`, `SPAC business combination`, `Plan of reorganization`, `Spin-off`, `Up-C transition`, `Section 162 issuance`, `JV formation`, `Other`. `Asset purchase` covers all asset-purchase-style triggers regardless of the specific IRC mechanism (Section 1012 cost basis, Section 338(h)(10) election, Section 336(e) election, Section 1001 asset purchase, Section 197 amortization of acquired intangibles); the relevant economic distinction is between LLC-unit-exchange-driven TRAs (where future exchanges generate new tax assets, tagged via `IPO` for Up-C IPOs) and asset-purchase-driven TRAs (one-shot step-up that amortizes down). |

Optional fields (include when meaningful, omit otherwise):

| Field | Type | Notes |
|---|---|---|
| `counterparty-type` | enum | `pre-IPO holders`, `M&A sellers`, `founder vehicle`, `named individual`, `transfer-agent book-entry`, `plan-of-reorganization trustee`, `Other`. |
| `notes` | string | Annotation for anything that does not fit the other fields (aggregate caps, per-tranche structures, valuation-allowance quirks, off-EDGAR docket pointers, predecessor-name notes for shared CIKs, et cetera). **Maximum 3 lines.** Longer narrative belongs in the Explanation paragraph. Quote the value with `>-` when multi-line. |

### Part 2: `## TRA Timeline`

Event-grouped bullet list. Each `####` heading groups events under a
single phase of the TRA's life. Under each grouping, bullet points carry
`- YYYY-MM-DD: <one-line description>` entries.

Group-heading naming is free-form short-event-named ("Bankruptcy
cancellation", "Hershey acquisition", "Up-C IPO and TRA execution",
etc.). Most TRAs need two or three groupings; complex TRAs with parallel
amendments or multi-step terminations may need more.

Bullet count per group: **trim filings that do not change the contract
state**. Annual 10-Ks and 10-Qs whose only TRA-relevant content is a
balance-sheet entry should not appear unless they mark a material event
(first valuation-allowance write-down, first amendment, last filing
before deregistration, et cetera). Most groupings carry 2-5 bullets;
exceed this only when many distinct events actually happen.

Inferred dates take a `?` suffix and an inline qualification within the
description (e.g., `2014-04-23?: Origination date inferred from
preamble; trigger event date used`).

### Part 3: `## Explanation`

One concise paragraph explaining what happened with the TRA. Writing
constraints:

- Highly focused: name the trigger event, the contract's economic
  terms, any material amendments, and how it ended (or its current
  state).
- Easy to follow: a reader who has not seen the contract logs should
  understand the paragraph on first reading.
- Not requiring deep TRA knowledge: avoid jargon-stacking. Terms of art
  (`Up-C`, `Section 754`, `formula-locked ETP`) are fine when they
  appear naturally, but lead with what happened, not with the term of
  art.
- Reference, do not repeat: when more detail would be useful, end the
  paragraph with a sentence pointing the reader at the relevant
  detailed file (e.g., "See `contract_log.md` for the full amendment
  history and the executed termination instrument.").

The paragraph is roughly 3-5 sentences in most cases. Longer paragraphs
are a signal that the contract has unusual features (parallel TRAs,
cross-jurisdictional treatment, multi-step terminations); the long
version goes in `contract_log.md`, and the explanation paragraph here
should still stay concise by pointing to that file.

## What this skill does NOT cover

The summary tracks material TRA events and end-of-life state only. Do
NOT list or restate the following.

In the timeline:

- **Annual or quarterly liability balances.** Filings whose only
  TRA-relevant content is an updated carrying value should not appear
  as bullets. The trajectory belongs in the Explanation paragraph or in
  `notes`. Include a balance disclosure as a bullet only when it marks
  a material event (first valuation-allowance write-down, first cash
  payment, last filing before deregistration).
- **Successive S-1 amendments without substantive change.** When an
  S-1/A is a pagination-only or boilerplate update, omit it. Pick the
  filing that first introduced the operative provision or the 8-K that
  attaches the executed contract.
- **Routine 10-Q TRA-mention filings.** Quarterly filings that repeat
  the standard TRA footnote without a new event do not belong in the
  timeline.
- **Credit-agreement or debt-covenant TRA mentions.** Skip unless the
  amendment actually restricts TRA payments.
- **Press releases.** Cite the corresponding 8-K instead.
- **Natural beneficiary-pool changes.** Unit-by-unit exchanges that do
  not require a contract amendment are not events; only material
  beneficiary changes (waiver, mass transfer, dissolution of a holder
  entity) belong on the timeline.
- **Unrelated corporate events.** Debt refinancings, board changes,
  dividend declarations, and similar do not interact with the TRA and
  should be omitted.

In the Explanation paragraph:

- Do not re-narrate the contract log filing by filing.
- Do not spell out IRC chapter mechanics; the contract log carries
  those, and the Explanation paragraph leads with what happened.
- Do not restate frontmatter fields (sharing ratio, dates, et cetera)
  beyond what naturally fits one or two sentences.
- Do not detail every payment; the trajectory can be one sentence with
  the cumulative figure and a pointer to the contract log.

When the timeline is bullet-heavy or the explanation balloons past 5
sentences, the file is probably duplicating the contract log; trim and
reference.

## Template

A fillable scaffold is at
`~/.claude/skills/tra-build-timeline/references/empty_template.qmd`.
Copy it into the firm directory under the appropriate filename
(`<slug>_summary.qmd` or `<slug>_TRA-<date>_summary.qmd` for multi-TRA
firms) and fill in the placeholders.

## Workflow

1. **Read inputs.** Read `contract_log.md`, `filing_notes.md`, and the
   contract files under each `TRA-<date>/` subdirectory. Read any
   `validation_*.md` notes if present.

2. **Identify TRAs.** Each `TRA-<date>[-<diff>]/` subdirectory is one
   TRA. Single-firm-single-TRA is the common case; multi-TRA firms
   produce one summary file each.

3. **Extract frontmatter values.** For each TRA, populate the required
   fields plus any applicable recommended fields. When the contract log
   leaves a field ambiguous, fill it as best you can and add a `notes`
   field flagging the ambiguity.

4. **Build the timeline.** Identify the natural groupings of events
   (origination phase, amendment phase, termination phase). Place each
   dated event under its grouping. Keep each bullet to one line. When a
   bullet refers to a filing, name the filing type (8-K, 10-K, S-1,
   etc.) but do not include the accession number in the bullet; the
   accession lives in `contract_log.md`.

5. **Write the explanation paragraph.** One paragraph, 3-6 sentences in
   typical cases. Lead with what happened (the trigger event, the
   payment terms, any material changes, the end-of-life state). Avoid
   jargon-stacking. End with a one-sentence pointer to
   `contract_log.md` for readers who want more detail.

6. **Handle the acquirer cross-check (acquired firms only).** When the
   firm was acquired during the TRA's life, run the four-step acquirer
   check before fixing the `status` field:

   a. Read the target's DEF14A merger proxy for "Tax Receivable
      Agreement" plus the acquirer's name.
   b. Read the merger-agreement exhibits (S-4 or 8-K Item 1.01) for an
      explicit TRA-treatment clause.
   c. Read the target's last pre-close 10-K or 10-Q subsequent-events
      note.
   d. Read the acquirer's post-close 10-K or 10-Q for the assumed
      liability disclosure.

   When the acquirer is itself in our test-run directory, add an
   inline pointer to its summary file in the explanation paragraph
   (e.g., "TRA persists under Hershey; see
   `../hershey-foods-co_0000047111/hershey-foods-co_summary.qmd`").

   When the acquirer is not in our test-run directory but is on EDGAR,
   note the acquirer's CIK so a future pass can fetch its filings.

7. **Choose the status.** Use `Ongoing` when the TRA is in force.
   Use `Terminated` when the TRA has ended via any of the three
   mechanisms (including economic extinguishment via restructuring that
   leaves zero balance and no future possibility). Use `Unknown` when
   the firm has exited the EDGAR universe (private acquirer, off-EDGAR
   bankruptcy docket) and the TRA's fate cannot be determined from
   available filings. State what happened to the firm in the
   explanation paragraph in `Unknown` cases.

## Worked example

The reference example is at
`TRA-contracts/pioneer-pe-holding-llc_0001594466/pioneer-timeline.qmd`.
Note that the example pre-dates this skill's frontmatter design and
carries a reduced field set (`title`, `author`, `date`, `company-names`,
`CIKs`, `status`); it is correct in structure but the skill should
produce the fuller frontmatter listed above.

## Deferred to next project

- **Structured time-series schema.** Machine-readable event extraction
  from the summary files into a long-format dataset of (TRA-id, date,
  event-type, event-payload) rows. This is the deliverable of the
  follow-on coauthor project, which uses the YAML frontmatter and the
  timeline bullets as input.
- **8-K stream monitoring integration.** Ongoing detection of new
  TRA-relevant filings for `Ongoing` TRAs.
