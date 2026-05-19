#!/usr/bin/env python3
"""Preprocess SEC EDGAR TRA HTML for pandoc conversion.

Normalizes recurring SEC HTML quirks into structure pandoc can convert
cleanly:

1. Strip page-break artifacts: <a name="PB_*">, <hr>, <p> page numbers,
   recurring "Table of Contents" backlinks.
2. Promote bolded ARTICLE / SECTION / SCHEDULE / EXHIBIT paragraphs into
   real <h1> / <h2> / <h3> headings with stable id attributes. Handles
   one-line, two-line (ARTICLE I + DEFINITIONS), and three-line
   (ARTICLE / I / DEFINITIONS) constructions.
3. Strip layout-only tables (TOC, signature blocks, decorative shims,
   single-clause indent wrappers).
4. Strip visual styling: <font> tags, style attributes on <span> /
   <div> outside <table> blocks.
5. Merge consecutive <p> blocks split by page-break injection: when
   the first does not end in sentence-terminating punctuation and the
   next starts with lowercase or a continuation word.

Usage:
    python preprocess_html.py <input.htm> -o <output.htm>
    python preprocess_html.py <input.htm> --in-place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag


ROMAN_RE = re.compile(r"^[IVXLCDM]+$")
ARTICLE_INLINE_RE = re.compile(
    r"^\s*ARTICLE\s+([IVXLCDM]+)\b(?:\s*[:.\-–—]?\s*(.*))?$",
    re.IGNORECASE,
)
ARTICLE_BARE_RE = re.compile(r"^\s*ARTICLE\s*$", re.IGNORECASE)
SECTION_INLINE_RE = re.compile(
    r"^\s*SECTION\s+(\d+\.\d+)\b\.?\s*(.*)$",
    re.IGNORECASE,
)
SCHEDULE_INLINE_RE = re.compile(
    r"^\s*SCHEDULE\s+([A-Z])\b\.?\s*(.*)$",
    re.IGNORECASE,
)
EXHIBIT_INLINE_RE = re.compile(
    r"^\s*EXHIBIT\s+([A-Z])\b\.?\s*(.*)$",
    re.IGNORECASE,
)
ALL_CAPS_TITLE_RE = re.compile(r"^[A-Z][A-Z0-9 \-,;'/&]+$")
SENTENCE_END_RE = re.compile(r"[\.\?\!:;\"”’]$")


UNCLOSED_PAGEBREAK_P_RE = re.compile(
    r"<p\s+[Ss]tyle\s*=\s*['\"]\s*page-break-(?:before|after)\s*:\s*always\s*['\"]\s*>",
)

# Any TOC anchor link with content (possibly including nested tags).
_TOC_LINK_WITH_CONTENT_RE = re.compile(
    r"<a\s+href\s*=\s*[\"']#([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
# Anchor target definition (matches name= or id= form).
_ANCHOR_NAME_OR_ID_RE_TMPL = (
    r"<a\s+(?:name|id)\s*=\s*[\"']{tid}[\"']"
)


def _strip_tags_and_entities(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&#160;", " ")
        .replace("&nbsp;", " ")
        .replace("&#8201;", " ")
        .replace("&amp;", "&")
    )
    return text


def _extract_tra_from_filing(html_text: str) -> str:
    """If the HTML is a large SEC filing (S-4, DRS, 424B3, proxy) with a
    TRA embedded as an annex/exhibit, extract just the TRA region.
    Otherwise return the input unchanged.

    Strategy: collect every TOC anchor link. Find the ones whose visible
    text mentions Tax Receivable; treat each as a candidate. For each
    candidate, find its anchor target in the body, then find the next
    OTHER-TOC-target anchor; that brackets a candidate region. Pick the
    candidate that yields the largest substantial region (>5KB). This
    handles documents (Stagwell) that use both a short summary TOC
    pointing at page-marker anchors and a detailed annex TOC pointing
    at the real annex body anchor: the page-marker bracket is tiny
    while the annex bracket is 100KB+, so the annex wins."""
    SIZE_THRESHOLD = 500_000
    MIN_EXTRACT_SIZE = 5_000
    if len(html_text) < SIZE_THRESHOLD:
        return html_text

    all_toc_targets: list[str] = []
    candidates: list[tuple[str, int]] = []
    for m in _TOC_LINK_WITH_CONTENT_RE.finditer(html_text):
        all_toc_targets.append(m.group(1))
        inner = _strip_tags_and_entities(m.group(2))
        if re.search(r"Tax\s+Receivable", inner, re.IGNORECASE):
            candidates.append((m.group(1), m.end()))
    if not candidates:
        return html_text

    best: tuple[int, int] | None = None
    best_size = 0
    for target_id, toc_end in candidates:
        target_re = re.compile(
            _ANCHOR_NAME_OR_ID_RE_TMPL.format(tid=re.escape(target_id)),
            re.IGNORECASE,
        )
        start_match = target_re.search(html_text, pos=toc_end)
        if not start_match:
            continue
        other_targets = sorted({t for t in all_toc_targets if t != target_id})
        end = len(html_text)
        if other_targets:
            other_re = re.compile(
                r"<a\s+(?:name|id)\s*=\s*[\"'](?:"
                + "|".join(re.escape(t) for t in other_targets)
                + r")[\"']",
                re.IGNORECASE,
            )
            # Skip aliases: anchors that sit within a few hundred bytes of
            # the start are usually multiple ID-aliases on the same Annex
            # marker. Real section boundaries are at least 1KB away.
            ALIAS_PROXIMITY = 1_000
            search_pos = start_match.end()
            while True:
                em = other_re.search(html_text, pos=search_pos)
                if em is None:
                    break
                if em.start() - start_match.end() < ALIAS_PROXIMITY:
                    search_pos = em.end()
                    continue
                end = em.start()
                break
        extract_start = html_text.rfind("<", 0, start_match.start())
        if extract_start < 0:
            extract_start = start_match.start()
        size = end - extract_start
        if size > best_size and size > MIN_EXTRACT_SIZE:
            best_size = size
            best = (extract_start, end)

    if best is None:
        return html_text
    extracted = html_text[best[0]:best[1]]
    return f"<html><body>\n{extracted}\n</body></html>"


def _clip_to_html(html_text: str) -> str:
    """Strip EDGAR SGML metadata (<TYPE>, <SEQUENCE>, <FILENAME>,
    <DESCRIPTION>, <TEXT>) that prefixes the actual HTML document.
    Also normalize unclosed `<p Style='page-break-before:always'>` tags
    (Sculptor pattern) to `<hr>` so BS4 doesn't parse subsequent content
    as nested inside the open `<p>`. For large filings that wrap the
    TRA inside a much larger document (proxy, S-4, DRS, 424B3), extract
    just the TRA region using the TOC's own anchor structure."""
    m = re.search(r"<html\b", html_text, re.IGNORECASE)
    if m:
        html_text = html_text[m.start():]
    else:
        m = re.search(r"<body\b", html_text, re.IGNORECASE)
        if m:
            html_text = html_text[m.start():]
    html_text = _extract_tra_from_filing(html_text)
    html_text = UNCLOSED_PAGEBREAK_P_RE.sub("<hr>", html_text)
    return html_text


def _parse(html_text: str) -> BeautifulSoup:
    html_text = _clip_to_html(html_text)
    try:
        return BeautifulSoup(html_text, "html.parser")
    except Exception:
        return BeautifulSoup(html_text, "html.parser")


def strip_page_break_artifacts(soup: BeautifulSoup) -> int:
    """Remove SEC page-break debris. Returns count of removals."""
    removed = 0

    # <a name="PB_*"> or <a id="PB_*"> page-break anchors (usually empty).
    for a in soup.find_all("a"):
        ident = a.get("name") or a.get("id") or ""
        if ident.startswith("PB_") or ident.lower().startswith("pb_"):
            a.decompose()
            removed += 1

    # <hr> page-break separators.
    for hr in soup.find_all("hr"):
        hr.decompose()
        removed += 1

    # <p> containing only a page-number variant: bare integer (`9`),
    # dash-bracketed (`-9-`), roman (`iv`, `-iv-`).
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if re.fullmatch(r"-?\d{1,3}-?|-?[ivxlcdm]+-?", text, re.IGNORECASE):
            p.decompose()
            removed += 1

    # Recurring "Table of Contents" backlinks. Two shapes:
    #   <p><a href="#toc">Table of Contents</a></p>
    #   <a href="#toc">Table of Contents</a> inline
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if href.lower() in ("#toc", "#table_of_contents", "#table-of-contents"):
            text = a.get_text(strip=True).lower()
            if "table of contents" in text or text == "":
                parent = a.parent
                if (parent and parent.name == "p"
                        and parent.get_text(strip=True).lower()
                        == a.get_text(strip=True).lower()):
                    parent.decompose()
                else:
                    a.decompose()
                removed += 1

    return removed


def _is_inside_table(tag: Tag) -> bool:
    for ancestor in tag.parents:
        if ancestor.name == "table":
            return True
    return False


def _replace_with_heading(
    soup: BeautifulSoup, p: Tag, level: int, ident: str, title_text: str,
) -> None:
    """Replace <p> with <hN id="ident">title_text</hN>."""
    heading = soup.new_tag(f"h{level}", id=ident)
    heading.string = title_text
    p.replace_with(heading)


def _split_section_paragraph(soup: BeautifulSoup, p: Tag, num: str) -> bool:
    """Split a <p> of the form 'SECTION X.YZ. <emph>TITLE</emph>. BODY...'
    into <h3 id="section-X-YZ">Section X.YZ: TITLE</h3> followed by
    <p>BODY...</p>. Returns True on success."""
    # Find the first emphasis element inside the <p> whose text is short
    # enough to be a title (heuristic: under 100 chars).
    title_elem = None
    for tag in p.find_all(["u", "b", "strong", "i", "em"]):
        if _is_inside_table(tag):
            continue
        t = tag.get_text(strip=True)
        # Title must not include the section-number prefix.
        if SECTION_INLINE_RE.match(t):
            continue
        if 1 <= len(t) <= 120:
            title_elem = tag
            break
    if title_elem is None:
        return False

    title = title_elem.get_text(separator=" ", strip=True)
    title = re.sub(r"\s+", " ", title).strip(" .:,")
    # Strip a leading 'Section X.YZ' prefix if the emphasis text includes it
    # (some contracts wrap the entire heading in <strong>Section 1.1 Title</strong>).
    title = re.sub(
        r"^Section\s+\d+\.\d+\.?\s*", "", title, flags=re.IGNORECASE,
    ).strip(" .:,")
    if not title:
        return False

    # Collect everything inside <p> that follows the title_elem (recursively
    # by checking descendants order).
    body_parts: list = []
    seen_title = False
    for descendant in list(p.descendants):
        if descendant is title_elem:
            seen_title = True
            continue
        if not seen_title:
            continue
        if isinstance(descendant, Tag):
            # Skip Tag descendants whose parent is also captured (avoid
            # duplication); instead capture top-level tags after title_elem
            # by walking siblings explicitly. We'll handle this below.
            pass

    # Better approach: extract siblings of title_elem within the same <p>
    # via a sibling walk.
    body_html_parts: list[str] = []
    capture = False
    for child in list(p.children):
        if not capture:
            # Find when we cross the title element.
            if isinstance(child, Tag) and (child is title_elem
                                            or title_elem in child.descendants):
                capture = True
            continue
        if isinstance(child, Tag):
            body_html_parts.append(str(child))
        else:
            body_html_parts.append(str(child))
    body_html = "".join(body_html_parts).strip()

    heading = soup.new_tag("h3", id=f"section-{num.replace('.', '-')}")
    heading.string = f"Section {num}: {title}"
    p.replace_with(heading)
    if body_html:
        body_soup = BeautifulSoup(body_html, "html.parser")
        body_text = body_soup.get_text(separator=" ", strip=True)
        body_text_clean = re.sub(r"[\s\xa0.,;:]+", "", body_text)
        if body_text_clean:
            body_p = soup.new_tag("p")
            for child in list(body_soup.children):
                body_p.append(child)
            heading.insert_after(body_p)
    return True


def _next_paragraph_sibling(p: Tag, max_skip: int = 2) -> Tag | None:
    """Find the next <p> sibling, skipping over empty or whitespace-only
    siblings. Returns None if no qualifying sibling exists within max_skip."""
    sib = p.next_sibling
    skipped = 0
    while sib is not None and skipped < max_skip + 4:
        if isinstance(sib, Tag):
            if sib.name == "p":
                if sib.get_text(strip=True):
                    return sib
                # empty paragraph; keep looking
            elif sib.name in ("br", "span") and not sib.get_text(strip=True):
                pass
            else:
                return None
        elif isinstance(sib, NavigableString):
            if sib.strip() != "":
                return None
        sib = sib.next_sibling
        skipped += 1
    return None


def promote_inline_article_markers(soup: BeautifulSoup) -> int:
    """Walk <b>/<strong> tags and promote any whose text matches an
    ARTICLE marker (`ARTICLE I`, `ARTICLE III`, etc.) to <h2>. Catches
    SEC HTML where ARTICLE markers float outside a well-formed `<p>`
    wrapper, typically because the source has unclosed structural tags
    that BS4 parses as nested wrappers (Sculptor pattern). Companion to
    `promote_strong_headings`, which handles the well-formed case.

    If the next sibling-emphasis tag is an all-caps title, consume it as
    the heading's title (e.g., `ARTICLE III` + `TAX BENEFIT PAYMENTS`)."""
    promoted = 0
    used_slugs: set[str] = set()
    for b in list(soup.find_all(["b", "strong"])):
        if not b.parent or _is_inside_table(b):
            continue
        # Skip if this <b> sits inside an existing heading.
        if b.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"]):
            continue
        text = b.get_text(separator=" ", strip=True)
        m = ARTICLE_INLINE_RE.match(text)
        if not m:
            continue
        roman = m.group(1).upper()
        title_inline = (m.group(2) or "").strip(" \t:-–—")

        # Look ahead at neighboring emphasis tags for the title.
        if not title_inline:
            sib = b.next_sibling
            steps = 0
            while sib is not None and steps < 6:
                if isinstance(sib, Tag):
                    if sib.name in ("b", "strong"):
                        sib_text = re.sub(
                            r"\s+", " ",
                            sib.get_text(separator=" ", strip=True),
                        )
                        if ALL_CAPS_TITLE_RE.match(sib_text):
                            title_inline = sib_text.strip(" .:")
                            sib.decompose()
                        break
                    if sib.name in ("u", "i", "em", "font", "span"):
                        sib_text = re.sub(
                            r"\s+", " ",
                            sib.get_text(separator=" ", strip=True),
                        )
                        if ALL_CAPS_TITLE_RE.match(sib_text):
                            title_inline = sib_text.strip(" .:")
                            sib.decompose()
                            break
                    if sib.name in ("br",):
                        pass
                    else:
                        break
                elif isinstance(sib, NavigableString):
                    if sib.strip():
                        break
                sib = sib.next_sibling
                steps += 1

        slug = f"article-{roman.lower()}"
        if slug in used_slugs:
            continue
        used_slugs.add(slug)

        heading_text = (
            f"ARTICLE {roman}: {title_inline}" if title_inline
            else f"ARTICLE {roman}"
        )
        heading = soup.new_tag("h2", id=slug)
        heading.string = heading_text
        b.replace_with(heading)
        promoted += 1
    return promoted


def promote_strong_headings(soup: BeautifulSoup) -> int:  # noqa: C901
    """Convert <p>ARTICLE I</p>, <p>SECTION X.YZ</p>, <p>SCHEDULE A</p>,
    <p>EXHIBIT A</p> into <h2>/<h3>/<h2>/<h2> headings with stable ids."""
    promoted = 0

    paragraphs = list(soup.find_all("p"))
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i]
        if not p.parent:
            # Already detached from a previous pass.
            i += 1
            continue
        if _is_inside_table(p):
            i += 1
            continue
        text = p.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        if not text:
            i += 1
            continue

        # ARTICLE: inline form.
        m = ARTICLE_INLINE_RE.match(text)
        if m:
            roman = m.group(1).upper()
            title_inline = (m.group(2) or "").strip(" \t:-–—")
            # Look for a title on the next paragraph if not present inline.
            if not title_inline:
                next_p = _next_paragraph_sibling(p)
                if next_p is not None:
                    next_text = re.sub(
                        r"\s+", " ", next_p.get_text(separator=" ", strip=True)
                    )
                    if ALL_CAPS_TITLE_RE.match(next_text):
                        title_inline = next_text.strip(" .:")
                        next_p.decompose()
            heading_text = (
                f"ARTICLE {roman}: {title_inline}" if title_inline
                else f"ARTICLE {roman}"
            )
            _replace_with_heading(soup, p, 2, f"article-{roman.lower()}", heading_text)
            promoted += 1
            i += 1
            continue

        # ARTICLE: bare form (the roman is on the next <p>).
        if ARTICLE_BARE_RE.match(text):
            next_p = _next_paragraph_sibling(p)
            if next_p is None:
                i += 1
                continue
            next_text = re.sub(
                r"\s+", " ", next_p.get_text(separator=" ", strip=True)
            )
            if not ROMAN_RE.match(next_text):
                i += 1
                continue
            roman = next_text.upper()
            # And maybe the title is the <p> after that.
            title = ""
            next_next = _next_paragraph_sibling(next_p)
            if next_next is not None:
                nn_text = re.sub(
                    r"\s+", " ", next_next.get_text(separator=" ", strip=True)
                )
                if ALL_CAPS_TITLE_RE.match(nn_text):
                    title = nn_text.strip(" .:")
                    next_next.decompose()
            next_p.decompose()
            heading_text = (
                f"ARTICLE {roman}: {title}" if title else f"ARTICLE {roman}"
            )
            _replace_with_heading(soup, p, 2, f"article-{roman.lower()}", heading_text)
            promoted += 1
            i += 1
            continue

        # SECTION X.YZ. <emphasis>TITLE</emphasis>. body...
        # SEC TRA contracts put the heading and body in one <p>; split into
        # a real <h3> heading + a sibling <p> for the body.
        m = SECTION_INLINE_RE.match(text)
        if m:
            num = m.group(1)
            if _split_section_paragraph(soup, p, num):
                promoted += 1
                i += 1
                continue
            # Fallback: no emphasis title found inline. Treat the rest of
            # the matched text as the title (no body split).
            rest = (m.group(2) or "").strip(" .:")
            # If 'rest' is implausibly long (more than ~120 chars), it's
            # almost certainly body content; truncate at the first period.
            if len(rest) > 120:
                dot_pos = rest.find(".")
                if dot_pos > 0:
                    rest = rest[:dot_pos].strip(" .:")
            heading_text = (
                f"Section {num}: {rest}" if rest else f"Section {num}"
            )
            ident = f"section-{num.replace('.', '-')}"
            _replace_with_heading(soup, p, 3, ident, heading_text)
            promoted += 1
            i += 1
            continue

        # SCHEDULE A ...
        m = SCHEDULE_INLINE_RE.match(text)
        if m:
            letter = m.group(1).upper()
            rest = (m.group(2) or "").strip(" .:")
            heading_text = (
                f"Schedule {letter}: {rest}" if rest else f"Schedule {letter}"
            )
            _replace_with_heading(soup, p, 2, f"schedule-{letter.lower()}", heading_text)
            promoted += 1
            i += 1
            continue

        # EXHIBIT A ...
        m = EXHIBIT_INLINE_RE.match(text)
        if m:
            letter = m.group(1).upper()
            rest = (m.group(2) or "").strip(" .:")
            heading_text = (
                f"Exhibit {letter}: {rest}" if rest else f"Exhibit {letter}"
            )
            _replace_with_heading(soup, p, 2, f"exhibit-{letter.lower()}", heading_text)
            promoted += 1
            i += 1
            continue

        i += 1

    return promoted


# Layout-table heuristics.
def _looks_like_toc_table(table: Tag) -> bool:
    """A TOC table either (a) has many internal-anchor links plus 'ARTICLE'
    or 'SECTION' text, or (b) has 3+ rows whose cells include multiple
    'Section X.YZ' / 'ARTICLE N' references alongside small integers
    (the trailing page-number column).

    Markdown output has no page numbers, so a TOC ends up as a useless
    dash-grid table anyway — drop it whether or not it carries anchor
    links."""
    text = table.get_text(separator=" ", strip=True)
    text_upper = text.upper()
    if "ARTICLE" not in text_upper and "SECTION" not in text_upper:
        return False
    # (a) Anchor-link form.
    links = table.find_all("a", href=True)
    if len(links) >= 3:
        internal_links = [a for a in links if a["href"].startswith("#")]
        if len(internal_links) >= len(links) * 0.5:
            return True
    # (b) Link-less form: many Article/Section references + trailing
    # integer page numbers.
    rows = table.find_all("tr")
    if len(rows) < 3:
        return False
    ref_count = len(re.findall(r"\bArticle\s+[IVXLCDM]+\b", text, re.IGNORECASE))
    ref_count += len(re.findall(r"\bSection\s+\d+\.\d+\b", text, re.IGNORECASE))
    if ref_count < 3:
        return False
    page_number_cells = 0
    for row in rows:
        for cell in row.find_all(["td", "th"]):
            t = cell.get_text(strip=True)
            if re.fullmatch(r"\d{1,3}", t):
                page_number_cells += 1
    return page_number_cells >= 3


def _looks_like_signature_block(table: Tag) -> bool:
    text = table.get_text(separator=" ", strip=True)
    score = 0
    for marker in ("By:", "Name:", "Title:", "/s/", "Signature"):
        if marker in text:
            score += 1
    # A real signature block typically has multiple of these markers.
    return score >= 2


def _looks_like_single_clause_wrapper(table: Tag) -> bool:
    """One row, one cell with short text content."""
    rows = table.find_all("tr")
    if len(rows) != 1:
        return False
    cells = rows[0].find_all(["td", "th"])
    if len(cells) > 2:
        return False
    text = table.get_text(strip=True)
    # Short content, no nested headings.
    return len(text) < 200 and not table.find(["h1", "h2", "h3", "h4"])


def _looks_like_decorative(table: Tag) -> bool:
    """All cells empty or whitespace-only."""
    text = re.sub(r"[\s\xa0]+", "", table.get_text())
    return text == ""


def _looks_like_page_number_table(table: Tag) -> bool:
    """A 1-row, 2-or-3-cell table whose only non-empty cell contains a
    small integer (the page number). Pandoc renders these as dash-grid
    markdown tables that bleed into the body text."""
    rows = table.find_all("tr")
    if len(rows) != 1:
        return False
    non_empty = []
    for cell in rows[0].find_all(["td", "th"]):
        t = cell.get_text(strip=True)
        if t and t.replace("\xa0", "").strip():
            non_empty.append(t.replace("\xa0", "").strip())
    if len(non_empty) != 1:
        return False
    return bool(re.fullmatch(r"\d{1,4}", non_empty[0]))


def strip_layout_tables(soup: BeautifulSoup) -> dict:
    counts = {
        "toc": 0, "signature": 0, "single_clause": 0,
        "decorative": 0, "page_number": 0,
    }
    # Iterate over a snapshot since we'll mutate.
    for table in list(soup.find_all("table")):
        if not table.parent:
            continue
        if _looks_like_page_number_table(table):
            table.decompose()
            counts["page_number"] += 1
            continue
        if _looks_like_toc_table(table):
            table.decompose()
            counts["toc"] += 1
            continue
        if _looks_like_signature_block(table):
            # Convert to plain paragraphs rather than discarding entirely.
            new_div = soup.new_tag("div")
            for cell in table.find_all(["td", "th"]):
                cell_text = cell.get_text(separator=" ", strip=True)
                if cell_text:
                    p = soup.new_tag("p")
                    p.string = cell_text
                    new_div.append(p)
            table.replace_with(new_div)
            counts["signature"] += 1
            continue
        if _looks_like_decorative(table):
            table.decompose()
            counts["decorative"] += 1
            continue
        if _looks_like_single_clause_wrapper(table):
            # Unwrap: replace the table with its inner text wrapped in <p>.
            inner_text = table.get_text(separator=" ", strip=True)
            if inner_text:
                p = soup.new_tag("p")
                p.string = inner_text
                table.replace_with(p)
            else:
                table.decompose()
            counts["single_clause"] += 1
            continue
    return counts


def strip_visual_styling(soup: BeautifulSoup) -> int:
    """Strip <font> tags entirely (unwrap, keep children). Strip style
    attribute from <span> and <div> outside <table> blocks. Strip
    cellpadding / cellspacing / width / bgcolor decorative attributes
    from any element outside <table> blocks. Inside tables we leave
    styling alone so substantive tables survive."""
    stripped = 0
    for font in soup.find_all("font"):
        font.unwrap()
        stripped += 1
    for tag in soup.find_all(["span", "div"]):
        if _is_inside_table(tag):
            continue
        if "style" in tag.attrs:
            del tag.attrs["style"]
            stripped += 1
        if "class" in tag.attrs:
            del tag.attrs["class"]
            stripped += 1
    return stripped


def _is_page_break_signal(el) -> bool:
    """An element that pandoc would treat as a page-break artifact: the
    PB anchor span, the <hr> separator, an integer-only <p> page number,
    a Table-of-Contents backlink <p>, an NBSP/empty filler <p>, a
    <br style="page-break-...">, or a wrapper <div> containing only one
    of these."""
    if isinstance(el, NavigableString):
        return el.strip() == ""
    if not isinstance(el, Tag):
        return False
    if el.name == "hr":
        return True
    if el.name == "a":
        ident = (el.get("name") or el.get("id") or "").lower()
        if ident.startswith("pb_"):
            return True
    if el.name == "br":
        if "page-break" in (el.get("style") or "").lower():
            return True
    if el.name == "p":
        text = el.get_text(strip=True)
        if not text:
            return True
        if re.fullmatch(r"\d{1,3}", text):
            return True
        a = el.find("a", href=True)
        if a and (a.get("href") or "").lower() in ("#toc", "#table_of_contents", "#table-of-contents"):
            inner = a.get_text(strip=True).lower()
            if "table of contents" in inner or "back to top" in inner:
                return True
    if el.name == "div":
        children = [
            c for c in el.children
            if not (isinstance(c, NavigableString) and c.strip() == "")
        ]
        if len(children) == 0:
            return True
        if len(children) == 1 and isinstance(children[0], Tag):
            inner = children[0]
            if inner.name == "hr":
                return True
            if inner.name == "a":
                ident = (inner.get("name") or inner.get("id") or "").lower()
                if ident.startswith("pb_"):
                    return True
    return False


def _is_substantive_p(el) -> bool:
    if not isinstance(el, Tag) or el.name != "p":
        return False
    text = el.get_text(separator=" ", strip=True)
    if not text or text.isdigit():
        return False
    return len(text) >= 5


def _is_css_page_break_div(tag: Tag) -> bool:
    """Recognize the SEC CSS-based page-break convention: a <div> whose
    style attribute encodes a CSS page break (`break-before: page`,
    `page-break-before: ...`) or a visual horizontal rule
    (`border-bottom: ... solid`), AND whose own text content is
    whitespace-only (an empty placeholder, not a content wrapper)."""
    if tag.name != "div":
        return False
    style = (tag.get("style") or "").lower()
    if not style:
        return False
    has_break = (
        "break-before: page" in style
        or "break-after: page" in style
        or "page-break-before:" in style
        or "page-break-after:" in style
    )
    has_border_rule = "border-bottom:" in style and "solid" in style
    if not (has_break or has_border_rule):
        return False
    text = tag.get_text(strip=True).replace("\xa0", "")
    return text == ""


def _find_page_break_signal_tags(soup: BeautifulSoup) -> list[Tag]:
    """Return every page-break leaf signal in document order.

    Leaf signals are individual tags, not wrappers: an <hr>, a
    `<a name="PB_*">` empty anchor, a `<br style="page-break-...">`, an
    integer-only <p>, or an empty <div> carrying the SEC CSS convention
    (`break-before: page`, `page-break-before:`, or `border-bottom:
    ... solid`). Wrappers like <div><hr></div> are not returned
    separately because the inner <hr> covers that case."""
    signals: list[Tag] = []
    for tag in soup.find_all(True):
        if not tag.parent:
            continue
        if tag.name == "hr":
            signals.append(tag)
        elif tag.name == "a":
            ident = (tag.get("name") or tag.get("id") or "").lower()
            if ident.startswith("pb_"):
                signals.append(tag)
        elif tag.name == "br":
            if "page-break" in (tag.get("style") or "").lower():
                signals.append(tag)
        elif tag.name == "p":
            text = tag.get_text(strip=True)
            # Page-number variants: bare integer (`9`), dash-bracketed
            # (`-9-`), roman numeral (`iv`, `-iv-`), often used as folio
            # markers in Cibus-style filings.
            if text and re.fullmatch(
                r"-?\d{1,3}-?|-?[ivxlcdm]+-?",
                text,
                re.IGNORECASE,
            ):
                signals.append(tag)
        elif tag.name == "div":
            if _is_css_page_break_div(tag):
                signals.append(tag)
    return signals


def _prev_substantive_p_in_doc_order(start: Tag) -> Tag | None:
    """Walk previous_element backward across the entire document tree;
    return the first substantive <p>. Abort (return None) if a heading
    is encountered first, since that signals a section boundary."""
    el = start.previous_element
    while el is not None:
        if isinstance(el, Tag):
            if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                return None
            if _is_inside_table(el):
                pass
            elif el.name == "p" and _is_substantive_p(el):
                return el
        el = el.previous_element
    return None


def _next_substantive_p_in_doc_order(start: Tag) -> Tag | None:
    el = start.next_element
    while el is not None:
        if isinstance(el, Tag):
            if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                return None
            if _is_inside_table(el):
                pass
            elif el.name == "p" and _is_substantive_p(el):
                return el
        el = el.next_element
    return None


def merge_split_paragraphs(soup: BeautifulSoup) -> int:
    """Rejoin paragraphs that pandoc chunked across SEC page breaks.

    Approach: walk every page-break signal in the document. For each, find
    the substantive <p> immediately preceding and following in document
    order (crosses <div> boundaries naturally). If the preceding <p> does
    not end in sentence-terminating punctuation, splice the following <p>
    into it. Iterates until no more merges occur (handles paragraphs
    chunked across 3+ page boundaries).

    Paragraph splits in SEC HTML are essentially always page-break-induced,
    so walking from the signal outward is more reliable than walking from
    paragraphs and guessing whether their endings look interrupted."""
    total_merged = 0
    while True:
        merged_this_pass = 0
        for sig in _find_page_break_signal_tags(soup):
            if not sig.parent or _is_inside_table(sig):
                continue
            preceding = _prev_substantive_p_in_doc_order(sig)
            if preceding is None:
                continue
            following = _next_substantive_p_in_doc_order(sig)
            if following is None:
                continue
            ptext = preceding.get_text(separator=" ", strip=True)
            if SENTENCE_END_RE.search(ptext):
                continue
            preceding.append(" ")
            for child in list(following.children):
                preceding.append(
                    child.extract() if isinstance(child, Tag) else child
                )
            following.decompose()
            merged_this_pass += 1
        if merged_this_pass == 0:
            break
        total_merged += merged_this_pass
    return total_merged


BLOCK_TAG_NAMES = {
    "p", "div", "table", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre",
}


def consolidate_title_block(soup: BeautifulSoup) -> int:
    """Replace the leading run of consecutive centered paragraphs (the
    title block: exhibit identifier, document title, parties, date) with
    a single <h1> + supporting subtitle <p>.

    Heuristic: walk <p>/<div> elements in document order. Collect
    centered ones until we hit a substantial non-centered paragraph
    (the parties paragraph). Within the collected block, the principal
    title is the first line containing the word AGREEMENT (case-
    insensitive) of length 10-80 chars. Remaining lines become a
    single subtitle paragraph joined by ' | '.

    Must run BEFORE strip_visual_styling (depends on the centering
    signal) and BEFORE promote_centered_section_headers (so it does
    not need to skip-count the title block).
    """
    body = soup.body or soup
    candidates: list[tuple[Tag, str]] = []
    for el in body.find_all(["p", "div"]):
        if not el.parent or _is_inside_table(el):
            continue
        text = re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True))
        if not text:
            continue
        candidates.append((el, text))

    # Title block stops at a centered structural marker (TABLE OF CONTENTS,
    # RECITALS, WITNESSETH, ARTICLE N, etc.); those are section breaks, not
    # supporting context for the document title.
    section_stop_re = re.compile(
        r"^(TABLE OF CONTENTS|RECITALS|WITNESSETH|SIGNATURES?|ARTICLE\s+[IVXLCDM]+)",
        re.IGNORECASE,
    )
    title_block: list[tuple[Tag, str]] = []
    started = False
    for el, text in candidates:
        if _is_centered(el):
            if section_stop_re.match(text):
                break
            title_block.append((el, text))
            started = True
        else:
            if started and len(text) > 50:
                break
            continue
        if len(title_block) > 25:
            break

    if len(title_block) < 1:
        return 0

    principal_idx = None
    for i, (_el, text) in enumerate(title_block):
        if (re.search(r"\bAGREEMENT\b", text, re.IGNORECASE)
                and 10 <= len(text) <= 80):
            principal_idx = i
            break
    if principal_idx is None:
        return 0

    principal_text = title_block[principal_idx][1]
    connector_re = re.compile(
        r"^(and|or|between|among|by and among|with|by|as|the|of|in|to|"
        r"dated|dated as of|dated as|as of)\.?$",
        re.IGNORECASE,
    )
    principal_lower = principal_text.lower()
    subtitle_lines: list[str] = []
    for i, (_el, text) in enumerate(title_block):
        if i == principal_idx:
            continue
        # Drop connector-only fragments (and, between, by and among, ...).
        if connector_re.match(text):
            continue
        # Drop later occurrences whose text is a substring of the principal
        # (case-insensitive) — handles `TAX RECEIVABLE AGREEMENT` appearing
        # both with and without a parenthetical modifier in the same block.
        if text.lower() in principal_lower or principal_lower in text.lower():
            continue
        subtitle_lines.append(text)

    h1 = soup.new_tag("h1")
    h1.string = principal_text
    subtitle_p = None
    if subtitle_lines:
        subtitle_p = soup.new_tag("p")
        # Trail with a period so the page-break merger does not treat the
        # subtitle's missing terminator as a split-paragraph signal and
        # absorb the next (parties) paragraph into the subtitle.
        joined = " · ".join(subtitle_lines)
        if not joined.endswith("."):
            joined = joined + "."
        subtitle_p.string = joined

    first_el = title_block[0][0]
    first_el.insert_before(h1)
    if subtitle_p:
        h1.insert_after(subtitle_p)
    for el, _ in title_block:
        if el.parent:
            el.decompose()
    return 1


def _is_centered(tag: Tag) -> bool:
    style = (tag.get("style") or "").lower()
    if "text-align" in style and "center" in style:
        return True
    if (tag.get("align") or "").lower() == "center":
        return True
    return False


# A short, all-caps phrase suitable for a standalone section header.
# Rules: 1-4 words, all upper-case alphabetic plus optional colon, no commas
# or periods (those signal company names or sentence fragments like
# "NOW, THEREFORE").
SECTION_HEADER_CANDIDATE_RE = re.compile(
    r"^[A-Z][A-Z' \-/&]{2,40}[A-Z](?::)?$",
)


def promote_centered_section_headers(soup: BeautifulSoup) -> int:
    """Promote standalone centered short ALL-CAPS paragraphs to <h2>.

    SEC TRA filings consistently center words like RECITALS, WITNESSETH,
    and SIGNATURES as section breaks. The opening title block is also
    centered (multiple consecutive centered paragraphs); we skip those by
    waiting until we see at least one non-centered substantive paragraph
    (the parties paragraph) before starting promotion.

    Must run BEFORE strip_visual_styling, since the `text-align:center`
    style attribute is the signal we depend on.
    """
    promoted = 0
    used_slugs: set[str] = set()
    title_block_ended = False
    prev_centered_was_article = False

    for tag in list(soup.find_all(["p", "div"])):
        if not tag.parent or _is_inside_table(tag):
            continue
        text = re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True))
        if not text:
            continue
        # End of title block: first non-centered substantive paragraph.
        if not title_block_ended:
            if not _is_centered(tag) and len(text) > 50:
                title_block_ended = True
            continue
        if not _is_centered(tag):
            prev_centered_was_article = False
            continue
        # Track ARTICLE markers and skip the centered-promo on this element
        # and the next centered element (which is the article title that
        # promote_strong_headings will merge into the ARTICLE heading).
        if ARTICLE_INLINE_RE.match(text) or ARTICLE_BARE_RE.match(text):
            prev_centered_was_article = True
            continue
        if prev_centered_was_article:
            # This centered element is the article title; leave it alone.
            prev_centered_was_article = False
            continue
        # Skip elements already covered by SECTION/SCHEDULE/EXHIBIT.
        if (SECTION_INLINE_RE.match(text)
                or SCHEDULE_INLINE_RE.match(text)
                or EXHIBIT_INLINE_RE.match(text)):
            continue
        if not SECTION_HEADER_CANDIDATE_RE.match(text):
            continue
        word_count = len(text.split())
        if word_count > 4:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        if not slug or slug in used_slugs:
            continue
        used_slugs.add(slug)
        _replace_with_heading(soup, tag, 2, slug, text.rstrip(":"))
        promoted += 1
    return promoted


def normalize_content_divs_to_paragraphs(soup: BeautifulSoup) -> int:
    """Convert each <div> whose direct children are all inline elements
    (no nested <p>, <div>, <table>, headings, lists, et cetera) into a
    <p> element. Some SEC filings (Dutch Bros, modern Edgar HTML)
    render every content block as <div>, which downstream heading-
    promotion and paragraph-merging logic does not recognize."""
    converted = 0
    for div in list(soup.find_all("div")):
        if not div.parent or _is_inside_table(div):
            continue
        # If any direct child is itself a block element, leave the div as-is.
        has_block_child = any(
            (isinstance(c, Tag) and c.name in BLOCK_TAG_NAMES)
            for c in div.children
        )
        if has_block_child:
            continue
        # Convert to <p>.
        new_p = soup.new_tag("p")
        for child in list(div.children):
            new_p.append(child.extract() if isinstance(child, Tag) else child)
        div.replace_with(new_p)
        converted += 1
    return converted


def preprocess(html_text: str) -> tuple[str, dict]:
    soup = _parse(html_text)
    stats = {}
    # Consolidate the leading title block into a single <h1> + subtitle <p>.
    # Runs BEFORE the styling strip so the centering signal is intact.
    stats["title_block_consolidated"] = consolidate_title_block(soup)
    # Promote centered standalone section headers (RECITALS, WITNESSETH)
    # while the `text-align:center` style attribute is still available.
    stats["centered_headers_promoted"] = promote_centered_section_headers(soup)
    # Convert content-only <div>s to <p>s so heading promotion, page-break
    # detection, and paragraph merging can find them (some SEC filings,
    # like Dutch Bros, render every block as <div>). Page-break <div>s
    # (which contain inner <p>&nbsp;</p>) survive this step because they
    # have block-level children.
    stats["divs_converted_to_p"] = normalize_content_divs_to_paragraphs(soup)
    # Merge paragraphs split across page boundaries BEFORE stripping
    # styling. The CSS page-break convention (style="break-before: page",
    # style="border-bottom: ... solid") is the only signal in some SEC
    # filings (e.g., wm-technology), and strip_visual_styling would
    # remove it.
    stats["paragraphs_merged"] = merge_split_paragraphs(soup)
    # Now safe to strip <font> tags and inline div/span styles.
    stats["styling_stripped"] = strip_visual_styling(soup)
    # Strip page-break debris after div-to-p conversion so integer-only
    # <div>N</div> page numbers get caught.
    stats["page_break_removed"] = strip_page_break_artifacts(soup)
    stats["headings_promoted"] = promote_strong_headings(soup)
    stats["inline_articles_promoted"] = promote_inline_article_markers(soup)
    stats["tables_stripped"] = strip_layout_tables(soup)
    return str(soup), stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preprocess SEC EDGAR TRA HTML for pandoc conversion.",
    )
    parser.add_argument("input", help="Input .htm or .html file.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-o", "--output", help="Write preprocessed HTML to this path.")
    group.add_argument("--in-place", action="store_true",
                       help="Rewrite the input file.")
    args = parser.parse_args()

    html_text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    new_html, stats = preprocess(html_text)
    output_path = Path(args.input if args.in_place else args.output)
    output_path.write_text(new_html, encoding="utf-8")

    print(f"Title block consolidated: {stats['title_block_consolidated']}")
    print(f"Centered section headers promoted: {stats['centered_headers_promoted']}")
    print(f"Page-break artifacts removed: {stats['page_break_removed']}")
    print(f"Content <div>s converted to <p>: {stats['divs_converted_to_p']}")
    print(f"Headings promoted: {stats['headings_promoted']}")
    print(f"Inline ARTICLE markers promoted: {stats['inline_articles_promoted']}")
    print(
        f"Layout tables stripped: toc={stats['tables_stripped']['toc']}, "
        f"signature={stats['tables_stripped']['signature']}, "
        f"single_clause={stats['tables_stripped']['single_clause']}, "
        f"decorative={stats['tables_stripped']['decorative']}, "
        f"page_number={stats['tables_stripped']['page_number']}"
    )
    print(f"Visual-styling attributes/tags stripped: {stats['styling_stripped']}")
    print(f"Atomized paragraphs merged: {stats['paragraphs_merged']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
