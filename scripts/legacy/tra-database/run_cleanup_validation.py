"""S2 validation: apply deterministic cleanup rules (1, 4, 5, 6, 8) from the
`tra-htm-to-md` skill to one representative pandoc.md per sampled folder.

Run from `<project root>` via `pixi run python <this>`. Writes
`<stem>.final.md` next to each input. Reports per-file before/after
line counts and how many lines of each artifact category were removed.

This validation covers the rules that can be applied without
structural-judgment (header strip, page-break/page-number removal,
backslash-unescape, empty-span and <u>-tag removal, NBSP filler
stripping). Rules 2, 3, 7 (HTML-table reconstitution, substantive-table
preservation, atomized-paragraph rejoining) require per-document
judgment and are spot-checked manually after the deterministic pass.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# One representative pandoc.md per sampled folder; chosen as the
# executed/form-of TRA contract (not amendments), matching the brief.
REPRESENTATIVES = [
    "appreciate-holdings-inc_0001821075__TRA-2022-11-29__2022-11-29_executed_ea169605ex10-1_appreciate.htm.pandoc.md",
    "bitcoin-depot-inc_0001901799__TRA-2023-06-30__2023-06-13_d479758dex104.htm.pandoc.md",
    "charter-communications-inc-mo_0001091667__TRA-2025-05-16-cox-form__2025-05-16_ef20049261_ex2-1.htm.pandoc.md",
    "eve-holding-inc_0001823652__TRA-2022-05-09__2022-05-13_d337083dex103.htm.pandoc.md",
    "galaxy-digital-holdings-ltd_0001405064__TRA-2018-07-31__2022-01-28_form-of-AR-TRA_ex10-3.htm.pandoc.md",
    "hicks-acquisition-co-ii-inc_0001416995__TRA-2012-05-16__2012-05-18_form-of-TRA-via-CrossPurchase-ex22.htm.pandoc.md",
    "twfg-inc_0002007596__TRA-2024-07-19__2024-07-23_exhibit102-8xk.htm.pandoc.md",
    "wayne-farms-inc_0001636032__TRA-2015-04-20__2015-04-20_form-of_ex10-3.htm.pandoc.md",
    "worldpay-inc_0001533932__TRA-2012-03-21-fifthThird__2012-05-08_executed_ex-10.6.htm.pandoc.md",
    "zoominfo-technologies-inc_0001794515__TRA-2020-06-03-Reorganization__2020-05-26_exhibit104taxreceivableagr.htm.pandoc.md",
]

HRULE = "-" * 72
TOC_LINK = "##### [Table of Contents](#toc)"
EMPTY_SPAN = re.compile(r'<span id="[^"]*"></span>')
U_TAG = re.compile(r"</?u>")
ESCAPED_PUNCT = re.compile(r"\\([()_\[\]])")
PAGE_NUM_LINE = re.compile(r"^\s*\d+\s*$")
NBSP_ONLY = re.compile(r"^[\s ]+$")


def clean(text: str) -> tuple[str, dict[str, int]]:
    lines = text.splitlines()
    counts = {
        "header_lines_dropped": 0,
        "page_rules_dropped": 0,
        "page_numbers_dropped": 0,
        "toc_links_dropped": 0,
        "empty_spans_dropped": 0,
        "u_tags_unwrapped": 0,
        "escaped_punct_unescaped": 0,
        "nbsp_filler_dropped": 0,
    }

    # Rule 1: drop leading exhibit-metadata block. Strip lines until we hit
    # the first bolded line (typically `**Exhibit ...` or `**TAX...`).
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("**") or line.startswith("# "):
            start = i
            break
    counts["header_lines_dropped"] = start
    lines = lines[start:]

    cleaned: list[str] = []
    for line in lines:
        # Rule 4: drop horizontal-rule page breaks
        if line.strip() == HRULE:
            counts["page_rules_dropped"] += 1
            continue
        # Rule 4: drop standalone page-number lines
        if PAGE_NUM_LINE.match(line) and line.strip() != "":
            # Be conservative: only treat as page-number if the integer is
            # small (< 1000) and the line is short, to avoid stripping
            # legitimate numeric-only table cells.
            if len(line.strip()) <= 4:
                counts["page_numbers_dropped"] += 1
                continue
        # Rule 4: drop repeated TOC heading links
        if line.strip() == TOC_LINK:
            counts["toc_links_dropped"] += 1
            continue
        # Rule 8: drop NBSP-only filler lines
        if NBSP_ONLY.match(line) and (line.strip() == "" or " " in line):
            if " " in line:
                counts["nbsp_filler_dropped"] += 1
                continue
        # Rule 6: drop empty span anchors
        new_line, n_spans = EMPTY_SPAN.subn("", line)
        counts["empty_spans_dropped"] += n_spans
        # Rule 6: unwrap <u>...</u> tags
        new_line, n_u = U_TAG.subn("", new_line)
        counts["u_tags_unwrapped"] += n_u
        # Rule 5: unescape backslash-escaped punctuation
        new_line, n_esc = ESCAPED_PUNCT.subn(r"\1", new_line)
        counts["escaped_punct_unescaped"] += n_esc
        cleaned.append(new_line)

    # Collapse runs of >2 blank lines to exactly 1 blank line
    out: list[str] = []
    blank_run = 0
    for line in cleaned:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append(line)
        else:
            blank_run = 0
            out.append(line)

    return "\n".join(out) + "\n", counts


def main() -> None:
    report_lines: list[str] = []
    failures: list[tuple[str, str]] = []

    for fname in REPRESENTATIVES:
        src = HERE / fname
        if not src.exists():
            failures.append((fname, "input pandoc.md missing"))
            continue
        text = src.read_text()
        before = text.count("\n") + 1
        cleaned, counts = clean(text)
        after = cleaned.count("\n") + 1
        out = src.with_suffix("")
        # filename pattern: <stem>.pandoc.md -> <stem>.final.md
        if str(src).endswith(".pandoc.md"):
            out = Path(str(src)[: -len(".pandoc.md")] + ".final.md")
        else:
            out = src.with_suffix(".final.md")
        out.write_text(cleaned)
        report_lines.append(
            f"- `{fname}`: {before} -> {after} lines "
            f"(header={counts['header_lines_dropped']}, "
            f"page_rules={counts['page_rules_dropped']}, "
            f"page_nums={counts['page_numbers_dropped']}, "
            f"toc_links={counts['toc_links_dropped']}, "
            f"empty_spans={counts['empty_spans_dropped']}, "
            f"u_tags={counts['u_tags_unwrapped']}, "
            f"escaped_punct={counts['escaped_punct_unescaped']}, "
            f"nbsp_filler={counts['nbsp_filler_dropped']})"
        )

    print(f"Processed {len(REPRESENTATIVES) - len(failures)} files; "
          f"{len(failures)} failures.")
    for line in report_lines:
        print(line)
    if failures:
        for fname, reason in failures:
            print(f"FAILURE: {fname}: {reason}")


if __name__ == "__main__":
    main()
