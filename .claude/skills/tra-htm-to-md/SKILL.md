---
name: tra-htm-to-md
description: >-
  Convert a directory of SEC EDGAR Tax-Receivable-Agreement HTML files
  into clean markdown. Two-pass pipeline: pandoc first-pass, then an
  LLM cleanup pass that strips an enumerated set of recurring SEC-HTML
  artifacts (exhibit metadata blocks, raw HTML table passthrough,
  page-break markers, backslash-escaped punctuation, empty span
  anchors and stray <u> tags, atomized paragraph fragments, NBSP
  filler lines, residual <br> tags). Produces a `.md` companion
  alongside each `.htm` and optionally a `terms-summary.md` per TRA
  capturing the four standard contractual term definitions (tax-asset
  type, sharing ratio, early-termination valuation assumptions,
  default interest rate).
allowed-tools: Read, Write, Edit, Bash
---

# TRA HTML-to-Markdown converter

## Purpose

Given a directory containing one or more SEC EDGAR `.htm` / `.html`
exhibit files (typically TRA contracts and their amendments), produce
a clean `.md` markdown companion alongside each HTML file. The
markdown is the human-readable representation downstream tools (TRA
summary builders, terms extractors, dashboards) will read; the HTML
remains the canonical source and is never modified or deleted.

The skill optionally also produces a structured `terms-summary.md`
per TRA capturing four contractual definitions that recur across
nearly every TRA: the tax-asset type, the sharing ratio, the
early-termination valuation assumptions (discount rate plus the
assumption set), and the default interest rate.

## Workflow

### Step 1: Find source and target directories

Inputs: a source directory containing `.htm` / `.html` files. The
target directory is the same as the source directory by default; the
markdown is written next to each HTML file.

Resolve the source directory from the caller (typical invocation
passes a path like `<project root>/TRA-contracts/<firm>/TRA-<date>/`).
Enumerate every `.htm` and `.html` file directly inside the source
directory (do not recurse; each `TRA-<date>/` folder is flat).

For every HTML file, the target markdown filename is `<stem>.md`,
written next to the source. If a `<stem>.md` already exists, do not
overwrite it without an explicit `--force` flag from the caller.

Verify the source directory exists and carries at least one HTML
file before continuing. Fail loudly with the source path in the
error if the directory is empty.

### Step 2: HTML preprocessing

Run the BeautifulSoup-based preprocessor at
`.claude/skills/tra-htm-to-md/scripts/preprocess_html.py`. The passes
run in this order:

1. **Pre-parse normalization.** Strip EDGAR SGML metadata (`<TYPE>`,
   `<SEQUENCE>`, `<FILENAME>`, `<DESCRIPTION>`, `<TEXT>`) that
   prefixes the actual HTML document. Substitute every unclosed
   `<p Style='page-break-before:always'>` (Sculptor-pattern marker
   that, left in place, makes BS4 parse subsequent content as
   deeply-nested children) with `<hr>` — preserves intent and
   lets the existing `<hr>` signal detector pick it up downstream.
2. **Consolidate title block.** Collapse the leading run of
   consecutive centered paragraphs (exhibit identifier, contract
   title, parties, date) into a single `<h1>` heading plus a
   subtitle `<p>` joined by ` · `. Filters connector-only fragments
   (`among`, `between`, `by and among`, ...) and dedup principal-
   title substrings. Trails the subtitle with `.` so the downstream
   page-break merger doesn't absorb the next paragraph into it.
3. **Promote centered standalone section headers.** Standalone
   centered short ALL-CAPS paragraphs (`RECITALS`, `WITNESSETH`,
   `SIGNATURES`) become `<h2>`. Skips ARTICLE marker followed by
   title so the ARTICLE merger still works.
4. **Normalize content `<div>`s to `<p>`.** SEC HTML that wraps
   every content block in `<div>` (Dutch-Bros pattern) is rewritten
   so heading promotion, page-break detection, and paragraph
   merging can see the content. Page-break `<div>`s (which contain
   inner block elements) survive this step.
5. **Merge paragraphs split across page breaks.** Walk every
   page-break signal in document order; for each, find the
   substantive `<p>` immediately preceding and following (crosses
   `<div>` boundaries via `previous_element`/`next_element`). If
   the preceding doesn't end in sentence-terminating punctuation,
   splice them. Iterates until stable. Recognized signals: `<hr>`,
   `<a name="PB_*">`, `<br style="page-break-...">`, integer or
   roman-numeral page-number `<p>` (`9`, `-9-`, `iv`, `-iv-`), and
   `<div>` with CSS `break-before:page`, `page-break-before:`, or
   `border-bottom: ... solid` (modern SEC pattern in wm-technology
   etc.).
6. **Strip visual styling.** `<font>` tags unwrapped; `style` and
   `class` attributes stripped from `<span>` / `<div>` outside
   tables. Runs AFTER the merge so CSS page-break signals are
   intact at merge time.
7. **Strip page-break artifacts.** Remove `<a name="PB_*">`,
   `<hr>`, integer/roman-numeral page-number `<p>`, recurring TOC
   backlinks.
8. **Promote bolded ARTICLE / SECTION / SCHEDULE / EXHIBIT
   paragraphs to `<h2>` / `<h3>` headings** with stable id
   attributes. Handles one-line, two-line, and three-line
   constructions; splits SECTION paragraphs that combine heading
   and body in one `<p>` into `<h3>` + sibling body `<p>`.
9. **Promote inline ARTICLE markers.** Walk `<b>` and `<strong>`
   tags directly; if the text matches an ARTICLE pattern, promote
   to `<h2>` in-place. Catches malformed-source cases (Sculptor)
   where ARTICLE markers float outside any well-formed wrapper.
   Consumes a next-sibling emphasis tag as the heading title if
   it's an all-caps short phrase.
10. **Strip layout-only tables.** TOC tables (by anchor links OR
    by Article/Section refs + page-number cells), signature blocks
    (converted to plain paragraphs), single-clause indent wrappers,
    decorative shims, and page-number tables.

Invocation:

```
python .claude/skills/tra-htm-to-md/scripts/preprocess_html.py \
  <input.htm> --output <input.preprocessed.htm>
```

### Step 3: Pandoc conversion

Run pandoc against the preprocessed HTML:

```
pandoc --from=html --to=markdown --wrap=none \
  <input.preprocessed.htm> -o <input.pandoc.md>
```

Notes on the flags:

- `--to=markdown` (pandoc's extended dialect, not
  `markdown_strict`) emits `# Heading {#anchor}` attribute syntax
  that Quarto and Positron's visual editor render as real
  headings with stable anchor targets. It also supports definition
  lists (`Term\n:   body`), which the polish step in Step 4 uses.
- `--wrap=none` puts each paragraph on a single line. This makes
  the definition-list regex (which matches paragraphs starting with
  `"[Term]{.underline}"` or `"**Term**"`) line-anchored and
  reliable.
- The source HTML is the canonical record; the `.preprocessed.htm`
  and `.pandoc.md` are intermediates. The final `.md` (Step 4
  output) lives next to the source HTML.

### Step 4: Polish (deflist, references, Quarto frontmatter)

Run the polish script at
`.claude/skills/tra-htm-to-md/scripts/clean_and_link.py` against
the pandoc output:

```
python .claude/skills/tra-htm-to-md/scripts/clean_and_link.py \
  <input.pandoc.md> --output <input.md>
```

The polish script does five things:

1. **Residual cleanup.** Drops stray `<div>` / `</div>` tags pandoc
   passed through verbatim, strips pandoc fenced div lines
   (`:::` and `::: {align="left"}` from `<div align="left">`
   wrappers in source HTML), drops empty-bold `** **` lines,
   un-escapes pandoc's load-bearing-free punctuation escapes
   (`\$`, `\#`, `\&`, `\<`, `\>`), drops standalone `\` hard-line-
   break markers, strips orphan leading `. ` from paragraphs that
   begin `. <Capital>` (residual from section-paragraph splitter),
   and collapses runs of blank lines to a single blank.
2. **Strip table of contents.** Removes `## TABLE OF CONTENTS` /
   `## CONTENTS` heading plus content until the next heading.
   Also strips standalone pandoc dash-grid tables whose contents
   include 3+ ARTICLE / Section / EXHIBIT / SCHEDULE references
   (catches link-less ToCs). Preserves substantive dash-grid
   tables (defined-term indices using `§`, joinder clauses,
   schedule formats).
3. **Definition-list conversion.** Find the Definitions section
   by locating any `## ARTICLE N:` heading whose title contains
   "Definitions" (falls back to `#article-i`). Within that
   region, every paragraph matching one of four term-form
   alternations becomes a deflist entry:

   - Underlined term, accepting all four quote placements:
     `"[Term]{.underline}"`, `["Term]{.underline}"`,
     `"[Term"]{.underline}`, `["Term"]{.underline}`
   - Bold-quoted: `"**Term**"`
   - Plain-quoted: `"Term"`
   - Article-prefixed: `A "Term"`, `An "Term"`, `The "Term"`

   Each alternation allows an optional `:` between the closing
   quote and the body (handles `"Term": body` form). The term is
   normalized: stripped of quotes, `**...**`/`*...*` bold/italic
   markers, and `[...]{.underline}` spans. Pandoc empty inline
   anchors (`[]{#anchor-id}`) are stripped before matching.
   Paragraphs inside the Definitions region that are not deflist
   entries get 4-space indentation so they nest as continuations
   of the previous definition.

   Example output:

   ```markdown
   Accounting Firm
   :   means, as of any time, the accounting firm that prepares the
       Federal income Tax Returns of Vantiv.
   ```

4. **Section-reference linking.** Builds the anchor set from
   `{#anchor}` heading attributes. Walks every `[text]{.underline}`
   span and every plain-text `Section X.YZ` / `Article III` /
   `Schedule A` / `Exhibit B` pattern; if the target anchor
   exists, replaces with a markdown link `[text](#anchor)`.
   Defined-term emphasis spans whose inner text does not match a
   reference pattern are stripped to plain text.
5. **Quarto YAML frontmatter prepend.** Adds a minimal frontmatter
   block enabling auto-TOC:

   ```yaml
   ---
   title: "TAX RECEIVABLE AGREEMENT"
   format:
     html:
       toc: true
       toc-depth: 3
       toc-location: left
   ---
   ```

   The title is auto-detected from the first bolded contract-title
   line in the body.

The polish script supports `--in-place` to rewrite the input.

#### Linking scope and known gaps

- **Underline-wrapped single references** are linked end-to-end
  (the common form in Appreciate, Charter, Clearwater).
- **Plain-text cross-references** are linked via a regex scan with
  the anchor-existence filter, so contracts that do not underline
  cross-references (Worldpay, Blackstone, Galaxy, Wayne Farms, Eve)
  also get internal navigation.
- **Compound references** like `Sections 2.01 and 2.02` are
  linked individually (each component matches the single-ref
  pattern in turn).
- **Deep-subsection anchors.** `Section 2.01(c)(ii)` links to the
  section-level anchor `#section-2-01`; the `(c)(ii)` sub-anchor
  is not generated.
- **Cross-document references** (`Section 5(a) of the Exchange
  Agreement`) are not mis-linked: the anchor-existence filter
  rejects them because no matching internal anchor exists.

#### What the deterministic pipeline does not handle

- **Substantive-table conversion.** Schedule A notices, Exhibit
  A Exchange Basis, Exhibit B Tax Schedule remain as pandoc-
  emitted markdown (pipe tables or raw `<table>` blocks depending
  on shape). An optional later pass can convert them to consistent
  pipe-table form.
- **Mid-paragraph rejoining.** When pandoc's `--wrap=none` is
  used (the recommendation here), every paragraph is one line and
  this is a non-issue. If the caller wants a different wrap
  setting, the polish script does not re-join paragraphs.

### Preservation contract

The cleanup must preserve all substantive contract content
verbatim. Do not summarize, paraphrase, or omit clauses,
definitions, schedules, or exhibits. The cleaned markdown should
contain the same legal text as the source HTML, with the artifacts
above removed and the structural headings normalized.

When the source HTML carries an exhibit whose body is shown only
as a placeholder ("[Draft Loan Agreement attached separately]"),
leave that placeholder in the cleaned markdown rather than
fabricating content.

### Output structure

The cleaned `.md` should follow this top-level structure when the
underlying contract is a full executed TRA:

1. Exhibit number and title (bolded).
2. Parties paragraph (`This TAX RECEIVABLE AGREEMENT...`).
3. WHEREAS recitals.
4. NOW, THEREFORE clause.
5. Article-level `#` headings, with section-level `**SECTION X.Y**` bolded labels.
6. Signature section.
7. Schedule A (notices) and each Exhibit, each as its own `#` heading.

For amendments and addenda, the structure is shorter (one or two
articles, parties, signatures) and the same cleanup rules apply.

## Optional: terms-summary.md

When the contract states identifiable terms for the four standard
TRA definitions, produce a `terms-summary.md` in the same directory.
Definitions to track:

1. **Tax asset type.** Basis Step-Up (Section 743(b) / 754 of the
   Code; or Sections 732/1012 in disregarded-entity cases), NOL
   (net operating loss carryforward), Other tax credit, or a
   comma-separated subset.
2. **Sharing ratio.** The percentage of Realized Tax Benefits the
   corporate taxpayer pays to the TRA counterparties (commonly 85%,
   sometimes a compound rate).
3. **Early-termination calculation (valuation assumptions).** The
   discount rate used to present-value remaining Tax Benefit Payments
   plus the assumption set the calculation rests on (future taxable
   income assumed sufficient to use deductions; rate regime;
   treatment of loss carryovers and non-amortizable assets; treatment
   of unexchanged units).
4. **Default interest rate.** The rate charged on late Vantiv-style
   payments, typically LIBOR plus a basis-point premium or Prime
   plus a basis-point premium.

Use this terse template. Each value is a short phrase. Longer text
(definitions, full valuation-assumption paragraphs, citations) lives
in the contract itself; the terms-summary is a reference card.

```markdown
# Terms summary: <TRA name>

Tax Asset Type: <Basis Step-Up, NOLs, Other tax credit, or comma-separated subset>
Sharing Ratio: <e.g. 85%>
Early Termination Assumptions:
  - Discount Rate: <e.g. LIBOR + 100bps, Applicable Treasury Rate, SOFR + 200bps>
  - Taxable Income: <one short phrase, e.g. "Sufficient to use all tax assets">
  - Tax Asset Schedule:
     - NOLs: <one phrase, e.g. "Utilized pro-rata between early termination date and expiration">
     - Basis Step-Up: <one phrase, e.g. "Immediately utilizable">
  - Remaining Exchanges: <one phrase, e.g. "Treated as exchanged on termination date">
Default Interest Rate: <e.g. LIBOR + 500bps, Prime + 200bps>

Other terms (non-standard, if any):
  - <Term label>: <short phrase>

Amendments and Restatements (if any):
  - A&R <n> (YYYY-MM-DD): <which term changed and the new short value>
```

Style rules:

- Each value should be one short phrase, ideally under 15 words.
  Cross-reference back to the contract for the verbatim text.
- Drop sub-bullets under `Tax Asset Schedule` that do not apply
  (e.g. omit the `NOLs:` line if the contract is Basis-Step-Up
  only). Do not write `<not applicable>` for missing tax-asset
  subtypes.
- For terms the contract does not state, write `<not stated>`
  as the value rather than omitting the line.
- `Other terms (non-standard, if any):` is a free-form slot for
  payment-structure or threshold features the four standard
  definitions do not cover (e.g. a one-time closing payment plus
  contingent post-year payments, a "Deductible" threshold like
  Expro's $18,057,000, a payment cap, an exchange-vesting condition).
  Omit the block entirely if the contract has no such features.
- For Amended and Restated versions, append one bullet under
  `Amendments and Restatements` per A&R, citing which of the
  top-level terms changed and the new short value. Original
  definitions stay in the top-level keys; only delta is captured
  in each A&R bullet.

## Worked example

See `references/`:

- `example.htm`: source HTML of the Vantiv-Fifth Third TRA dated March 21, 2012 (`worldpay-inc_0001533932/TRA-2012-03-21-fifthThird/2012-05-08_executed_ex-10.6.htm`).
- `example.preprocessed.htm`: output of the BeautifulSoup preprocessor.
- `example.pandoc.md`: pandoc first-pass output (`--to=markdown --wrap=none`) against the preprocessed HTML.
- `example.final.md`: polished markdown after definition-list conversion, reference linking, and YAML frontmatter prepend.
- `example_terms_summary.md`: the structured terms-summary for the same TRA.

## Invariants and constraints

- The HTML files are read-only. The skill never modifies or deletes
  any `.htm` / `.html` source.
- The skill writes `.md` files only. If a target `.md` already
  exists, the caller must pass `--force` to overwrite.
- Pandoc is invoked via the bare `pandoc` binary (pandoc 3.1.3 on
  the development environment); pixi need not be involved unless
  the caller wires it in.
- All paths in the cleanup pass are relative; the skill is
  relocatable across machines.
