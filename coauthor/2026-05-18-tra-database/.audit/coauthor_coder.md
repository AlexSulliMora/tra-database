
## 2026-05-18T20:15:25-07:00

**Tool**: Agent
**Session**: 1d894a68-8692-46c9-8093-c69c02b611af
**Agent ID**: 

### Prompt

Extract Tax Receivable Agreement (TRA) sections from 20 SEC HTML filings where the TRA is embedded inside a larger wrapper agreement (Business Combination Agreement, Merger Agreement, Investment Agreement, Equity Purchase Agreement, Purchase and Contribution Agreement, S-4, etc.). Deliverable: an extracted HTML file per input that contains ONLY the TRA section, plus a manifest summarizing what you did.

## Background

The user has a pipeline (`~/.claude/skills/tra-htm-to-md/scripts/preprocess_html.py` + pandoc + `clean_and_link.py`) that converts SEC TRA HTML to clean markdown. It works on standalone TRAs and on TRAs embedded in proxy filings with a TOC pointing to the TRA annex. For these 20 files, the wrapper agreement uses lettered Exhibits (Exhibit C/D/E/F) appended after the main agreement's `IN WITNESS WHEREOF` block, rather than a TOC-anchored annex, so the existing TOC-based extractor doesn't fire.

## The 20 files (paths relative to /home/sulli/research/tra/)

```
TRA-contracts/arya-sciences-acquisition-corp-iv_0001838821/TRA-2021-09-29/2021-09-29_form-of-TRA-as-BCA-Exhibit-C.htm
TRA-contracts/amicus-therapeutics-inc_0001178879/TRA-2021-09-29-form-of-unexecuted/2021-09-29_business-combination-agreement-with-form-of-tra.htm
TRA-contracts/federal-street-acquisition-corp_0001701821/TRA-2019-01-04/2018-08-14_form-of-TRA_in_ex-2.1.htm
TRA-contracts/fast-acquisition-corp-ii_0001839824/TRA-2022-07-12/2022-07-12_ea162701ex2-1_fastacq2_form-of-TRA-embedded-as-Exhibit-D.htm
TRA-contracts/genesis-healthcare-inc_0001351051/TRA-2015-02-02/2014-08-18_form-of-TRA-as-Exhibit-A-to-Purchase-and-Contribution-Agreement.htm
TRA-contracts/egh-acquisition-corp_0002052547/TRA-2026-01-21-form-of/2026-01-21_BCA-with-form-of-TRA-as-ExhibitC.htm
TRA-contracts/charter-communications-inc-mo_0001091667/TRA-2025-05-16-cox-form/2025-05-16_ef20049261_ex2-1.htm
TRA-contracts/easterly-acquisition-corp_0001641197/TRA-2017-06-28/2017-06-30_v470027_ex2-1_investment-agreement-with-form-of-TRA-as-Exhibit-D.htm
TRA-contracts/flyexclusive-inc_0001843973/TRA-2023-12-27/2022-10-18_form-of_in-EPA_d308193dex21.htm
TRA-contracts/evgo-inc_0001821159/TRA-2021-07-01/2021-01-25_form-of-in-BCA-ex2-1.htm
TRA-contracts/mudrick-capital-acquisition-corp-ii_0001820727/TRA-2021-04-06/2021-04-06_tm2112182d1_ex2-1_merger-agreement-with-form-of-TRA.htm
TRA-contracts/real-brokerage-inc_0001862461/TRA-2013-10-07/2026-04-26_amendment-no-1_within_merger-agreement_tm2612777d5_ex2-1.htm
TRA-contracts/nebula-acquisition-corp_0001720353/TRA-2020-06-10/2020-01-06_form-of-TRA-in-BCA-Exhibit-F.htm
TRA-contracts/highland-transcend-partners-i-corp_0001828817/TRA-2021-09-09/form-of-tra-amended-2021-10-22.htm
TRA-contracts/charter-communications-inc-mo_0001091667/TRA-prospective-gci-divestiture/2024-11-12_ny20038391x1_ex2-1.htm
TRA-contracts/sierra-income-corp_0001523526/TRA-2014-09-23-Medley/2019-07-29_amended-restated-termination-waiver-lockup-agreement_embedded-in-merger-agreement.htm
TRA-contracts/sierra-income-corp_0001523526/TRA-2014-09-23-Medley/2018-08-09_termination-waiver-lockup-agreement_embedded-in-merger-agreement.htm
TRA-contracts/digital-media-solutions-inc_0001725134/TRA-2020-07-15/2020-07-20_executed_ex-10.6_via_424b3.htm
TRA-contracts/alti-global-inc_0001838615/TRA-2023-01-03/2022-02-11_form-of-from-S4-annexE.html
TRA-contracts/aurora-diagnostics-holdings-llc_0001367832/TRA-2010-12-20-formof/2012-03-23_d280216dex102.htm
```

## What you already know

I scanned all 20 with grep. Findings:

**Confirmed centered+bold TAX RECEIVABLE AGREEMENT heading** (these are easy):
- `flyexclusive 2022 EPA`: line 9692 (FORM OF TAX RECEIVABLE AGREEMENT), 9703 (TAX RECEIVABLE AGREEMENT), file ends at 12369
- `digital-media-solutions executed 424b3`: line 8572, file ends at 28822; TRA IN WITNESS at line 9510 (mentions "TRA Holders")
- `aurora-diagnostics`: line 11053 (bold centered TAX RECEIVABLE AGREEMENT), file ends at 12466; TRA IN WITNESS at line 11671

**Special-case stub files** (very few lines but huge byte size; structure does not allow line-based extraction):
- `alti-global`: 10 lines total, 627KB. The TRA is wrapped in a `<pre>` block on a single line. Probably DO NOT line-extract; just leave it alone (or extract the `<pre>` content with a different approach).
- `genesis-healthcare`: 18 lines total, 1.9MB. SGML wrapper (DOCUMENT/TYPE/SEQUENCE/FILENAME) with one giant content line. Same — probably leave alone or treat specially.

**Duplicate** (same file copied to two TRA folders, identical content):
- `arya-sciences` and `amicus-therapeutics` are byte-identical (~2.2MB each, both 23090 lines). Extract once, copy result to both locations.

**Sierra-income special case**: the user clarified that these are "Termination Waiver Lockup Agreement" embedded in a merger agreement. The user wants the termination-waiver-lockup section extracted (the TRA's operative termination instrument). Look for the "Termination Waiver Lockup Agreement" heading or the "Termination of Tax Receivable Agreement" section.

For the remaining files (the bulk), the centered+bold heading regex I used was too narrow — most files DO have a TAX RECEIVABLE AGREEMENT heading but with different HTML markup. You'll need a broader detection strategy.

## Approach

Write a Python script in `/tmp/extract_embedded_tras.py` that for each input file:

1. Detects whether the file fits the "wrapper" pattern (size > 500KB AND a `Tax Receivable Agreement` reference exists later in the document, well past line 1).
2. Identifies the TRA start. Multiple candidate strategies, fall through in order:
   - **Best**: a heading-like element (`<P>`, `<DIV>`, `<H1-6>`) that is centered AND bolded AND whose visible text is exactly `TAX RECEIVABLE AGREEMENT` or `FORM OF TAX RECEIVABLE AGREEMENT` (allowing for `<font>` / `<b>` wrappers between the centered element and the text).
   - **Next best**: a centered element whose text is `EXHIBIT [A-Z]` or `ANNEX [A-Z]` and which is followed within a few lines by `Tax Receivable Agreement` (case-insensitive).
   - **Fallback**: any line where the text content (after stripping HTML tags) is exactly `TAX RECEIVABLE AGREEMENT` (uppercase, standalone).
3. Identifies the TRA end. Multiple strategies:
   - **Best**: next centered+bold `EXHIBIT [A-Z]` / `ANNEX [A-Z]` / `SCHEDULE [A-Z]` heading after the TRA's IN WITNESS WHEREOF.
   - **Next best**: end of file.
4. For the duplicate `arya-sciences` / `amicus-therapeutics` pair, extract once, write twice.
5. For `alti-global` and `genesis-healthcare`, recognize the stub pattern and either skip (leaving the original alone) or write a passthrough copy noted as `cannot extract via line-based method`.
6. For each successful extraction, write `<original-stem>.tra-extracted.htm` alongside the original. Wrap the extracted lines in `<html><body>...</body></html>` so pandoc has a valid root.
7. Build a manifest at `/tmp/tra_extraction_manifest.md` with columns: file, total_lines, start_line, end_line, extracted_bytes, status (`extracted` / `stub_skip` / `failed`), notes.

After the script runs, run the pipeline on each `.tra-extracted.htm`:

```bash
for f in $(find TRA-contracts -name '*.tra-extracted.htm'); do
  stem="${f%.htm}"
  pixi run -- python ~/.claude/skills/tra-htm-to-md/scripts/preprocess_html.py "$f" --output "${stem}.preprocessed.htm" > /dev/null 2>&1
  pandoc --from=html --to=markdown --wrap=none "${stem}.preprocessed.htm" -o "${stem}.pandoc.md" 2> /dev/null
  pixi run -- python ~/.claude/skills/tra-htm-to-md/scripts/clean_and_link.py "${stem}.pandoc.md" --output "${stem}.md" > /dev/null 2>&1
done
# Clean intermediates
find TRA-contracts -name '*.tra-extracted.preprocessed.htm' -delete
find TRA-contracts -name '*.tra-extracted.pandoc.md' -delete
```

This produces `<original-stem>.tra-extracted.md` files. The user will manually inspect a few and then decide whether to replace the original `.md` outputs.

## Constraints

- Don't modify or delete any existing `.htm` or `.md` files. Only write new `<stem>.tra-extracted.htm` and `<stem>.tra-extracted.md` files.
- Use `pixi run -- python` for any Python invocation that needs the project's environment (BeautifulSoup4 lives there).
- Don't write huge intermediates to `/tmp` other than the script and manifest.
- Don't dump the contents of any of these large files to stdout. Save intermediate inspection to `/tmp/` files if needed.
- Return a SHORT final report (under 400 words) with the manifest summary: count extracted / count stub-skipped / count failed, and the list of failed files with reasons. Do not include line-by-line per-file detail in your final report — that lives in the manifest file.

### Response



---
