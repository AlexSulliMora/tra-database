# tra-classify Signal Catalog

Per-version documentation of the deterministic signals the classifier scores and the rule it applies to combine them into `yes` / `no` / `uncertain`. **Versioned with the classifier.** When `--classifier-version` changes, this file documents what changed. Each version's section is immutable once an iteration ships; new versions append below.

The signals here are the only inputs to `--mode classify`. A4 (`--mode review-uncertain`) sees the document plus this catalog so it knows what the deterministic layer already checked.

---

## v1 — initial signal set (2026-05-24)

### Signals

#### S1. Centered title contains "TAX RECEIVABLE AGREEMENT"

The strongest signal. Real TRAs open with a centered title block carrying the phrase. The detector handles two centering mechanisms:

- **Inline style** — `<p align="center">`, `<div style="text-align: center">`, `<center>` tags wrapping the title text.
- **CSS class** — a `class` attribute on the title element matching common centering class names (`.center`, `.centered`, `.title-center`, `.text-center`, `.ta-center`, plus any class whose name contains `center` substring) where the class definition contains `text-align:center` in any `<style>` block in the document head.

Case-insensitive on the phrase. The detector reads only the leading title window (~80 KB).

Signal name: `centered_title`.

#### S2. Any of the four phrase variants present

The full-text search uses four variants (origin: prior session's `find_candidates.py`):
- `tax receivable agreement`
- `tax receivable agreements`
- `tax receivables agreement`
- `tax receivables agreements`

Any match in the scan window (~400 KB) sets this signal. **Critical:** prior attempts used only the singular `tax\s+receivable\s+agreement`, missing the two `receivables` variants and silently mis-classifying those documents. v1 covers all four.

Signal name: `phrase`.

#### S3. Defined-term presence (each named individually)

TRA-specific defined terms that corroborate the contract is a TRA rather than a document that mentions one. Each match emits its own signal:

| Term regex (case-insensitive) | Signal name |
|---|---|
| `realized\s+tax\s+benefit` | `defined_term_realized_tax_benefit` |
| `hypothetical\s+tax\s+liability` | `defined_term_hypothetical_tax_liability` |
| `exchange\s+basis\s+(?:schedule|adjustment)` | `defined_term_exchange_basis` |
| `tax\s+benefit\s+schedule` | `defined_term_tax_benefit_schedule` |
| `early\s+termination\s+payment` | `defined_term_early_termination_payment` |
| `net\s+tax\s+benefit\s+payment` | `defined_term_net_tax_benefit_payment` |
| `basis\s+adjustment` | `defined_term_basis_adjustment` |
| `tax\s+asset(?:s)?` | `defined_term_tax_asset` |
| `section\s+754\s+election` | `defined_term_section_754` |

Each match contributes one signal. Scanned within the ~400 KB scan window. Multiple matches strengthen corroboration; the classification rule (below) requires at least one for the "phrase + corroboration" yes path.

#### S4. Forced-uncertain override

Documents listed in `data/edgar-query/forced_uncertain.csv` keyed on `(cik, accession, filename)` are routed to `classification=uncertain` regardless of any other signal. The CSV is initially empty (header only). It populates when the user identifies a document that the deterministic signals cannot resolve correctly and the user wants A4 (and ultimately A1) to decide rather than the classifier guessing.

Signal name: `forced_uncertain` (and in this case, no other signals are scored — the override short-circuits).

### Classification rule (v1)

Applied in order; first match wins:

1. **Forced uncertain.** `(cik, accession, filename) ∈ forced_uncertain.csv` → `classification=uncertain`, `signals_matched=forced_uncertain`.
2. **PDF (no text extraction).** Extension `.pdf` → `classification=uncertain`, `signals_matched=pdf_no_text`.
3. **Strong yes.** `centered_title` matches → `classification=yes`, `signals_matched=centered_title` (+ any other matched signals appended for audit).
4. **Phrase + corroboration → yes.** `phrase` matches AND at least one `defined_term_*` matches → `classification=yes`, `signals_matched=phrase|<defined_term_*>...`.
5. **Phrase without corroboration → uncertain.** `phrase` matches but no `defined_term_*` → `classification=uncertain`, `signals_matched=phrase`. (Common case: documents that mention a TRA, e.g., LLC agreements or credit agreements; A4 reads the body to decide.)
6. **No phrase, no signals → no.** Neither `phrase` nor any `defined_term_*` matches → `classification=no`, `signals_matched` empty.

### Rationale

- **S1 carries most of the discrimination.** In the prior session's reference set (5 confirmed TRAs vs. 18 random EX-10 contrast files), every TRA had S1 and no contrast file did. The signal is cheap (bounded title-window read) and dominant.
- **S2 alone is insufficient** — the discriminative-failure-mode the v0 was rejected for. v1 keeps S2 but only as a corroboration-required signal (rule 5).
- **S3 acts as a corroboration tier.** Defined terms appear in real TRAs and rarely in mention-only documents. Multiple matches strengthen the call.
- **S4 is the escape hatch.** When the signal logic can't resolve a hard case (an amendment that incorporates the original TRA verbatim, a non-TRA tax-asset transfer agreement that reads similarly), the user adds the document to `forced_uncertain.csv` and A4 handles it. **Governance**: see the plan's `## Deferred / Open Questions` for the budget cap and reason-field policy to apply when this list grows.

### Known limitations (carried forward to v2)

- **CSS-class centering with multiple cascade levels.** A document where the centered title uses a class defined in an external stylesheet (not inline `<style>`) is missed by S1. The pull_exhibits.py output is self-contained per filing, but a few filings may reference external CSS not in the on-disk copy. Workaround: such documents fall through to S2/S3 logic, which usually catches the TRA via corroboration.
- **Signature-block heuristic not yet implemented.** v1 omitted this; can add as v2 if iteration reveals it would discriminate. The prior classifier didn't use it either.
- **File-size bounds not used.** The prior classifier dropped tiny / huge files combined with negative signals. v1 doesn't — every document is signal-scored regardless of size, since the bounded reads already prevent runaway memory use and a tiny TRA amendment is a legitimate yes.

---

## v2 — title-band S1 + rule-4 demotion (2026-05-24)

### Changes from v1

Two structural changes driven by F2 round 1 spot-checks against the A4 reviewer:

1. **S1 (`centered_title`) tightened to "title-band only".** v1 returned True if any centered `<p>`/`<div>`/`<h*>`/`<span>`/`<center>` block in the leading ~80 KB contained the phrase "TAX RECEIVABLE AGREEMENT". v2 returns True only if some non-empty centered block within the leading `TITLE_BAND_BYTES = 5000` of the document contains the phrase. Documents whose document title is something else (Tax Matters Agreement, LLC Agreement, Purchase Agreement) but that name TRAs in centered subsection headings or defined-term blocks far past the title block are now correctly rejected. Empty centered blocks (SEC HTML's `<p style="text-align:center">&nbsp;</p>` spacers) are skipped — they carry no title text to test against.

   Worked example: an EX-10.1 spin-off Tax Matters Agreement (McKesson/SpinCo/Change Healthcare, `data/edgar-query/exhibits/0000927653/0001193125-20-072880_d846210dex101.htm`) opens with a centered "Exhibit 10.1 Execution Version TAX MATTERS AGREEMENT" header in the first 200 bytes, then later (byte ~69 026) has a centered `<P>` block defining "Tax Receivable Agreements" as a parties' term. v1 matched the byte-69 026 block and emitted `yes`; v2 finds no TRA-phrase centered block within the first 5000 bytes and correctly emits no-S1 (the document falls through to rule 5 → uncertain → A4).

   Why the band rather than "first non-empty centered block": real TRAs commonly have a centered company name, "FORM OF", or "EXHIBIT B" preamble preceding the centered "TAX RECEIVABLE AGREEMENT" title block. A "first non-empty centered block" rule wrongly rejected those (e.g., Silvercrest TRA opens with centered "SILVERCREST ASSET MANAGEMENT GROUP INC." at offset 511, then centered "TAX RECEIVABLE AGREEMENT" at offset 681). The 5000-byte band covers preamble + title + parties + date without reaching body text or defined-term sections.

2. **Rule 4 (`phrase + ≥1 defined_term → yes`) demoted to `uncertain`.** F2 round 1 spot-check on 8 rule-4 hits: 8/8 were false positives (LLC agreements of Up-C operating partnerships, Tax Matters Agreements that allocate TRA payments in spin-off contexts, M&A Purchase Agreements that assume TRA liabilities — all carry TRA defined terms naturally because they live in or near the Up-C structure but are not themselves TRA contracts). Rule 4 produces no `yes` in v2; phrase + defined_term routes to `uncertain` and A4 decides.

### Signals (unchanged from v1)

S2 (phrase variants), S3 (defined-term signals), and S4 (forced-uncertain override) are unchanged. The signal names and regexes carry over verbatim; only S1's resolution rule and rule 4's verdict change.

### Classification rule (v2)

Applied in order; first match wins:

1. **Forced uncertain.** `(cik, accession, filename) ∈ forced_uncertain.csv` → `classification=uncertain`, `signals_matched=forced_uncertain`.
2. **PDF (no text extraction).** Extension `.pdf` → `classification=uncertain`, `signals_matched=pdf_no_text`.
3. **Strong yes.** v2 `centered_title` (first centered block in title window contains the TRA phrase) → `classification=yes`, `signals_matched=centered_title` (+ any other matched signals appended for audit).
4. **Phrase + corroboration → uncertain.** `phrase` matches AND at least one `defined_term_*` matches → `classification=uncertain`, `signals_matched=phrase|<defined_term_*>...`. (CHANGED from v1's `yes`.)
5. **Phrase without corroboration → uncertain.** `phrase` matches but no `defined_term_*` → `classification=uncertain`, `signals_matched=phrase`.
6. **No phrase, no signals → no.** Neither `phrase` nor any `defined_term_*` matches → `classification=no`, `signals_matched` empty.

### Expected effect on the 3025-document corpus

v1 classify produced: yes=1292 (933 from S1, 359 from rule 4) / uncertain=1298 / no=435.

v2 classify is expected to produce roughly: yes=N (only S1 hits, where N ≤ 933 because the first-centered-block tightening may exclude some prior S1 hits), uncertain=~1298 + 359 + (933 - N), no=435.

A4 will review the ~1657 uncertain rows in F2 round 1. The 359 ex-rule-4 docs are the most-likely false-positive bucket and benefit most from A4 review.

### Rationale

- **S1 over-matched because the regex is window-scoped, not title-scoped.** A real TRA's title block is always near byte 0; later centered blocks inside an 80 KB window are typically defined-term blocks, article headings, or signature pages. Restricting S1 to the *first* centered block aligns the signal with the discriminating property ("the document's title is 'TAX RECEIVABLE AGREEMENT'") rather than a weaker property ("the document contains a centered block mentioning the phrase").
- **Rule 4 conflated "is a TRA" with "lives near a TRA".** The Up-C structure that TRAs depend on involves a constellation of contracts (LLC agreement of the operating partnership, registration-rights agreement, exchange agreement, the TRA itself). All of them carry TRA defined terms in their bodies — `basis_adjustment` and `section_754_election` because the LLC makes the election, `tax_asset` because each contract allocates rights to it. Phrase + defined_term is therefore expected in non-TRA contracts that participate in the Up-C scheme. Demoting rule 4 to A4 review eliminates the false-positive category at the cost of more A4 calls.

### Known limitations (carried forward to v3 if needed)

- **Documents whose first centered block is "FORM OF" or "EXECUTION VERSION" preamble may slip through.** No examples observed in the 8-document rule-4 sample or 5-document centered_title sample, but plausibly exist. If F2 round 1 surfaces them, v3 could skip a small fixed set of preamble strings before locating the title block.
- **All other v1 limitations carry forward** (CSS centering with external stylesheets, no signature-block heuristic, no file-size bounds).

---

<!-- Append v3 section here when iteration produces a new accepted version. Do not edit v1 or v2 once shipped. -->
