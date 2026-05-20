---
name: TRA-classify
description: >-
  Filter a directory of SEC EX-10.* exhibits down to documents that plausibly
  ARE Tax Receivable Agreements (TRAs), so a human only manually reviews a
  small keep-list instead of the full haystack. Recursively finds every .htm
  file, drops the ones confidently not a TRA, and writes the survivors to a
  CSV. Conservative by design: favors recall, because a false drop discards a
  real TRA while a false keep just adds one file to the review pile. Use after
  an EDGAR full-text-search pull of EX-10 material-contract exhibits, when the
  next step is narrowing thousands of contracts to the TRA candidates.
---

# TRA-classify

## What this skill does

SEC full-text search for "tax receivable agreement" returns the EX-10.*
material-contracts exhibit class. Most of those exhibits are employment
agreements, credit agreements, leases, incentive plans, and LLC agreements;
only a minority are actual TRAs. This skill takes a source directory of such
exhibits, recursively finds every `.htm` file, and classifies each as:

- **drop**: confidently not a TRA.
- **keep**: needs a human to confirm.

It writes the keep-list to a CSV and prints a summary (total found, dropped,
kept). On the project's 15,035-exhibit corpus it cuts the manual-review pile
to roughly 1,800 files (about 88% dropped) with zero false drops on a
5-TRA reference set.

## When to use it

Use it right after `tra-download-filings` / an EDGAR full-text-search pull
has deposited EX-10 exhibits under `<CIK>/*.htm`, and before any
contract-by-contract classification step (`tra-process-filings`). It is a
cheap recall-oriented pre-filter, not a final classifier: every kept file
still needs a human (or `tra-process-filings`) to confirm.

## How to run it

```bash
pixi run -- python scripts/classify_tras.py <source_dir> \
    -o <keeplist.csv> [--drop-csv <droplist.csv>]
```

- `<source_dir>`: searched recursively for `*.htm`.
- `-o / --output`: keep-list CSV (default `tra_keeplist.csv` next to the
  skill folder).
- `--drop-csv`: optional CSV of dropped files, for auditing false drops.

The keep-list CSV carries one row per kept file with the computed signal
columns (`size_bytes`, `title_block`, `title_has_tra`, `title_is_non_tra`,
`phrase_present`, `income_tra_phrase`, `tra_term_count`, `decision`,
`reason`), so a reviewer can sort by signal strength.

Runtime is roughly 5-6 minutes for 15,000 files (single process,
bounded reads).

## The signals it uses

Learned from 5 confirmed reference TRAs (loanDepot, Zevia, Ranger Energy,
Blackstone, Tradeweb) contrasted against an 18-file random EX-10 sample
(credit agreements, an employment separation letter, RSU/incentive plans,
an indemnification agreement, a clearing-services agreement, a support
agreement, LLC operating agreements, an exchange agreement).

1. **Centered title block (strongest signal).** A contract opens with a run
   of centered lines (the SEC exhibit identifier, the document title, the
   parties, the date) ending at the first long left-aligned paragraph (the
   preamble). A TRA's centered title block contains the phrase
   "TAX RECEIVABLE AGREEMENT". Every reference TRA had this; no contrast-set
   file did. The skill parses the centered run with the same heuristic as
   `tra-htm-to-md/scripts/preprocess_html.py` (`consolidate_title_block`,
   `_is_centered`).
2. **Phrase presence.** "tax receivable agreement" anywhere in the document
   is a weaker cue: credit agreements, LLC agreements, and proxies mention
   a TRA without being one. Used as a keep-fallback when the centered title
   could not be parsed or the TRA is embedded in a larger filing.
3. **TRA-specific defined terminology.** "Realized Tax Benefit",
   "Hypothetical Tax Liability", "Exchange Basis Schedule", "Tax Benefit
   Schedule", "Early Termination Payment", "Section 754 Election", and
   similar (from `tra-process-filings/SKILL.md`, "What a Tax Receivable
   Agreement looks like"). Three or more present is a phrase-free keep.
4. **Disqualifying titles.** Centered titles naming a clearly different
   instrument (credit agreement, employment agreement, RSU/incentive plan,
   LLC/limited-partnership/operating agreement, exchange agreement,
   registration-rights / stockholders / voting / support / merger /
   purchase agreement, lease, note, warrant) drive a drop, but only when
   no TRA phrase appears anywhere.
5. **File-size bounds.** Tiny files (under 4 kB) with no TRA phrase are too
   short to be a full contract. Multi-megabyte files (over 1.2 MB) with no
   TRA phrase and no defining terms are large non-TRA filings (credit
   agreements, indentures, S-4s). Size never drives a drop on its own.

## Decision rules (in order)

For each `.htm` file:

1. Centered title contains "tax receivable agreement" -> **keep**.
2. Centered title names a non-TRA instrument AND no TRA phrase anywhere
   -> **drop**.
3. "tax receivable agreement" phrase present anywhere -> **keep**.
4. Three or more TRA-specific defined terms present -> **keep**.
5. File under 4 kB with no TRA phrase -> **drop**.
6. File over 1.2 MB with no TRA phrase and no terms -> **drop**.
7. Otherwise (no TRA title, phrase, or terminology) -> **drop**.

The phrase and term checks are placed before the size checks so a short
TRA amendment or waiver that mentions the phrase is never dropped on size.

## Why it favors recall

A false drop silently discards a real TRA, which is the costly error in a
corpus-building pipeline. A false keep just leaves one extra file for a
human to dismiss in seconds. Every drop rule therefore requires the
absence of all positive TRA signals; no single negative signal (a
non-TRA-looking title, an extreme file size) drops a file on its own.

The known false-keep population is Up-C-adjacent co-filings: LLC operating
agreements, exchange agreements, and credit agreements that reference a
company's TRA in passing. These are kept by rule 3 and discarded by the
human reviewer. That is the intended tradeoff.

## WSL safety

Large HTML files are never loaded fully into memory. The title check reads
only the leading 80 kB; the phrase / term scan reads at most the leading
400 kB. Files are size-checked via `stat` before any read.

## Validation results

- **5 reference TRAs**: 0 dropped (100% kept). Zero false drops.
- **18-file random non-TRA sample**: 14 dropped (78%). The 4 kept are an
  LLC limited-partnership agreement, a Bioventus LLC operating agreement, a
  Cornerstone credit-agreement amendment, and the Apollo Second Amended and
  Restated Exchange Agreement, all genuinely Up-C-adjacent documents that
  mention a TRA. Correct conservative keeps.
- **Full `data/edgar-query/exhibits/` corpus**: 15,035 `.htm` found,
  13,229 dropped, **1,806 kept** (88.0% reduction).

## Files

- `SKILL.md` (this file).
- `scripts/classify_tras.py`: the classifier. One command-line argument
  (the source directory), recursive `.htm` glob, per-file classification,
  CSV keep-list output, printed summary.
