# Review notes: tra-background.md v1

Proposed changes to `docs/tra-background.md` after your first editing pass.
Organized as cross-cutting observations first, then a section-by-section review
covering necessity, bullet-vs-prose, and any other notes per section.

---

## Cross-cutting observations

### 1. Several agreed-upon edits did not make it into this round

We discussed removing these in chat; they're still present in the file:

- **The "Source skills" section** at the bottom. Provenance metadata; remove per our exchange.
- **"Expect zero TRA directories under the firm's CIK"** in Section 7 (Beneficiary and Financing arm entries). Operational layout language from the old pipeline; remove. The underlying domain insight ("contract documents live under the obligor's CIK, not this firm's") is already carried by the surrounding sentences.
- **The differentiator-slug paragraph** in Section 10 (`TRA-<YYYY-MM-DD>-<diff>`, etc.). Operational naming convention; remove. The underlying domain insight ("a firm can carry multiple distinct parallel TRAs") is the only part that belongs in this file and is already in the section's opening sentence.
- **"Operative" still appears in many places.** Section 2 closing paragraph ("operative effect terminates"), Section 6 (Exchange Agreement note's "operative effect terminates the TRA IS TRA-operative", merger entry's "operative effect is the merger"), Section 9.1 ("Operative payment terms"). We agreed to trim. Replacements per context: drop the word entirely, or substitute "effect" / "does the work of" / "what the contract is for".
- **"ETP" survived in three places.**
  - Section 11.3: "Section 4.01 ETP formula" — replace with "Section 4.01 termination payment formula" or just "termination payment formula".
  - Section 14, cap-and-release sub-bullets: "negotiated outside the contract's ETP formula" and "negotiated for materially less than the contract's ETP". Replace both with "termination payment".

### 2. One typo and one stub

- Section 4, new entry: **"Valuation Assumptions: the assumptions used to calculation a termination payment"** — "calculation" should be "calculate". Also, the entry is so short it reads as a stub (one fragment), while Section 5.3 covers this term in depth. Either expand the Section 4 entry (one full sentence pointing to Section 5.3 for detail) or remove it (Section 5.3 carries the substance).

### 3. One factual nuance introduced that needs propagation

Section 2's TRA Repurchase entry now says: **"TRA Repurchase Agreement is TRA buyback (the company buys back the TRA cashflows from the beneficiaries) and, if all cashflows are bought back, is treated as a termination."** This introduces a useful distinction (partial repurchase ≠ termination) that does not yet propagate to Section 11 (terminations). Two options:

- **(a) Propagate the qualifier** to Section 11.1's list of titles that count as terminations: drop "TRA Repurchase Agreement" from the title list, or add a parenthetical "(when all cashflows are repurchased)".
- **(b) Recognize partial repurchases as a separate document type**, analogous to "Beneficiary modification" — the underlying TRA continues with a reduced cashflow profile.

If (a) is the intent, Section 2 and Section 11 stay consistent. If (b), Section 2 needs a new title pattern entry ("partial repurchase") and Section 11 needs to clarify that termination requires complete buyback.

### 4. "Section 4.01" is a load-bearing reference that the document never explains

Section 11.2 (status flags) and 11.3 cite "Section 4.01" as the change-of-control / early-termination provision. Section 4.01 is real shorthand for the most common TRA structure, but a reader who hasn't seen a TRA before doesn't know what it refers to. Options:

- Add a one-line gloss in Section 3 (Structural anatomy) noting that the early-termination payment formula is "commonly Section 4.01" of the TRA.
- Or drop the "Section 4.01" cite from Sections 11.2 and 11.3 and just say "the change-of-control trigger" / "the contract's own termination payment formula".

### 5. Section 3 inconsistency

The 11-item numbered structural-anatomy list mixes items that carry a one-line gloss (1, 2, 4, 5, 6, 9, 11) with items that are just a header (3, 7, 8, 10). Either give every item a one-line gloss or drop the glosses for all of them — the current mix reads as if some items were forgotten.

### 6. Section dividers got expanded by Pandoc

Every `---` divider became `------------------------------------------------------------------------` — looks like a pretty-print pass through pandoc or a visual markdown editor. Functionally fine; the long dividers just add visual weight. If you want them shortened, a global replace from the long form back to `---` is one mechanical pass.

### 7. Form-code escaping artifact (Section 15)

The 424B line reads `**424B**\*` — an editor escaped the trailing `*`. Should be `**424B\***` (escape inside the bold) or `**424B***` (unescaped, which mostly works).

---

## Section-by-section review

For each section: **Necessary?** **Bullets-to-prose?** Other notes.

### Top matter (preamble, lines 1-14)

- **Necessary:** yes. Sets the scope rule (this file = domain, skills = mechanics) which is the document's whole reason to exist.
- **Bullets-to-prose:** n/a (already prose).
- **Other:** good as is.

### Section 1: What a Tax Receivable Agreement is

- **Necessary:** yes; foundational.
- **Bullets-to-prose:** n/a (already prose after your edit).
- **Other:** the new "obligation to pay someone else realized tax savings, when those realized tax savings occur" sentence is the cleanest version of the definition the file has had. Keep.

### Section 2: Title patterns

- **Necessary:** yes; this is reference material an agent or reader scans against.
- **Bullets-to-prose:** **keep bullets.** Each bullet is a discrete category with example titles; collapsing into prose would force readers to parse a paragraph instead of scanning a checklist.
- **Other:** see cross-cutting note 3 (TRA Repurchase qualifier needs to propagate to Section 11). Closing paragraph still uses "operative" — replace.

### Section 3: Structural anatomy

- **Necessary:** yes; gives readers the mental model of TRA shape so later references to "the Determinations section" or "the Term and Termination article" land.
- **Bullets-to-prose:** **keep as a numbered list.** Ordering is meaningful (sections appear in this order in real TRAs).
- **Other:** fix the gloss inconsistency (cross-cutting note 5). Consider adding "(commonly Section 4.01)" to item 8 (Term and Termination) so later references to Section 4.01 land.

### Section 4: Defining terminology

- **Necessary:** yes; glossary the rest of the file relies on.
- **Bullets-to-prose:** **keep bullets.** Glossary form is correct for term-definition pairs.
- **Other:** fix the "Valuation Assumptions" typo and stub (cross-cutting note 2).

### Section 5: The four standard contractual terms

- **Necessary:** yes; these are the fields downstream extraction targets, so the inventory has to be authoritative.
- **Bullets-to-prose:** mixed.
  - 5.1 (Tax-asset type): **keep bullets** — three distinct categories.
  - 5.2 (Sharing ratio): **already prose.** Good.
  - 5.3 (Early-termination valuation assumptions): **keep bullets** for the four assumption-set items.
  - 5.4 (Default interest rate): **already prose.** Good.
- **Other:** none.

### Section 6: What is NOT a TRA

- **Necessary:** yes; this is the discriminator that prevents false positives. Probably the most-consulted section.
- **Bullets-to-prose:** **keep bullets.** 12 distinct document types, scanned as a "not this, not this, not this" reference.
- **Other:** several "operative" instances in the bullets (Exchange Agreement, Merger / purchase). Replace per cross-cutting note 1.

### Section 7: Firm roles relative to a TRA

- **Necessary:** yes; the role taxonomy feeds the `tra-role` field and the cross-CIK pointer logic.
- **Bullets-to-prose:** **keep bullets.** Five distinct roles, each with its own rules.
- **Other:** remove "Expect zero TRA directories" in Beneficiary and Financing arm (cross-cutting note 1). The closing prose ("When a firm is anything other than PubCo...") is good.

### Section 8: Trigger-event taxonomy

- **Necessary:** yes; populates the `trigger-event-type` field. Worth keeping the explicit "Other" line so the schema acknowledges open-endedness.
- **Bullets-to-prose:** **keep bullets.** Nine distinct categories, scanned as a classification reference.
- **Other:** none.

### Section 9: Same vs distinct contract

- **Necessary:** yes; the contract-grouping rule feeds Phase 3 (cross-firm consolidation) of `workflow-goal.qmd`. Without this, the consolidation step has no criteria.
- **Bullets-to-prose:**
  - 9.1 and 9.2: **keep bullets** (criteria checklists).
  - 9.3: **collapse to one sentence at the end of 9.2.** Currently a 5-item numbered priority list; could be one prose line: "When the criteria above don't decide cleanly, prioritize comparison of sharing ratio, then tax attributes, then beneficiary identification, then termination provisions, then governing law (which rarely changes)." That collapses 9.3 entirely.
- **Other:** "operative payment terms" in 9.1 → drop "operative" or replace with "payment terms".

### Section 10: Multiple parallel TRAs

- **Necessary:** marginal as a standalone section. After removing the differentiator-slug paragraph (cross-cutting note 1), the remainder is two sentences: "A firm can carry two or more distinct TRAs simultaneously (e.g., one covering NOL carryforwards, one covering stepped-up basis, or one inherited from an acquisition). Identify each by origination date."
- **Bullets-to-prose:** already prose.
- **Other:** consider folding into Section 9 as a closing observation: "Firms can also carry multiple distinct TRAs in parallel — identified by origination date — and the same criteria apply when deciding whether a newly encountered exhibit belongs to one of them or starts a new one." That eliminates a thin section.

### Section 11: Terminations and status flags

- **Necessary:** yes; the termination taxonomy is core to the schema.
- **Bullets-to-prose:**
  - 11.1 (Substance over form): **already prose.** Good. Could be shortened — the long title-list could collapse to "regardless of how the document is titled" without enumerating example titles, since Section 2 already enumerates them.
  - 11.2 (Status flags): **keep bullets** (11 distinct flags, classification reference).
  - 11.3 (Negotiated termination payments): **already prose.** Good. The trailing "The legacy status flag `cap_and_release` was renamed to `negotiated-termination-payment`" sentence belongs in Section 14 (vocabulary discipline) with the other rename notes; move it.
  - 11.4 (What is NOT a termination signal): **tossup.** Three bullets that could collapse to one prose paragraph, but the bullets work as a "do not flag these" checklist. Keep bullets if you value the checklist shape; collapse if you want the file tighter.
- **Other:** fix the ETP instance in 11.3 (cross-cutting note 1). Consider whether "Section 4.01" needs explanation (cross-cutting note 4).

### Section 12: Date attribution

- **Necessary:** yes; the date rules prevent silently wrong attributions that would cascade through the timelines.
- **Bullets-to-prose:**
  - 12.1: **keep numbered** (cascade order matters).
  - 12.2: **already prose.** Good.
  - 12.3: **keep numbered** (priority order matters).
- **Other:** the closing "Do not infer dates from the accession-number prefix" sentence is load-bearing — keep it.

### Section 13: Source filing vs announcement filing

- **Necessary:** yes; the source-vs-announcement distinction is real and the cross-reference convention prevents pointing at the wrong filing.
- **Bullets-to-prose:** **collapse to prose.** The two bullets are short definitions that read fine as one paragraph: "When an amendment, restatement, or termination is announced in an 8-K but the document text first appears in a later filing, record the announcement filing as a cross-reference (`Announced in [accession] dated [date]; document text filed with [source-filing accession]`) and cite the source filing as the contract source. This avoids pointing at an 8-K that summarizes the contract without containing the text."
- **Other:** none.

### Section 14: Vocabulary discipline

- **Necessary:** yes; the banned-phrasings list is project policy and needs a canonical location.
- **Bullets-to-prose:** **keep bullets.** Rules + reasons format reads naturally as a list.
- **Other:** fix the two ETP instances in the cap-and-release sub-bullets (cross-cutting note 1). After the ETP / instrument / TRA-class / cap-and-release sweep stabilizes, this section might want a "see also" line pointing at the wider banned-vocabulary memory in `~/.claude/`.

### Section 15: Form types relevant to TRA discovery

- **Necessary:** yes; the form-type inventory is reference material the download skill and the reading agent both consult.
- **Bullets-to-prose:** **keep bullets.** Reference list scanned by form type.
- **Other:** fix the `**424B**\*` escaping artifact (cross-cutting note 7). Closing paragraph naming the 8-K as the load-bearing form is good — keep.

### Section 16: Acquirer cross-check

- **Necessary:** yes; the four-step procedure handles the otherwise-easy-to-miss case where a TRA's fate is determined under a different CIK.
- **Bullets-to-prose:** **keep as a numbered list.** Procedure steps, ordered.
- **Other:** none.

### Section 17: Redactions

- **Necessary:** yes; redactions are a real and recurring case (Evo Payments example).
- **Bullets-to-prose:** n/a (already prose).
- **Other:** none.

### Section 18: Coverage gaps

- **Necessary:** yes; the "honest gap > inferred conclusion" rule is project policy.
- **Bullets-to-prose:** **collapse to one prose paragraph.** Current intro + 3-bullet list + closing paragraph can be: "When a firm has a known TRA-impacting event (Chapter 11 petition, M&A close, dissolution, Form 15 deregistration) but the filings post-dating that event are absent from the directory, record an explicit Coverage gap entry listing the event date, the expected missing filings (Form 15 deregistration, plan-confirmation 8-K, post-merger Form 25, etc.), and the authoritative source if known (Kroll / Epiq / KCC bankruptcy docket URL; merger agreement under the acquirer's CIK). Do not infer the TRA's fate from absence of evidence — an honest coverage-gap note is preferred to an inferred 'terminated' without a citation."
- **Other:** none.

### Source skills section

- **Necessary:** no. Remove per cross-cutting note 1. Git history captures provenance, and once this file is canonical the relationship reverses (skills reference it, not the other way around).

---

## Summary

**High-value edits** (these would close visible gaps in the current draft):

1. Apply the agreed removals: Source skills section, "Expect zero TRA directories" lines (Section 7), Section 10 differentiator-slug paragraph, remaining "operative" instances, remaining "ETP" instances.
2. Fix the Valuation Assumptions typo and decide whether to expand or remove that entry.
3. Decide on TRA Repurchase partial-vs-complete propagation (Section 2 → Section 11).
4. Decide on Section 4.01 — either gloss it once in Section 3 or drop the cite.

**Tightening edits** (optional, would shorten the file by ~40 lines):

5. Collapse Section 9.3 into the end of 9.2.
6. Consider folding Section 10 into Section 9.
7. Collapse Section 13 bullets into prose.
8. Collapse Section 18 bullets into prose.

**Mechanical / cosmetic:**

9. Normalize the long `------------------------------------------------------------------------` dividers back to `---`.
10. Fix the `**424B**\*` escaping in Section 15.
11. Move the `cap_and_release` rename note from Section 11.3 to Section 14.
