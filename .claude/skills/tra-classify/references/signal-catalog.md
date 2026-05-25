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

<!-- Append v2 section here when iteration produces a new accepted version. Do not edit v1 once shipped. -->
