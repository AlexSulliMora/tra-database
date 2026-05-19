---
name: tra-process-filings
description: >-
  For each downloaded filing in a firm's directory (output of
  tra-download-filings), identify TRA contracts, classify them as
  original/amendment/termination, determine which contracts are the same
  vs. distinct, and write per-filing annotations plus a contract log.
---

# TRA filing processor

## Purpose

Given a per-firm directory of downloaded filings, read and classify every document for TRA contract content. The agent identifies unique contracts, tracks versions and amendments, detects terminations, and annotates each filing. Classification is agent-driven: hash- or regex-based identification is explicitly insufficient. The agent reads the contract text and reasons from it.

## Universal constraints

-   All SEC interaction goes through `scripts/sec_edgar/` (invoked as `PYTHONPATH=scripts pixi run python ...` from `<project root>`).
-   The SEC 10 req/sec rate cap applies to any supplemental fetches (trigger-event filings, amendment history).
-   Never write output filenames starting with `report`, `summary`, `findings`, or `analysis`.
-   Do not use the acronym "EFTS"; write "EDGAR full-text search" or "full-text search".
-   Do not use the words "bilateral" or "multilateral" to describe TRAs. Every TRA is structurally a two-party contract: PubCo (obligor) and the collective LLC shareholders (beneficiaries). When the LLC-shareholder side is broken into sub-groups within one contract document, describe the sub-groups by name (e.g., "with Fifth Third, Advent, and JPDN named as the LLC-shareholder sub-groups") rather than labeling the contract "multilateral". The multi-named-beneficiary-group structure is normal, not a structural quirk.
-   Do not use the phrase "cap-and-release" to describe a TRA termination. "Cap" misleadingly implies that further payments may still occur subject to a ceiling, when in fact a single payment terminates the contract. Use "termination payment" (basic case), "CoC payment" (Change of Control-triggered), "settlement payment" (negotiated outside the contract's ETP formula), or "negotiated termination payment" (negotiated for materially less than the contract's ETP). The status flag was renamed from `cap_and_release` to `negotiated_termination_payment`.

## Inputs

| Parameter | Type | Notes |
|-------------|------------------|----------------------------------------|
| `firm_dir` | path | Per-firm directory from `tra-download-filings`, i.e., `<output_dir>/<CIK>/`. |

## Outputs

```         
<firm_dir>/
├── TRA-<origination-date>[-<differentiator>]/
│   ├── <YYYY-MM-DD>-original-{executed|unexecuted}.<ext>
│   ├── <YYYY-MM-DD>-AR-<N>-{executed|unexecuted}.<ext>
│   ├── <YYYY-MM-DD>-amendment-<N>-{executed|unexecuted}.<ext>
│   └── <YYYY-MM-DD>-termination.<ext>
├── contract_log.md
└── filing_notes.md
```

### Contract filename convention

Every contract file inside a `TRA-<origination-date>/` directory uses one of four classification slugs, joined to a leading date and (when applicable) a trailing execution-state suffix:

- `<YYYY-MM-DD>-original-{executed|unexecuted}.<ext>` — the first/originating Tax Receivable Agreement for the contract. Exactly one per directory.
- `<YYYY-MM-DD>-AR-<N>-{executed|unexecuted}.<ext>` — the Nth Amended and Restated version (`AR-1`, `AR-2`, …). Counts only restatements, not numbered amendments.
- `<YYYY-MM-DD>-amendment-<N>-{executed|unexecuted}.<ext>` — the Nth numbered amendment (`amendment-1`, `amendment-2`, …). Counts only numbered amendments, not restatements.
- `<YYYY-MM-DD>-termination.<ext>` — the operative termination instrument for the contract. No execution-state suffix; terminations are saved only once they are operative.

Rules to disambiguate:

1. **The `termination` label is by operative effect, not by document title or structural type.** If an instrument's operative effect is to terminate the contract, save it as `<date>-termination.<ext>` regardless of whether the document is titled "Termination Agreement", "Payment and Termination Agreement", "Amendment No. N", or "Second Amended and Restated Tax Receivable Agreement". An amendment whose operative provision terminates the agreement is saved as a `termination`, not as an `amendment-<N>` or `AR-<N>`. Use `terminates: true` in the `contract_log.md` entry to record that the document's structural form was an amendment or restatement that happened to terminate, but the saved filename uses the `termination` slug.
2. **The `<YYYY-MM-DD>` date is the SEC filing date (the date the document became publicly available on EDGAR), NOT the effective date inside the document body and NOT the period-end of the parent filing.** The filing date is the date stamped on the EDGAR submission that disclosed the contract. When the contract was first attached to an S-1 or DRS draft and later re-attached to a 424B3 prospectus, each saved copy carries the filing date of its own enclosing submission. The internal "dated as of [date]" line inside the contract is recorded in `contract_log.md` if relevant but is not used in the filename.
3. **`executed` vs `unexecuted` is signature-based.** A signed final version (signatures on the signature pages, date filled in the preamble, no `[●]`/`[•]` placeholders for parties or dates) is `executed`. A form-of, draft, or template version (placeholders present, no signatures) is `unexecuted`. The termination filename omits this suffix because terminations are saved only in their operative form.
4. **`<ext>` is the source file extension** (`htm` or `html`); the companion markdown produced by `tra-htm-to-md` carries the same stem with `.md`.

After cleanup completes (Step 7), the firm directory contains ONLY `contract_log.md`, `filing_notes.md`, and the `TRA-*/` subdirectories; all raw `<accession>/` directories are deleted.

### contract_log.md

One entry per contract identification decision. Each entry records:

-   Which document triggered the decision.
-   The classification: original / Amended and Restated / Amendment No. X / Termination.
-   Whether this is a new contract or an additional version of one already saved.
-   The agent's reasoning in one to five sentences.
-   Any flags: `origin_date_unverified`, `manual_verification_needed`, `terminates: true`.

### filing_notes.md

One entry per filing in `firm_dir`. Most filings that contain no new TRA information get a short boilerplate line, e.g.:

> `2023-05-12 | 10-Q | 0001594686-23-000041 | Standard 10-Q disclosures, no new TRA information.`

Reserve longer annotations for filings with actual new content or company news which may affect the TRA: corporate restructurings, Up-C collapse, TRA amendments or terminations, M&A or other change of control events, change to LLC agreement or certificate of incorporation (only if it affects the TRA).

**Omission permitted for non-substantive firms.** When every TRA mention in the firm's filings is non-substantive (e.g., boilerplate negative-covenant carve-outs in M&A SPAs, generic "Indebtedness" definition enumerations, contingent fallback clauses that never triggered), the agent may omit `filing_notes.md` entirely. In that case, `contract_log.md` must explicitly state in its role-determination entry: "No substantive TRA content found across the firm's filings; `filing_notes.md` omitted per spec." Producing hundreds of boilerplate "no new TRA information" entries for a firm that never had a real TRA is wasted output. Firms with any substantive TRA content (payment amounts disclosed, TRA-related accounting entries, settlement events, beneficiary-side payment receipts, etc.) must still have a `filing_notes.md` per the standard rule.

## Workflow

Before the per-document steps, identify the role the firm of interest plays relative to the TRA. The role determines whether to expect any saved contract files at all and which CIKs to cross-reference:

- **PubCo (TRA obligor).** The firm went public via Up-C IPO, SPAC business combination, or similar and committed to pay TRA beneficiaries. The original TRA, amendments, and any termination instrument should be filed under the firm's own CIK. This is the default case the rest of the workflow assumes.
- **Beneficiary.** The firm is a recipient of TRA payments rather than the obligor (e.g., McKesson received payments from Change Healthcare under the McK TRA). The actual contract documents live under the obligor's CIK, not the firm's. Expect zero TRA directories under the firm's CIK; the firm's filings disclose carrying value of a receivable and payment receipts. Note this in `contract_log.md` with a cross-reference to the obligor's CIK if known.
- **Acquirer.** The firm acquired another company and extinguished the target's TRA at the acquisition close (e.g., Comcast settled DreamWorks's TRA at acquisition). The actual contract documents live under the target's CIK; the firm's filings disclose the settlement as an acquisition-accounting line item in the next post-close periodic filing. Expect zero TRA directories under the firm's CIK.
- **Financing arm.** The firm is a downstream financing subsidiary of an Up-C parent and is not a contractual party to the TRA but funds payments via upstream distributions (e.g., VWR Funding for VWR Corp). Expect zero TRA directories under the firm's CIK; cross-reference the parent's CIK in `contract_log.md`.
- **Never executed.** The firm contemplated a TRA in a draft or form-of exhibit but the deal was amended before close to remove the TRA, so no executed contract exists (e.g., Swiftmerge / AleAnna). Save the draft only and use status flag `never_executed`.

### Step 1: strip HTML and read

For each document under `firm_dir`:

-   Strip HTML to readable plain text. The standard library `html.parser` is sufficient; no rendering needed.
-   Read the file via the Read tool or via a helper.

### Step 2: classify each document

#### What a Tax Receivable Agreement looks like

A Tax Receivable Agreement is a contract by which a public company (commonly called PubCo) commits to pay a defined percentage of certain realized tax savings to a defined set of beneficiaries (typically pre-IPO holders or sponsor entities, most commonly 85% of the savings). Most TRAs arise from Up-C IPOs, but variants exist for M&A acquisitions, reverse mergers, partnership restructurings, and SPAC-driven transactions. Look for these markers in the document:

**Title.** A TRA-related instrument's title falls into one of these patterns:

- *Origination:* "Tax Receivable Agreement", "Income Tax Receivable Agreement".
- *Restatement:* "Amended and Restated Tax Receivable Agreement", "Second Amended and Restated Tax Receivable Agreement", and so on.
- *Numbered amendment:* "Amendment No. X to the [Amended and Restated] Tax Receivable Agreement", "First Amendment to the Tax Receivable Agreement".
- *Termination-by-distinct-title:* the operative effect is to terminate the TRA, but the document is titled as something other than "Amendment" or "Termination of TRA". Common variants: "Payment and Termination Agreement", "TRA Repurchase Agreement", "Tax Receivable Prepayment Agreement", "Waiver and Termination of Tax Receivable Agreement", "Termination and Release Agreement". Classify these under Step 3 Termination mechanism 2 (amendment whose operative provision terminates), regardless of the title.
- *Beneficiary modification:* "TRA Waiver and Assignment Agreement", "Waiver of Tax Receivable Agreement (Individual)", used when one beneficiary releases their share back to PubCo or assigns rights to another party. Not a termination; the underlying TRA continues with a modified beneficiary roster.
- *Waiver of a specific provision:* unilateral instruments executed under a waiver clause, modifying behavior under a named section without amending the contract text directly (e.g., Apollo's May 2022 waiver of early-termination right). Treat as an amendment-class document with a `waives: <provision>` flag in the contract log.

The title is a strong hint but content determines classification. Always read the operative provisions: "Payment and Termination Agreement" is functionally a terminating amendment; "TRA Waiver and Assignment" modifies the beneficiary roster without terminating.

**Preamble.** Opens with "This Tax Receivable Agreement, dated as of [date], is entered into by and between [PubCo] and [the Pre-IPO Holders / Continuing LLC Members / Sponsor Party / specifically named beneficiaries]". An Amended and Restated version's preamble says it "amends and restates [the prior Tax Receivable Agreement] dated as of [date]". An amendment references the prior agreement and specifies which provisions are being changed.

**Structure.** A typical TRA has these sections in roughly this order: Definitions; Determinations and Schedules (Realized Tax Benefit, Hypothetical Tax Liability, Actual Tax Liability, Tax Benefit Schedule); Payments (timing, calculation, early termination payment); Tax Returns and Reconciliations; Term and Termination; General Provisions (governing law, arbitration, assignment, amendment procedure).

**Defining terminology.** "Realized Tax Benefit", "Hypothetical Tax Liability", "Actual Tax Liability", "Exchange Basis Schedule", "Tax Benefit Schedule", "Net Tax Benefit Payment", "Early Termination Payment", "Section 754 Election", "Continuing LLC Members" / "Pre-IPO Holders" / "Sponsor Party" / "TRA Beneficiaries", "Pre-IPO Tax Assets".

**Payment percentage.** Most often 85%; 75%, 90%, and tiered rates also appear.

**Tax attributes covered.** Most commonly basis step-ups from exchanges under Section 754, pre-IPO net operating loss carryforwards (NOLs), foreign tax credits, or imputed interest deductions.

#### What is NOT a TRA

These agreements are commonly filed alongside a TRA and share parties or terminology. Do not save them as TRA contracts:

- **Tax Sharing Agreement.** Intercompany allocation of tax liability among members of a consolidated group. Not a payment from PubCo to outside beneficiaries.
- **Exchange Agreement.** Governs the mechanism for exchanging LLC Units for PubCo Class A common stock. Often co-filed with a TRA but is a separate contract with no payment obligation tied to tax savings.
- **LLC Operating Agreement / Limited Liability Company Agreement.** Governs the operating partnership's internal affairs.
- **Stockholders Agreement / Voting Agreement / Registration Rights Agreement.** Govern voting, board representation, transfer restrictions, or registration rights. No tax-payment obligation.
- **TRA Bonus Plan / Tax Receivable Agreement Bonus Plan.** A compensation arrangement that pays employees a share of TRA-related tax savings as bonus compensation (e.g., Acreage Holdings's Bonus Plans I and II). Tied to but separate from the classical TRA; the Bonus Plan is a benefit-plan document, not a contractual TRA. Note the Bonus Plan in `contract_log.md` as a parallel non-TRA instrument with a `parallel_bonus_plan: true` flag; do not save it as a TRA contract file.

When in doubt: a TRA has a payment obligation from PubCo to specifically named beneficiaries, calculated as a percentage of tax savings PubCo realizes from defined tax attributes. If those three elements are present, it is a TRA; if any is absent, it is not.

#### Classification questions

For each document classified as a TRA, answer:

1. **Original, restated, amendment, or termination?**
   - "Tax Receivable Agreement" (no qualifier): original.
   - "Amended and Restated Tax Receivable Agreement": wholesale rewrite; a complete contract, not a marked-up delta.
   - "Amendment No. X to the [...] Tax Receivable Agreement" or "First/Second/... Amendment to...": delta against the prior version; modifies specific provisions.
   - "Termination of Tax Receivable Agreement", "Notice of Termination", or similar: standalone termination document.
   - Amendment whose operative provision terminates the agreement: treat as amendment with the `terminates: true` flag.

2. **Unexecuted draft or executed signed version?**
   - Unexecuted: no signatures, blank preamble date, blank schedules. Typical of TRAs filed with S-1 / S-1/A or in registration exhibits.
   - Executed: signatures present, preamble date filled in. Typical of TRAs filed with 8-K after IPO or Up-C close, or as 10-K exhibits.

3. **Same underlying contract as one already saved, or distinct?** Apply Step 3.

Record the classification and reasoning in `contract_log.md` regardless of outcome.

### Step 3: same contract vs distinct contract

Before saving a new document, read the existing files in the relevant `TRA-*/` subdirectory and decide whether the new document is:

- The same contract in a different state (e.g., executed vs unexecuted, or a re-filing with no substantive change).
- A new version of the same contract (an amendment or an Amended and Restated rewrite).
- A separate parallel contract (a different TRA entirely).

#### Criteria for "same contract"

Two documents represent the same underlying contract when ALL of the following match:

- **Parties.** Same PubCo, same defined beneficiary group (e.g., the same "Continuing LLC Members" or the same set of Pre-IPO Stockholders listed in the same annex).
- **Effective date.** Same preamble date, OR one is blank (unexecuted) and the other carries the date the parties later signed.
- **Operative payment terms.** Same payment percentage, same definition of "Realized Tax Benefit", same payment cadence.
- **Tax attributes covered.** Same set of tax assets giving rise to payments (e.g., both cover Section 754 basis step-ups and pre-IPO NOLs; or both cover only NOLs).
- **Term and termination triggers.** Same termination provisions and same early termination payment formula.

An unexecuted draft (no date, no signatures) and the corresponding executed version (with date and signatures) of the same agreement satisfy these criteria, since their terms are identical and the differences are execution-related metadata. Save both files and note the unexecuted/executed pair in `contract_log.md`.

**Beneficiary trusts or affiliated transferees added at execution.** If the unexecuted form-of names only individual Principals (e.g., Tannenbaum and Berman) but the executed version adds family trusts, holding companies, or affiliated transferee vehicles as additional named beneficiaries (e.g., FSC CT II, Inc. plus two family trusts), treat as execution-state difference, not a separate contract. The Principals are the parties of record; trusts and affiliates are transferee vehicles holding the same economic interest. Note the additions in `contract_log.md`.

**Wholesale beneficiary reassignment via amendment.** When an amendment changes the beneficiary set wholesale, for example by assigning all TRA Member rights to a single new entity (e.g., Acreage's Third Amendment assigning TRA rights to Canopy USA), the underlying contract persists. Treat as an amendment to the same contract, not a new contract, when the amendment text uses "amend" or "assign" language and the original instrument's structure is retained. The Step 3 "Parties" criterion for distinct contracts applies to comparing two independent agreement documents, not to a single contract whose beneficiary roster changes via amendment.

#### Criteria for "different contract"

Two documents are distinct contracts when ANY of the following differ:

- **Parties.** The beneficiary set is meaningfully different (e.g., one TRA is with the original Continuing LLC Members; another is with a Sponsor Party or an acquired counterparty from a later transaction).
- **Tax attributes covered.** One TRA covers basis step-ups; another covers NOL carryforwards or foreign tax credits. These are typically parallel agreements at the same firm.
- **Payment percentage.** 85% vs 75%, or per-attribute tiered rates that differ.
- **Effective date with substantive differences.** A TRA established at IPO is distinct from a TRA established at a later M&A event, even at the same PubCo.

When parallel TRAs exist, identify each by origination date; see the "Multiple parallel TRAs" subsection below for the directory naming rule.

#### Criteria for "new version of the same contract"

An amendment or restatement keeps the same underlying contract but modifies its terms. When reading the new document:

- Note the explicit reference to the prior agreement: an amendment references "that certain Tax Receivable Agreement dated as of [date]" or "the Tax Receivable Agreement, as amended"; an Amended and Restated version says "amends and restates the Tax Receivable Agreement dated as of [date], as previously amended".
- Identify what changed. Common amendment types:
  - **Adding or removing beneficiaries** (e.g., after an M&A transaction or a beneficiary departure).
  - **Modifying payment timing** (extending or compressing deferral periods).
  - **Modifying termination provisions** (early-termination triggers, change-of-control calculations).
  - **Modifying the payment percentage.**
  - **Administrative changes** (clarifications or corrections with no economic substance).
  - **Termination amendments** (amendments whose operative effect is to terminate the agreement).

Save the new version alongside the prior one and write a one-paragraph summary of what changed to `contract_log.md`.

#### Best-effort term comparison

When deciding same / distinct / new-version, focus on these provisions, in priority order:

1. **Payment percentage** (Payments / Determinations section).
2. **Tax attributes covered** (Definitions: "Tax Attributes", "Pre-IPO Tax Assets", "Eligible Tax Benefits").
3. **Beneficiary identification** (parties listed in the preamble or a beneficiary annex).
4. **Termination provisions** (early termination calculations, change-of-control triggers).
5. **Governing law and dispute resolution** (rarely changes, but worth a quick check).

The comparison is approximate; small differences in legal phrasing without economic substance do not count as substantive. Record the comparison method in `contract_log.md` (whether key sections were skimmed or fully read, and what differences were found).

When an Amended and Restated version coexists with the original plus cumulative numbered amendments, write the following to `contract_log.md` and to the relevant `filing_notes.md` entry:

> "Manual verification needed: an Amended and Restated agreement and the original plus amendments Nos. 1 through N are both on file; these should produce equivalent terms if the restatement was administrative, but confirm."

#### Multiple parallel TRAs

When a firm has two or more distinct TRAs (e.g., one covering NOL carryforwards, one covering stepped-up basis, or one inherited from an acquisition), identify each by origination date. If two contracts share an origination date, add a differentiator slug: `TRA-<YYYY-MM-DD>-<diff>`. The differentiator is whichever attribute differs most prominently: tax attribute type (`NOL`, `Basis`), counterparty name, payout rate (`rate-85pct`), or another short, stable label.

#### Terminations

A TRA can terminate by various instruments and causes. The classifier records whether termination occurred and the cause; the precise legal-instrument distinction (standalone termination agreement vs amendment-that-terminates vs operation of an existing change-of-control clause) is not separately tracked.

When any instrument whose operative effect is to terminate the contract is filed, save it in the parent contract's directory as `<YYYY-MM-DD>-termination.<ext>` per the filename convention above. This applies whether the document is titled "Termination Agreement", "Payment and Termination Agreement", "Amendment No. N to the Tax Receivable Agreement", or even "Second Amended and Restated Tax Receivable Agreement" — operative effect determines the filename slug, not the document title or structural type. When the document is structurally an amendment or restatement that happens to terminate, also tag it with `terminates: true` in `contract_log.md` so the structural form is preserved in the log even though the saved filename uses the `termination` slug. The `<YYYY-MM-DD>` is the SEC filing date of the disclosing submission, not the effective date inside the document body. When the termination comes from a bankruptcy plan, merger agreement, or another non-TRA-specific instrument, do not save any TRA-specific termination file; record the citation to the controlling document in `contract_log.md`.

When a termination instrument is executed concurrent with a merger agreement and substitutes a negotiated fixed payment for the contract's own Section 4.01 formula (common at going-private transactions involving Up-C firms: Switch, Vertiv, VWR Corp, McAfee, Evo Payments, Enfusion), record the payment amount and, where disclosed, the payment as a percentage of the pre-termination Early Termination Payment formula. Use the `terminated_merger` (or `terminated_<event-type>`) status flag.

For terminations that come from bankruptcy court orders, M&A closes, change-of-control events, dissolution, or expiration by operation of the contract's own terms, record in `contract_log.md`: economic-extinguishment evidence (last-recorded liability, valuation-allowance stance, regulatory events such as Form 15 deregistration or Nasdaq delisting), the date of the event, the citation in the most recent SEC filing that confirms the status, and the authoritative source for the legal instrument if it lives outside EDGAR (e.g., a bankruptcy docket URL).

#### Status flags

A contract's lifecycle state in `contract_log.md` is one of these flags:

- `in_force` — active TRA still operating per its terms.
- `terminated_by_expiration` — expired by operation of the contract's own terms (Section 4.01 ten-year anniversary, full utilization of tax attributes, or economic decay of tax attributes to zero).
- `terminated_merger` — terminated at an M&A close, typically via negotiated termination payment amendment.
- `terminated_change_of_control` — terminated by a Section 4.01 change-of-control trigger executed as such.
- `terminated_bankruptcy` — rejected or extinguished in a bankruptcy proceeding visible in SEC filings.
- `terminated_dissolution` — terminated by dissolution or winding up of the obligor.
- `terminated` — terminated via an explicit on-EDGAR termination instrument (whether titled "Amendment" or "Termination Agreement" or similar). Used when the parties executed a TRA-specific termination paper rather than the termination coming from an external event like a merger or bankruptcy.
- `terminated_unverified` — economic extinguishment is clear but the legal mechanism is not visible in SEC filings (typical of bankruptcy resolutions documented only on the claims-agent docket).
- `transferred_offledger` — the TRA is alive in law but the obligor entity has been deconsolidated from the firm of interest's consolidated statements, so the liability no longer appears on the firm's balance sheet (e.g., Oaktree post-Brookfield merger). The contract continues to generate payments at the deconsolidated entities.
- `economically_extinguished_in_force` — the TRA's economic value is zero (e.g., full valuation allowance because tax attributes cannot be utilized), but the contract is legally in force and may be reinstated (e.g., FXCM's 2015 write-down and 2017 RSA reinstatement).
- `never_executed` — the TRA was filed in form-of or unexecuted draft but the deal was amended before close to remove the TRA, so no executed instrument exists (e.g., Swiftmerge / AleAnna).

When a status changes (e.g., from `in_force` to `terminated_merger`), record both the prior flag and the transition date in `contract_log.md`.

#### What is NOT a termination signal

The following are payment-status or covenant disclosures, not terminations. Repeated mentions across filings are normal:

- **Valuation allowance / no-liability-recognized disclosures.** A TRA that never accrues a payable because the company maintains a full valuation allowance on the underlying deferred tax assets is still in force. "No liability recognized" footnotes are not cancel signals; they are normal disclosures while the TRA's economic benefit is depressed.
- **Payment-restriction covenants in debt agreements.** A credit-agreement amendment that prohibits TRA payments until certain debt-amortization milestones are met restricts payment timing; it does not terminate the TRA.
- **Subordination provisions.** Routine subordination of TRA payments to senior debt is structural, not termination.

#### Source filing vs announcement filing

When an amendment, restatement, or termination is announced in an 8-K (typically Item 1.01 for entering into a material agreement or Item 1.02 for termination of a material agreement) but the document text first appears in a later filing (e.g., as a 10-Q or 10-K exhibit), record both in `contract_log.md`:

- **Source filing:** the filing containing the actual contract document text. This is what gets cited as "Source filing" in the entry.
- **Announcement filing:** the 8-K. Cross-reference as "Announced in [accession] dated [date]; document text filed with [source-filing accession]".

This avoids pointing at an 8-K that summarizes the contract without containing the text.

### Step 4: determine origination dates

Apply the following cascade in order:

**Priority 1: preamble date.**

The contract's opening recitals typically include a date: "This Tax Receivable Agreement, dated as of \[date\], is entered into by and between..." Use that date.

**Priority 2: trigger event date.**

When the preamble date is blank (common for unexecuted contracts filed with registration statements), the agent reads the firm's surrounding filings to identify the event that created the relevant tax asset: the IPO date (for Up-C structures), the effective date of a merger, the date of partnership formation, or the closing date of a restructuring. Relevant filing types to check: IPO 8-K (Item 1.01), merger 8-K (Item 2.01), the S-1 effective date, or the 10-K tax footnote disclosing the initial TRA liability.

**Priority 3: exhibit filing date.**

When neither the preamble nor the trigger event can be identified from available documents, use the date on which the exhibit was first filed with the SEC. Set the `origin_date_unverified` flag in `contract_log.md`.

### Step 5: write per-filing annotations

For each filing (not just exhibit documents):

-   Read the TRA-relevant sections of the primary document.
-   Write one entry to `filing_notes.md`.

Annotation lengths upper bound by filing type:

| Content | Expected annotation |
|-----------------------|------------------------------------------------|
| Standard periodic disclosure, no new info | One line: form type, date, accession, "no new TRA information." |
| Filing with a new payment amount | One sentences with the amount, payment period cited. |
| TRA Amendment | One paragraph describing what changed and why. In elaborate restructurings or M&A related amendments this may be longer, but keep it as short and focused as possible on the TRA. |
| Termination announcement | One paragraph with effective date, payment (if any), and counterparties. |
| IPO / Up-C registration statement | Two to four sentences including Up-C status, type of underlying tax assets, payout rate, and eligible attributes. |

When the stripped text around a TRA mention in an amended filing (e.g. 10-K/A vs 10-K for the same filing period) is identical to that in the original or a previous amended filing version (word-for-word match in the surrounding paragraph), annotate as "Amended same as original" without repeating the text.

#### Redacted contract terms

When a contract is filed with material redactions (e.g., per-recipient amounts in an Annex A shown as `[*****]`, or specific dollar payments redacted from a negotiated termination payment amendment), record what is disclosed elsewhere: the aggregate payment amount often appears in the related DEFM14A or proxy materials even when the per-recipient breakdown is redacted in the exhibit (e.g., Evo Payments's $225M payment in the DEFM14A). Note both the redaction and the aggregate-from-elsewhere source in `contract_log.md`. Do not infer redacted amounts; leave them as `[redacted]` if no public disclosure exists.

#### Cross-CIK references

When the firm is a beneficiary, acquirer, financing arm, or otherwise expected to have zero contract files (see the workflow preamble), record the cross-reference explicitly: "Actual contract documents live under CIK <other-CIK> (<other-firm-name>); this directory carries only carrying-value disclosures / acquisition-accounting line items / financing-arm related-party notes." This makes the absence of TRA directories legible to a downstream consumer and points the next dispatch at the right CIK if a full document set is needed.

#### Date attribution for filing_notes entries

For each filing, attribute a date in this priority order:

1. **Date of report** (8-K) or **period of report** (10-K, 10-Q, DEF 14A): extracted from the document text where present.
2. **Filing date** as registered with SEC: extracted from SEC submissions metadata.
3. **Period-end from filename slug:** for inline-XBRL-only filings whose visible text omits an explicit date (e.g., `vnce-20230128.htm` → period ending January 28, 2023), use the period-end encoded in the filename. Note this convention in a Coverage note at the end of `filing_notes.md`.

**Do not** infer dates from the accession-number prefix. The first 10-digit segment is the filer's CIK and carries no date information. The middle two-digit segment encodes the SEC submission year, but can differ from the filing's date of report by months; treat it as a fallback only when no other source is available.

### Step 6: coverage gaps

When the firm has a known TRA-impacting event (Chapter 11 petition, M&A close, dissolution, Form 15 deregistration) but the filings post-dating that event are not in the directory:

- Record a "Coverage gap" entry in `contract_log.md` listing the event date, the expected filings (e.g., Form 15 deregistration, plan confirmation 8-K, post-merger Form 25), and the authoritative source if known (e.g., bankruptcy docket URL on Kroll, Epiq, or KCC; merger agreement under the acquirer's CIK).
- Do not infer the TRA's fate from absence of evidence. An honest coverage-gap note is preferred to an inferred "terminated" without a citation.
- Flag that a future re-run of `tra-download-filings` should extend the form filter or scan the acquirer's filings to close the gap.

### Step 7: clean up raw downloaded filings

After successfully writing `contract_log.md` and (where applicable) `filing_notes.md`, delete every `<accession>/` subdirectory from the firm directory. The raw `<accession>/` directories are the per-filing downloads from `tra-download-filings` and are no longer needed once the analysis is complete; the TRA contract files saved under `TRA-*/` (if any) carry the legally meaningful documents, and `filing_notes.md` carries every filing's annotation.

Cleanup applies regardless of whether any `TRA-*/` subdirectory exists or whether `filing_notes.md` is present. A mention-only firm (no TRA contracts saved) still gets its raw `<accession>/` subdirectories deleted, because the analysis outputs are complete and the raw filings are no longer needed.

Safety preconditions before deletion:
1. `contract_log.md` exists and is non-empty.
2. EITHER:
   - `filing_notes.md` exists and is non-empty (the standard case), OR
   - `contract_log.md` contains the explicit omission sentence: "No substantive TRA content found across the firm's filings; `filing_notes.md` omitted per spec." (the non-substantive-mention-only case).
3. The cleanup must not touch:
   - `contract_log.md` or `filing_notes.md` (if present)
   - Any `TRA-<date>[-<diff>]/` subdirectory
   - Any other markdown or analysis file at the firm-directory level

If any precondition fails, skip cleanup and flag the firm with a `cleanup_skipped` note in the next-run revision history.

## Re-running on an existing firm directory

When this skill is dispatched on a directory that already contains a prior run's outputs:

1. Read the existing `contract_log.md` and `filing_notes.md` before doing anything else.
2. Do not redo work that is already correct. The current run augments rather than replaces.
3. If the prior run produced incorrect structure (e.g., contract directories named by accession number instead of origination date, or unexecuted-and-executed pairs saved as distinct TRAs when they are the same contract per the Step 3 criteria), remediate the structure per the current spec and note the cleanup in `contract_log.md`.
4. Add per-filing entries for any new filings in `filing_notes.md` in the appropriate chronological position.
5. If new evidence changes a prior conclusion (e.g., the TRA's fate in bankruptcy was previously "could not be determined" but new filings now provide an answer), update the relevant section of `contract_log.md` with a brief revision note explaining what changed.

## File-naming rules

Output files: `filing_notes.md` and `contract_log.md`. These names are safe. Do NOT use `report.md`, `summary.md`, `findings.md`, or `analysis.md`; the subagent Write tool blocks those filenames.

For contract files, use the filename as it appears in the filing index (e.g., `ex-10.1.htm`), prefixed with the filing date if the index name is not unique across filings: `<YYYY-MM-DD>_<filename>.<ext>`.

## What this skill does not do

-   Download filings (that is `tra-download-filings`).
-   Build a cross-firm timeline or database (that is `tra-build-timeline`).
-   Render HTML; plain-text stripping is sufficient for contract reading.
-   Produce a machine-readable artifact; structured output is deferred to `tra-build-timeline`.