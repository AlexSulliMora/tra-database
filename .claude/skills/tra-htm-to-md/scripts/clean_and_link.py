#!/usr/bin/env python3
"""Polish pandoc output from the TRA HTML preprocessor.

This script runs AFTER `preprocess_html.py` + pandoc and applies the
final markdown-level transforms:

1. **YAML frontmatter** for Quarto (title, format html, toc auto).
2. **Residual cleanup**: strip stray `<div>` / `</div>` tags pandoc passed
   through verbatim, drop empty-bold `** **` lines, collapse multi-line
   blank runs, drop leading EDGAR metadata lines if they slipped through.
3. **Definition list conversion** within the `# ARTICLE I` body: lines of
   the form `"[Term]{.underline}" means <body>.` become deflist entries
   with the quotation marks stripped from the term.
4. **Section-reference linking**: build the anchor set from existing
   `{#anchor}` heading attributes, then scan for `Section X.YZ`,
   `Article III`, `Schedule A`, `Exhibit B` patterns and convert to
   markdown links when the target anchor exists. Handles both
   `[Section X.YZ]{.underline}` (pandoc's encoded form of `<u>`) and
   plain-text references.

Usage:
    python clean_and_link.py <input.md> --output <output.md>
    python clean_and_link.py <input.md> --in-place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Heading attribute regex: pandoc emits `# ARTICLE I: DEFINITIONS {#article-i}`.
HEADING_WITH_ID_RE = re.compile(
    r"^(#+)\s+(.+?)\s*\{#([a-z0-9-]+)\}\s*$",
    re.MULTILINE,
)

# Reference patterns to match in body text.
SECTION_REF_RE = re.compile(r"\bSection\s+(\d+\.\d+)(?:\([a-z0-9]+\))*\b")
ARTICLE_REF_RE = re.compile(r"\bArticle\s+([IVXLCDM]+)\b")
SCHEDULE_REF_RE = re.compile(r"\bSchedule\s+([A-Z])\b")
EXHIBIT_REF_RE = re.compile(r"\bExhibit\s+([A-Z])\b")

# Pandoc's encoded form of <u>...</u> is `[text]{.underline}`.
UNDERLINE_SPAN_RE = re.compile(r"\[([^\]]+)\]\{\.underline\}")

# Definition paragraph: any line starting with a quoted defined term.
# Three encodings are accepted:
#   "[Term]{.underline}" body...        (Worldpay-style, <u>-wrapped)
#   "**Term**" body...                  (Appreciate-style, <strong>-wrapped)
#   "Term" body...                      (Dutch-Bros, Re-Max, Viant: plain)
# Restricted to the `# ARTICLE I` body so the match doesn't fire on
# body-text uses of quoted defined terms elsewhere.
DEFINITION_PARA_RE = re.compile(
    # Underlined term: matches all four quote placements, with an
    # optional `:` between the closing quote and the body (e.g.,
    # `"[Attributable]{.underline}": The portion...`):
    #   "[Term]{.underline}"   ["Term]{.underline}"
    #   "[Term"]{.underline}   ["Term"]{.underline}
    r'^"?\["?([^\]"]+?)"?\]\{\.underline\}"?:?\s+(.+)$|'
    # Bold term: "**Term**", with optional colon.
    r'^"\*\*([^*]+)\*\*"\s*:?\s*(.+)$|'
    # Plain quoted term: "Term" body..., with optional colon.
    r'^"([^"]{1,150}?)":?\s+(.+)$|'
    # Article-prefixed plain quoted term: A/An/The "Term" of/is/are/...
    r'^(?:A|An|The)\s+"([^"]{1,150}?)":?\s+(.+)$',
)

# Pandoc-emitted empty inline anchors `[]{#anchor-id}` from <a id="..."></a>
# nodes that pandoc preserves verbatim. Strip them before deflist matching.
EMPTY_INLINE_ANCHOR_RE = re.compile(r"\[\]\{#[^}]+\}")

# Stray div tags pandoc emits.
DIV_OPEN_RE = re.compile(r"^\s*<div>\s*$")
DIV_CLOSE_RE = re.compile(r"^\s*</div>\s*$")
EMPTY_BOLD_LINE_RE = re.compile(r"^\s*\*\*\s+\*\*\s*$")
NBSP_LINE_RE = re.compile(r"^\s*[ \s]+\s*$")
MULTI_BLANK_RE = re.compile(r"\n(\s*\n){2,}")


def section_slug(num: str) -> str:
    return "section-" + num.replace(".", "-")


def article_slug(roman: str) -> str:
    return "article-" + roman.lower()


def schedule_slug(letter: str) -> str:
    return "schedule-" + letter.lower()


def exhibit_slug(letter: str) -> str:
    return "exhibit-" + letter.lower()


def build_anchor_set(text: str) -> set[str]:
    """Build the set of `{#anchor}` ids declared on headings."""
    return {m.group(3) for m in HEADING_WITH_ID_RE.finditer(text)}


FENCED_DIV_RE = re.compile(r"^\s*:::\s*(?:\{[^}]*\})?\s*$", re.MULTILINE)


def strip_fenced_divs(text: str) -> str:
    """Strip pandoc's fenced div opening/closing lines (`:::` and
    `::: {align="left"}` etc.). These come from `<div align="left">` and
    similar wrappers in SEC HTML; they fragment content visually and
    have no value in our markdown output (alignment doesn't render
    meaningfully without surrounding CSS)."""
    return FENCED_DIV_RE.sub("", text)


ORPHAN_LEADING_DOT_RE = re.compile(r"^\.\s+([A-Z])", re.MULTILINE)


def strip_orphan_leading_dot(text: str) -> str:
    """Strip a stray leading `. ` from paragraphs that begin with `. <Capital>`.
    This appears when `_split_section_paragraph` extracted the section title
    but left the terminating period (wrapped in a <font> tag) at the start
    of the body."""
    return ORPHAN_LEADING_DOT_RE.sub(r"\1", text)


DASH_SEPARATOR_RE = re.compile(r"^\s*-{3,}(?:\s+-{3,})+\s*$")
TOC_HEADING_RE = re.compile(
    r"^#{1,3}\s+(TABLE\s+OF\s+CONTENTS|CONTENTS)\s*(?:\{#[a-z0-9-]+\})?\s*$",
    re.IGNORECASE,
)
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
TOC_REF_RE = re.compile(
    r"\b(?:ARTICLE\s+[IVXLCDM]+|Section\s+\d+\.\d+|EXHIBIT\s+[A-Z]|SCHEDULE\s+[A-Z])\b",
    re.IGNORECASE,
)


def strip_table_of_contents(text: str) -> str:
    """Two passes:

    1. Drop the `## TABLE OF CONTENTS` (or `## CONTENTS`) heading and all
       content following it up to the next heading. SEC ToCs render as
       dash-grid markdown tables that are noisy and meaningless without
       page numbers.
    2. Drop standalone pandoc dash-grid tables whose contents include 3+
       ARTICLE / Section / EXHIBIT / SCHEDULE references — those are
       page-bearing ToCs that survived without a leading heading. The
       nebula-style defined-term index (whose section refs use the `§`
       glyph, not the words ARTICLE/Section) is preserved.
    """
    lines = text.splitlines(keepends=True)

    # Pass 1: strip ToC heading + content until next heading.
    out: list[str] = []
    in_toc = False
    for line in lines:
        if TOC_HEADING_RE.match(line.rstrip("\n")):
            in_toc = True
            continue
        if in_toc:
            if ANY_HEADING_RE.match(line):
                in_toc = False
                out.append(line)
            continue
        out.append(line)

    # Pass 2: strip standalone dash-grid ToC tables.
    lines = out
    out = []
    i = 0
    while i < len(lines):
        if DASH_SEPARATOR_RE.match(lines[i].rstrip("\n")):
            j = i + 1
            while j < len(lines) and not DASH_SEPARATOR_RE.match(lines[j].rstrip("\n")):
                j += 1
            if j < len(lines):
                block_text = "".join(lines[i:j + 1])
                if len(TOC_REF_RE.findall(block_text)) >= 3:
                    i = j + 1
                    continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def strip_residual_html(text: str) -> str:
    """Drop stray <div> and </div> lines, empty-bold lines, NBSP-only lines."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if DIV_OPEN_RE.match(line) or DIV_CLOSE_RE.match(line):
            continue
        if EMPTY_BOLD_LINE_RE.match(line):
            out.append("\n")
            continue
        if NBSP_LINE_RE.match(line) and line.strip("  \t\n") == "":
            out.append("\n")
            continue
        out.append(line)
    return "".join(out)


def collapse_blank_runs(text: str) -> str:
    return MULTI_BLANK_RE.sub("\n\n", text).strip("\n") + "\n"


def find_article_i_range(text: str) -> tuple[int, int] | None:
    """Return (start, end) line indices for the Definitions section,
    exclusive of the heading itself. End is the line index of the next
    article-level heading (or end of file).

    The Definitions section is identified by a `## ARTICLE <N>:` heading
    whose title contains the word 'definitions' (case-insensitive), or by
    a fallback to `article-i` when no such title exists."""
    lines = text.splitlines(keepends=True)
    start = None
    title_idx_to_id: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = HEADING_WITH_ID_RE.match(line)
        if m and m.group(1) == "##":
            title_idx_to_id.append((i, m.group(2), m.group(3)))
    # Prefer a heading whose title contains 'definitions'.
    for i, title, ident in title_idx_to_id:
        if re.search(r"\bdefinitions?\b", title, re.IGNORECASE):
            start = i + 1
            break
    # Fallback: the heading with id `article-i`.
    if start is None:
        for i, _title, ident in title_idx_to_id:
            if ident == "article-i":
                start = i + 1
                break
    if start is None:
        return None
    for j in range(start, len(lines)):
        if re.match(r"^##\s+ARTICLE\b", lines[j]) or re.match(r"^#\s+", lines[j]):
            return (start, j)
    return (start, len(lines))


def convert_definitions_to_deflist(text: str) -> tuple[str, int]:
    """Within the `# ARTICLE I` body, convert each definition paragraph
    `"[Term]{.underline}" means <body>` into a markdown deflist entry:

        Term
        :   means <body>

    Returns (new_text, count_converted)."""
    rng = find_article_i_range(text)
    if rng is None:
        return text, 0
    start, end = rng
    lines = text.splitlines(keepends=True)
    count = 0
    new_lines: list[str] = []
    # While inside the Definitions section, treat any non-blank paragraph
    # between two deflist entries as a continuation of the previous
    # definition: indent with four spaces so pandoc nests it under the
    # entry. The continuation block ends only when a new deflist entry
    # starts or when we leave the Definitions region.
    in_entry = False
    for idx, line in enumerate(lines):
        if start <= idx < end:
            stripped = EMPTY_INLINE_ANCHOR_RE.sub("", line.rstrip("\n"))
            m = DEFINITION_PARA_RE.match(stripped)
            if m:
                term = (
                    m.group(1) or m.group(3) or m.group(5) or m.group(7) or ""
                ).strip()
                body = (
                    m.group(2) or m.group(4) or m.group(6) or m.group(8) or ""
                ).strip()
                # Normalize the term: strip bold/italic markdown markers
                # and underline spans so the definitions section presents
                # every defined term in plain text, regardless of how the
                # source HTML wrapped it.
                term = re.sub(r"\*\*", "", term)
                term = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", term)
                term = UNDERLINE_SPAN_RE.sub(r"\1", term)
                term = re.sub(r"\s+", " ", term).strip()
                if term:
                    new_lines.append(f"{term}\n")
                    new_lines.append(f":   {body}\n")
                    new_lines.append("\n")
                    count += 1
                    in_entry = True
                    continue
            if in_entry and line.strip() != "":
                new_lines.append(f"    {line.lstrip()}")
                if not line.endswith("\n"):
                    new_lines.append("\n")
                continue
        new_lines.append(line)
    return "".join(new_lines), count


def link_underline_spans(text: str, anchors: set[str]) -> tuple[str, int]:
    """Scan `[text]{.underline}` spans; if `text` is a single-reference
    pattern with an existing anchor, replace with a markdown link. If it
    is a defined-term emphasis (no ref pattern match), strip the
    `{.underline}` markup and keep `[text]` -> plain `text`."""
    linked = 0

    def repl(m: re.Match) -> str:
        nonlocal linked
        inner = m.group(1).strip()
        # Try section: 'Section X.YZ' (optionally with subsection)
        sm = re.match(r"^Section\s+(\d+\.\d+)(?:\([a-z0-9]+\))*$", inner)
        if sm:
            slug = section_slug(sm.group(1))
            if slug in anchors:
                linked += 1
                return f"[{inner}](#{slug})"
        am = re.match(r"^Article\s+([IVXLCDM]+)$", inner)
        if am:
            slug = article_slug(am.group(1))
            if slug in anchors:
                linked += 1
                return f"[{inner}](#{slug})"
        schm = re.match(r"^Schedule\s+([A-Z])$", inner)
        if schm:
            slug = schedule_slug(schm.group(1))
            if slug in anchors:
                linked += 1
                return f"[{inner}](#{slug})"
        em = re.match(r"^Exhibit\s+([A-Z])$", inner)
        if em:
            slug = exhibit_slug(em.group(1))
            if slug in anchors:
                linked += 1
                return f"[{inner}](#{slug})"
        # Not a reference pattern: defined-term emphasis. Strip the
        # underline markup, keep the inner text plain.
        return inner

    new_text = UNDERLINE_SPAN_RE.sub(repl, text)
    return new_text, linked


def link_plain_text_refs(text: str, anchors: set[str]) -> tuple[str, int]:
    """Scan plain text for Section / Article / Schedule / Exhibit
    references; link to existing anchors. Skip matches inside code
    fences, existing markdown links, or already-linked spans."""
    linked = 0

    # Process line by line to make existing-link detection simpler.
    # Skip headings, fenced code, and lines that already contain markdown links.
    out_lines: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence or line.startswith("#"):
            out_lines.append(line)
            continue

        # Split the line into "already-linked" and "plain" segments and only
        # transform the plain segments. Markdown link form: `[text](url)`.
        segments = re.split(r"(\[[^\]]+\]\([^\)]+\))", line)
        new_segments: list[str] = []
        for seg in segments:
            if seg.startswith("[") and "](" in seg:
                # Already a link; leave alone.
                new_segments.append(seg)
                continue
            seg, n1 = _link_pattern_in_segment(seg, SECTION_REF_RE, section_slug, anchors, group=1)
            linked += n1
            seg, n2 = _link_pattern_in_segment(seg, ARTICLE_REF_RE, article_slug, anchors, group=1)
            linked += n2
            seg, n3 = _link_pattern_in_segment(seg, SCHEDULE_REF_RE, schedule_slug, anchors, group=1)
            linked += n3
            seg, n4 = _link_pattern_in_segment(seg, EXHIBIT_REF_RE, exhibit_slug, anchors, group=1)
            linked += n4
            new_segments.append(seg)
        out_lines.append("".join(new_segments))
    return "".join(out_lines), linked


def _link_pattern_in_segment(seg, pattern, slug_fn, anchors, group=1):
    """Apply a single reference pattern to a segment with the existence
    filter. Returns (new_seg, count_linked)."""
    linked = 0

    def repl(m: re.Match) -> str:
        nonlocal linked
        target = slug_fn(m.group(group))
        if target in anchors:
            linked += 1
            return f"[{m.group(0)}](#{target})"
        return m.group(0)

    return pattern.sub(repl, seg), linked


def prepend_yaml_frontmatter(text: str, title: str | None = None) -> str:
    """Prepend a Quarto-friendly YAML frontmatter block with auto-TOC."""
    if text.startswith("---\n"):
        # Already has frontmatter; leave alone.
        return text
    title_line = f'title: "{title}"\n' if title else ""
    fm = (
        "---\n"
        + title_line
        + "format:\n"
        + "  html:\n"
        + "    toc: true\n"
        + "    toc-depth: 3\n"
        + "    toc-location: left\n"
        + "---\n\n"
    )
    return fm + text


def derive_title(text: str) -> str | None:
    """Detect the document title from the consolidated H1 (preferred) or
    a leading bold-only `**TAX RECEIVABLE AGREEMENT**` line."""
    for line in text.splitlines()[:60]:
        # H1 from the consolidated title block.
        m = re.match(r"^#\s+([^\{]+?)(?:\s*\{#[a-z0-9-]+\})?\s*$", line)
        if m:
            t = m.group(1).strip()
            if 5 <= len(t) <= 120 and "AGREEMENT" in t.upper():
                return t
        # Fall-through: leading bold line.
        m = re.match(r"^\*\*([^\*]+)\*\*\s*$", line.strip())
        if m and len(m.group(1)) < 120:
            t = m.group(1).strip()
            if "AGREEMENT" in t.upper() or "RECEIVABLE" in t.upper():
                return t
    return None


PANDOC_ESCAPE_RE = re.compile(r"\\([\$\#\&\<\>])")
STANDALONE_BACKSLASH_LINE_RE = re.compile(r"^\s*\\\s*$")


def unescape_pandoc_artifacts(text: str) -> str:
    """Un-escape pandoc punctuation escapes that aren't load-bearing in
    the output (`\\$`, `\\#`, `\\&`, `\\<`, `\\>`) and drop standalone `\\`
    hard-line-break markers."""
    text = PANDOC_ESCAPE_RE.sub(r"\1", text)
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if STANDALONE_BACKSLASH_LINE_RE.match(line):
            out.append("\n")
            continue
        out.append(line)
    return "".join(out)


def polish(text: str) -> tuple[str, dict]:
    """Apply all polish steps. Returns (new_text, stats)."""
    stats: dict = {}
    text = strip_residual_html(text)
    text = strip_fenced_divs(text)
    text = strip_orphan_leading_dot(text)
    text = strip_table_of_contents(text)
    text = unescape_pandoc_artifacts(text)
    text = collapse_blank_runs(text)

    anchors = build_anchor_set(text)
    stats["anchors"] = len(anchors)

    # Deflist conversion must run BEFORE the underline-linker, since the
    # deflist pattern relies on the `[Term]{.underline}` markup that the
    # underline-linker would otherwise strip.
    text, n_def = convert_definitions_to_deflist(text)
    stats["definitions_converted"] = n_def

    text, n_under = link_underline_spans(text, anchors)
    stats["underline_refs_linked"] = n_under

    text, n_plain = link_plain_text_refs(text, anchors)
    stats["plain_text_refs_linked"] = n_plain

    text = collapse_blank_runs(text)
    title = derive_title(text)
    text = prepend_yaml_frontmatter(text, title=title)
    return text, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Polish pandoc markdown output for TRA contracts.",
    )
    parser.add_argument("input", help="Pandoc markdown output (.md or .pandoc.md).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-o", "--output", help="Write polished output here.")
    group.add_argument("--in-place", action="store_true", help="Rewrite input.")
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    text, stats = polish(text)
    output_path = Path(args.input if args.in_place else args.output)
    output_path.write_text(text, encoding="utf-8")

    print(f"Anchors detected: {stats['anchors']}")
    print(f"Underline-span references linked: {stats['underline_refs_linked']}")
    print(f"Plain-text references linked: {stats['plain_text_refs_linked']}")
    print(f"Definitions converted to deflist: {stats['definitions_converted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
