# TRA background: subject-matter reference

------------------------------------------------------------------------

## 1. What a Tax Receivable Agreement is

A Tax Receivable Agreement is a contract by which a public company
("**PubCo"**) commits to pay a defined percentage of certain realized
tax savings to a defined set of **beneficiaries** (typically pre-IPO
holders, sponsor entities, or other counterparties). The payment
percentage is most often, but not always, 85%.

A TRA is an obligation to pay someone else realized tax savings, when
those realized tax savings occur. This transfers a percent of the
financial effect of tax savings to a different entity. The most common
origin of a TRA is an **Up-C IPO**: a partnership goes public via a
corporate holding structure ("Up-C") that retains pre-IPO holders'
partnership units. Future exchanges of those units for PubCo stock
create stepped-up tax basis at PubCo, and the TRA pays the pre-IPO
holders a share of the resulting tax savings when they occur. Other
origins include M&A transactions, SPAC business combinations, reverse
mergers, partnership restructurings, and plan-of-reorganization exits
from bankruptcy.

------------------------------------------------------------------------

## 2. Title patterns

A TRA-related document's title usually falls into one of these patterns:

- **Origination.** "Tax Receivable Agreement", "Income Tax Receivable
  Agreement".
- **Restatement.** "Amended and Restated Tax Receivable Agreement",
  "Second Amended and Restated Tax Receivable Agreement", and so on.
- **Numbered amendment.** "Amendment No. X to the \[Amended and
  Restated\] Tax Receivable Agreement", "First Amendment to the Tax
  Receivable Agreement".
- **Termination-by-distinct-title.** The effect is to terminate the TRA,
  but the document is titled as something other than "Amendment" or
  "Termination of TRA". Common variants: "Payment and Termination
  Agreement", "TRA Repurchase Agreement", "Tax Receivable Prepayment
  Agreement", "Waiver and Termination of Tax Receivable Agreement",
  "Termination and Release Agreement", "Exchange and Termination
  Agreement".
- **Beneficiary modification.** "TRA Waiver and Assignment Agreement",
  "Waiver of Tax Receivable Agreement (Individual)" used when one
  beneficiary releases their share back to PubCo or assigns rights to
  another party. The underlying TRA continues with a modified
  beneficiary roster.
- **Waiver of a specific provision.** Waivers modifying behavior under a
  named section without amending the contract text directly (e.g.,
  Apollo's May 2022 waiver of early-termination right). Treat as an
  amendment with a `waives: <provision>` flag.

**The title is a strong hint, but content determines classification.**
Always read the document to understand what it actually does. "Payment
and Termination Agreement" is functionally a terminating amendment; "TRA
Waiver and Assignment" modifies the beneficiary roster without
terminating; "TRA Repurchase Agreement" is a TRA termination via
buyback; the company buying back the TRA cashflows from the
beneficiaries is economically equivalent to a termination payment.

------------------------------------------------------------------------

## 3. Structural anatomy

A typical executed TRA carries these sections in roughly this order:

1.  **Title and parties block.** Centered title; "This Tax Receivable
    Agreement, dated as of \[date\], is entered into by and between
    \[PubCo\] and \[the Pre-IPO Holders / Continuing LLC Members /
    Sponsor Party / specifically named beneficiaries\]."
2.  **Recitals (WHEREAS/NOW/THEREFORE clauses).** Background on the Up-C
    structure, IPO, or triggering transaction.
3.  **Definitions.** The defined-term block.
4.  **Determinations and Schedules.** Realized Tax Benefit, Hypothetical
    Tax Liability, Actual Tax Liability, Tax Benefit Schedule, Exchange
    Basis Schedule.
5.  **Payments.** Timing, calculation, early-termination payment
    formula.
6.  **Tax Returns and Reconciliations.**
7.  **Term and Termination.**
8.  **General Provisions.** Governing law, arbitration, assignment,
    amendment procedure.
9.  **Signature pages.**
10. **Schedule A (notices) and Exhibits A, B, ...** (Exchange Basis
    Schedule formulas, Tax Benefit Schedule, etc.).

For amendments and addenda, the structure is shorter (one or two
articles, parties, signatures) and recitals reference the prior
agreement.

------------------------------------------------------------------------

## 4. Defining terminology

Standard defined terms that recur in TRA contracts:

- **Realized Tax Benefit**: the tax savings PubCo actually realizes in a
  year from the covered tax attributes, computed against the
  Hypothetical Tax Liability.
- **Hypothetical Tax Liability**: what PubCo's tax liability would have
  been without the covered tax attributes.
- **Actual Tax Liability**: PubCo's actual tax liability for the year.
- **Tax Benefit Schedule**: the per-year schedule of Realized Tax
  Benefits used to compute payments.
- **Exchange Basis Schedule**: the per-exchange schedule tracking basis
  step-ups generated by each LLC-unit-to-stock exchange.
- **Net Tax Benefit Payment**: the payment amount due after applying the
  sharing ratio.
- **Early Termination Payment**: the present value of remaining future
  payments owed if the TRA is terminated early (via change-of-control,
  election, or agreement). The termination payment formula is the
  contract's own valuation mechanism and is central to termination
  economics.
- **Valuation Assumptions**: the assumptions used to calculate a
  termination payment.
- **Section 754 Election**: the partnership-tax election that permits
  basis step-up on partnership-interest transfers; the mechanism
  underlying Up-C TRAs.
- **Continuing LLC Members / Pre-IPO Holders / Sponsor Party / TRA
  Beneficiaries**: the contractual beneficiary set, named differently by
  different drafters but referring to the same role.
- **Pre-IPO Tax Assets**: the tax attributes covered by the TRA, fixed
  as of the IPO or trigger event.

------------------------------------------------------------------------

## 5. The four standard contractual terms

Nearly every TRA states identifiable values for these four terms. These
are the fields a terms-summary extractor should capture:

### 5.1 Tax-asset type

Which tax attributes generate payments. Options:

- **Basis Step-Up**: IRC §743(b) / §754 basis adjustments (Up-C
  exchanges), or §732 / §1012 in disregarded-entity cases. Includes
  §338(h)(10) elections, §336(e) elections, §1012 cost-basis
  acquisitions, and §197 amortization of acquired intangibles. For
  corpus tagging purposes, these all collapse to `Basis Step-Up;` we
  care about basis vs non-basis, not the specific IRC mechanism.
- **NOL**: net operating loss carryforwards. Capital losses are also
  tagged `NOL`.
- **Other tax credit**: foreign tax credits, imputed interest
  deductions, R&D credits, etc.

A single TRA can cover multiple attributes (`[NOL, Basis Step-Up]`).

### 5.2 Sharing ratio

The percentage of Realized Tax Benefits paid to beneficiaries. Most
often 85%. When multiple rates apply to different categories (e.g., 85%
on basis step-up, 50% on NOL), state both. Aggregate caps and
per-tranche structures (e.g., PG&E's \$1.35B cap) are recorded
separately as notes, not as part of the sharing ratio.

### 5.3 Early-termination valuation assumptions

The discount rate plus the assumption set governing the termination
payment calculation. Discount rate examples: LIBOR + 100bps, Applicable
Treasury Rate, SOFR + 200bps. The assumption set typically covers:

- Whether future taxable income is assumed sufficient to use all
  deductions.
- The tax-rate regime (statutory rate at termination; or projected
  forward).
- Treatment of loss carryovers and non-amortizable assets.
- Treatment of unexchanged LLC units (commonly: treated as exchanged on
  the termination date).

### 5.4 Default interest rate

The rate charged on late payments. Typical: LIBOR + 500bps, Prime +
200bps.

------------------------------------------------------------------------

## 6. What is NOT a TRA

These agreements are commonly filed alongside a TRA or share parties and
terminology. They are not themselves TRAs:

- **Tax Sharing Agreement.** Intercompany allocation of tax liability
  among members of a consolidated group. No payment from PubCo to
  outside beneficiaries.
- **Tax Matters Agreement / Tax Separation Agreement.** Spin-off
  context; allocates pre- and post-distribution taxes between parent and
  spun-off entity. May mention a TRA but is not a TRA itself.
- **Exchange Agreement.** Governs the mechanism for exchanging LLC Units
  for PubCo Class A common stock. Often co-filed with a TRA but a
  separate contract with no payment obligation tied to tax savings.
- **LLC Operating Agreement / Limited Liability Company Agreement.**
  Governs the operating partnership's internal affairs. Carries
  `basis adjustment`, `section 754 election`, `tax asset` defined terms
  because the LLC is the entity making the basis-step-up election, but
  is not itself a TRA.
- **Stockholders Agreement / Voting Agreement / Registration Rights
  Agreement.** Govern voting, board representation, transfer
  restrictions, or registration rights.
- **Credit / loan agreements.** May name the TRA as a restricted-payment
  carve-out or as collateral. Credit agreements that *restrict* TRA
  payments do not terminate the TRA.
- **Stock Purchase / Shareholders / Investor Rights agreements** that
  assume or list the TRA among other IPO documents.
- **Merger / purchase agreements** ("Agreement and Plan of Merger",
  "Transaction Agreement") that require TRA termination at closing as
  one step among many.
- **Contribution and Exchange agreements** that reference TRA
  termination only in a recital about closing.
- **Plan Support Agreements / Backstop Commitment Letters** in
  bankruptcy contexts that reference a "Tax Benefits Monetization"
  mechanism. These govern bankruptcy plan support, not TRA payments.
- **TRA Bonus Plan / Tax Receivable Agreement Bonus Plan.** Compensation
  arrangement paying employees a share of TRA-related tax savings as
  bonus comp (e.g., Acreage Holdings's Bonus Plans I and II). Tied to
  but separate from the classical TRA. Record as a parallel non-TRA
  agreement with a `parallel-bonus-plan: true` flag; do not save as a
  TRA contract file.
- **8-K item descriptions** that paraphrase the TRA's terms. Filing-text
  documents, not contracts.

------------------------------------------------------------------------

## 7. Firm roles relative to a TRA

The firm whose CIK we are processing can occupy different roles relative
to a TRA. The role determines whether to expect any saved contract files
at all and which other CIKs to cross-reference:

- **PubCo (TRA obligor).** The firm went public via Up-C IPO, SPAC
  business combination, or similar and committed to pay TRA
  beneficiaries. The original TRA, amendments, and any termination are
  filed under the firm's own CIK. The default case.
- **Beneficiary.** The firm is a recipient of TRA payments rather than
  the obligor (e.g., McKesson received payments from Change Healthcare
  under the McK TRA). Actual contract documents live under the obligor's
  CIK.
- **Acquirer.** The firm acquired another company and extinguished the
  target's TRA at the acquisition close (e.g., Comcast settled
  DreamWorks's TRA at acquisition). Actual contract documents live under
  the target's CIK; the firm's filings disclose the settlement as an
  acquisition-accounting line item in the next post-close periodic
  filing.
- **Financing arm.** The firm is a downstream financing subsidiary of an
  Up-C parent and is not a contractual party to the TRA but funds
  payments via upstream distributions (e.g., VWR Funding for VWR Corp).
- **Never executed.** The firm contemplated a TRA in a draft or form-of
  exhibit but the deal was amended before close to remove the TRA, so no
  executed contract exists (e.g., Swiftmerge / AleAnna). Save the draft
  only and use status flag `never-executed`.

When a firm is anything other than PubCo, the firm-level log should
cross-reference the obligor / target / parent CIK so a downstream
consumer can locate the actual contract documents.

------------------------------------------------------------------------

## 8. Trigger-event taxonomy

What created the underlying tax asset. Used as the `trigger-event-type`
field in TRA frontmatter:

- **IPO.** Up-C IPO with the TRA created at IPO close. Future LLC-unit
  exchanges generate ongoing new tax assets.
- **Asset purchase.** All asset-purchase-style triggers regardless of
  the specific IRC mechanism (§1012 cost basis, §338(h)(10), §336(e),
  §1001, §197 amortization). The economic distinction from IPO is that
  the step-up is one-shot and amortizes down rather than being
  replenished by future exchanges.
- **Merger.** TRA created at merger close.
- **SPAC business combination.** TRA created at the SPAC's de-SPAC
  close.
- **Plan of reorganization.** TRA created as part of a Chapter 11 plan
  (e.g., PG&E's post-emergence TRA).
- **Spin-off.** TRA created at a spin-off close.
- **Up-C transition.** TRA created when an existing public company
  transitions into an Up-C structure (rare).
- **Section 162 issuance.** TRA covering §162 executive-compensation
  deductions.
- **Joint venture formation.** TRA created when a joint venture is
  formed.
- **Other.** Anything else.

------------------------------------------------------------------------

## 9. Same vs distinct contract

When processing a firm's filings, the same TRA frequently appears in
multiple exhibits (unexecuted draft in an S-1, executed version in an
8-K, re-attached copies in later 10-Ks). Distinguish "same contract in
different state" from "distinct contracts" before saving.

### 9.1 Criteria for "same contract"

Two documents represent the same underlying contract when ALL match:

- **Parties.** Same PubCo, same defined beneficiary group.
- **Effective date.** Same preamble date, OR one is blank (unexecuted)
  and the other carries the date the parties later signed.
- **Payment terms.** Same sharing ratio, same definition of "Realized
  Tax Benefit", same payment cadence.
- **Tax attributes covered.** Same set of tax assets giving rise to
  payments.
- **Term and termination triggers.** Same termination provisions and
  same early-termination payment formula.

An unexecuted draft and the corresponding executed version of the same
agreement satisfy these criteria; differences are execution-related
metadata.

**Beneficiary trusts or affiliated transferees added at execution.** If
the unexecuted form-of names only individual Principals but the executed
version adds family trusts, holding companies, or affiliated transferee
vehicles as additional named beneficiaries, treat as execution-state
difference, not a separate contract.

**Wholesale beneficiary reassignment via amendment.** When an amendment
changes the beneficiary set wholesale (e.g., assigning all TRA Member
rights to a single new entity, as in Acreage's Third Amendment assigning
rights to Canopy USA), the underlying contract persists. Treat as an
amendment to the same contract when the amendment text uses "amend" or
"assign" language.

### 9.2 Criteria for "distinct contracts"

Two documents are distinct contracts when ANY of the following differ:

- **Parties.** The beneficiary set is meaningfully different (e.g., one
  TRA is with the original Continuing LLC Members; another is with a
  Sponsor Party or an acquired counterparty from a later transaction).
- **Tax attributes covered.** One TRA covers basis step-ups; another
  covers NOL carryforwards or foreign tax credits. Typically parallel
  agreements at the same firm.
- **Sharing ratio.** 85% vs 75%, or per-attribute tiered rates that
  differ.
- **Effective date with substantive differences.** A TRA established at
  IPO is distinct from a TRA established at a later M&A event, even at
  the same PubCo.

### 9.3 Best-effort term comparison

When deciding, focus on these provisions in priority order:

1.  Sharing ratio (Payments / Determinations section).
2.  Tax attributes covered (Definitions: "Tax Attributes", "Pre-IPO Tax
    Assets", "Eligible Tax Benefits").
3.  Beneficiary identification (parties listed in preamble or
    beneficiary annex).
4.  Termination provisions (early-termination calculations,
    change-of-control triggers).
5.  Governing law and dispute resolution (rarely changes, but worth a
    quick check).

------------------------------------------------------------------------

## 10. Multiple parallel TRAs

A firm can carry two or more distinct TRAs simultaneously (e.g., one
covering NOL carryforwards, one covering stepped-up basis, or one
inherited from an acquisition). Identify each by origination date. If
two share an origination date, they can be differentiated by whichever
attribute differs most prominently: tax attribute type (`NOL`, `Basis`),
counterparty name, payout rate (`rate-85pct`), or another short stable
label.

------------------------------------------------------------------------

## 11. Terminations and status flags

### 11.1 Substance over form

There are multiple ways to terminate a TRA, the classifier records
whether termination occurred and the cause. **The termination label is
by economic substance, not by the form.** If a contract has the effect
of terminating the TRA, save it as a termination regardless of whether
the document is titled "Termination Agreement", "Payment and Termination
Agreement", "Amendment No. N", "Second Amended and Restated Tax
Receivable Agreement", "TRA Repurchase Agreement", "Exchange and
Termination Agreement", or something else altogether.

### 11.2 Status flags

A contract's lifecycle state is one of:

- `in-force`: TRA still active.
- `terminated-by-expiration`: expired within the original contract's own
  terms (ten-year anniversary, full utilization of tax attributes,
  economic decay to zero).
- `terminated-merger`: terminated at an M&A close, typically via
  negotiated termination payment amendment.
- `terminated-change-of-control`: terminated via change-of-control.
- `terminated-bankruptcy`: rejected or extinguished in a bankruptcy
  proceeding visible in SEC filings.
- `terminated-dissolution`: terminated by dissolution or winding up of
  the obligor.
- `terminated`: terminated via an explicit on-EDGAR termination (whether
  titled "Amendment", "Termination Agreement", "Repurchase Agreement",
  or similar). Used when the parties executed a TRA-specific termination
  paper rather than the termination coming from an external event.
- `terminated-unverified`: economic extinguishment is clear but the
  legal mechanism is not visible in SEC filings (typical of bankruptcy
  resolutions documented only on the claims-agent docket).
- `transferred-offledger`: the TRA is alive in law but the obligor
  entity has been deconsolidated from the firm of interest's
  consolidated statements, so the liability no longer appears on the
  firm's balance sheet (e.g., Oaktree post-Brookfield merger). The
  contract continues to generate payments at the deconsolidated
  entities.
- `economically-extinguished-in-force`: the TRA's economic value is zero
  (e.g., full valuation allowance because tax attributes cannot be
  utilized), but the contract is legally in force and may be reinstated
  (e.g., FXCM's 2015 write-down and 2017 RSA reinstatement).
- `never-executed`: the TRA was filed in form-of or unexecuted draft but
  the deal was amended before close to remove it.

When a status changes (e.g., from `in-force` to `terminated-merger`),
record both the prior flag and the transition date.

### 11.3 Negotiated termination payments

When a TRA is terminated as part of a merger and substitutes a
negotiated fixed payment for the contract's own termination payment
formula (common at going-private transactions involving Up-C firms:
Switch, Vertiv, VWR Corp, McAfee, Evo Payments, Enfusion), record the
payment amount and, where disclosed, the payment as a percentage of the
contractually stipulated termination payment. Use the
`terminated-merger` (or `terminated-<event-type>`) status flag.

### 11.4 What is NOT a termination signal

The following are payment-status or covenant disclosures, not
terminations. Repeated mentions across filings are normal:

- **Valuation allowance / no-liability-recognized disclosures.** A TRA
  that never accrues a payable because the company maintains a full
  valuation allowance on the underlying deferred tax assets is still in
  force. "No liability recognized" footnotes are normal disclosures
  while the TRA's economic benefit is depressed.
- **Payment-restriction covenants in debt agreements.** A
  credit-agreement amendment that prohibits TRA payments until certain
  debt-amortization milestones are met restricts payment timing; it does
  not terminate the TRA.
- **Subordination provisions.** Routine subordination of TRA payments to
  senior debt is structural, not termination.

------------------------------------------------------------------------

## 12. Date attribution

The dates that matter for a TRA — origination, amendment, termination —
must be attributed with care, because filings can disclose events months
after they occur.

### 12.1 Origination-date cascade

Apply in order:

1.  **Preamble date.** "This Tax Receivable Agreement, dated as of
    \[date\]..." in the contract's opening recitals.
2.  **Trigger-event date.** When the preamble date is blank (common for
    unexecuted contracts in registration statements), read the firm's
    surrounding filings to identify the event that created the relevant
    tax asset: IPO date (Up-C), merger effective date, partnership
    formation date, restructuring close date. Filings to check: IPO 8-K
    (Item 1.01), merger 8-K (Item 2.01), S-1 effective date, 10-K tax
    footnote disclosing the initial TRA liability.
3.  **Exhibit filing date.** When neither preamble nor trigger event is
    identifiable, use the date the exhibit was first filed with the SEC.
    Set the `origin-date-unverified` flag.

### 12.2 Date for saved contract filenames

The date in a saved contract filename is the **SEC filing date** (the
date the document became publicly available on EDGAR), NOT the effective
date inside the document body and NOT the period-end of the parent
filing. When the same contract was first attached to an S-1 and later
re-attached to a 424B3 prospectus, each saved copy carries the filing
date of its own enclosing submission. The internal "dated as of" line is
recorded in the contract log but not used in the filename.

### 12.3 Filing-log entry dates

For each filing, attribute a date in this priority order:

1.  **Date of report** (8-K) or **period of report** (10-K, 10-Q, DEF
    14A).
2.  **Filing date** as registered with SEC.
3.  **Period-end from filename slug** (for inline-XBRL-only filings
    whose visible text omits an explicit date, e.g., `vnce-20230128.htm`
    → period ending January 28, 2023).

Do not infer dates from the accession-number prefix. The first 10-digit
segment is the filer's CIK and carries no date information.

------------------------------------------------------------------------

## 13. Source filing vs announcement filing

When an amendment, restatement, or termination is announced in an 8-K
(typically Item 1.01 for entering into a material agreement, Item 1.02
for termination of a material agreement) but the document text first
appears in a later filing (e.g., as a 10-Q or 10-K exhibit), record
both:

- **Source filing:** the filing containing the actual contract document
  text.
- **Announcement filing:** the 8-K. Cross-reference as "Announced in
  \[accession\] dated \[date\]; document text filed with \[source-filing
  accession\]".

This avoids pointing at an 8-K that summarizes the contract without
containing the text.

------------------------------------------------------------------------

## 14. Vocabulary discipline

Specific phrasings to avoid and the reasons:

- **Do not say "bilateral" or "multilateral".** Every TRA is
  structurally a two-party contract: PubCo (obligor) and the collective
  LLC shareholders (beneficiaries). When the beneficiary side is broken
  into sub-groups within one contract (e.g., Fifth Third, Advent, and
  JPDN named as the LLC-shareholder sub-groups in the Vantiv TRA),
  describe the sub-groups by name rather than labeling the contract
  "multilateral". The multi-named-beneficiary-group structure is normal,
  not a structural quirk.
- **Do not say "cap-and-release"** to describe a TRA termination. "Cap"
  misleadingly implies that further payments may still occur subject to
  a ceiling, when in fact a single payment terminates the contract. Use:
  - "termination payment" (basic case)
  - "change-of-control payment" (Change of Control-triggered)
  - "settlement payment" or "negotiated termination payment" (negotiated
    outside the contractual termination payment)
- **Do not use the acronym "EFTS".** Write "EDGAR full-text search" or
  "full-text search".
- **Avoid jargon-stacking in narrative paragraphs.** Terms of art
  (`Up-C`, `TRA`, `M&A`) are fine when they appear naturally, but lead
  with what happened, not with the term of art.

------------------------------------------------------------------------

## 15. Form types relevant to TRA discovery

The SEC filings that disclose TRA events:

- **8-K**: material-events filings. Item 1.01 announces entering into a
  material agreement (TRA origination, amendment); Item 1.02 announces
  termination; Item 2.01 announces completion of acquisition or
  disposition (often paired with TRA termination at merger close).
- **10-K**: annual report. The tax footnote discloses the TRA's carrying
  value, payment cadence, valuation allowance stance, and any amendment
  activity in the period. Subsequent-events notes can disclose
  post-period termination activity.
- **10-Q**: quarterly report. Updated carrying values and any quarter's
  payment activity.
- **S-1 / S-1/A**: IPO registration. The TRA is attached as an exhibit,
  often as an unexecuted form-of in the initial S-1 and an executed
  version in a later amendment or in the 8-K filed at closing.
- **S-4 / S-4/A**: merger / business-combination registration. Attaches
  the TRA for SPAC business combinations and reverse mergers.
- **424B**: prospectus variants filed at IPO effectiveness. Often
  re-attach the executed TRA.
- **DRS / DRS/A**: confidential draft registration statements. Earlier
  versions of S-1 content.
- **DEF 14A / DEFM14A / DEFA14A / PRE 14A**: proxy statements. DEFM14A
  is the merger proxy and often discloses TRA-treatment terms at
  acquisition (including redacted payment amounts whose aggregates
  appear in the proxy even when the exhibit redacts the per-recipient
  breakdown).
- **20-F / 40-F / 6-K**: foreign-issuer equivalents.

The single-most-load-bearing form type for TRA event discovery is the
**8-K**, because material agreements, amendments, and terminations are
required to be disclosed within four business days. The 10-K's tax
footnote is the load-bearing form for ongoing status (carrying value,
valuation allowance, payment trajectory).

------------------------------------------------------------------------

## 16. Acquirer cross-check

When a firm was acquired during a TRA's life, run this four-step check
before fixing the TRA's status:

1.  Read the target's DEF14A merger proxy for "Tax Receivable Agreement"
    plus the acquirer's name.
2.  Read the merger-agreement exhibits (S-4 or 8-K Item 1.01) for an
    explicit TRA-treatment clause.
3.  Read the target's last pre-close 10-K or 10-Q subsequent-events
    note.
4.  Read the acquirer's post-close 10-K or 10-Q for the
    assumed-liability disclosure.

When the acquirer is itself in our processed set, add an inline pointer
to its filing log. When the acquirer is not yet processed but is on
EDGAR, note the acquirer's CIK so a future pass can fetch its filings.

------------------------------------------------------------------------

## 17. Redactions

When a contract is filed with material redactions (e.g., per-recipient
amounts in an Annex A shown as `[*****]`, or specific dollar payments
redacted from a negotiated termination payment amendment), record what
is disclosed elsewhere: the aggregate payment amount often appears in
the related DEFM14A or proxy materials even when the per-recipient
breakdown is redacted in the exhibit (e.g., Evo Payments's \$225M
payment in the DEFM14A). Note both the redaction and the
aggregate-from-elsewhere source. Do not infer redacted amounts; leave
them as `[redacted]` if no public disclosure exists.

------------------------------------------------------------------------

## 18. Coverage gaps

When a firm has a known TRA-impacting event (Chapter 11 petition, M&A
close, dissolution, Form 15 deregistration) but the filings post-dating
that event are absent from the directory, record an explicit "Coverage
gap" entry listing:

- The event date.
- The expected filings (e.g., Form 15 deregistration, plan-confirmation
  8-K, post-merger Form 25).
- The authoritative source if known (e.g., bankruptcy docket URL on
  Kroll, Epiq, or KCC; merger agreement under the acquirer's CIK).

Do not infer the TRA's fate from absence of evidence. An honest
coverage-gap note is preferred to an inferred "terminated" without a
citation.

------------------------------------------------------------------------