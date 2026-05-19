"""TOC (table of contents) anchor pre-extraction.

For each cached filing, parse the HTML and extract a list of
``(heading_text, line_offset, char_offset, anchor_id)`` triples. The
output is saved alongside the cached HTML at
``.tra_history_cache/edgar_archives/<CIK>/<accession>/<filename>.toc.tsv``.

The skill's reviewer agent loads this TSV when navigating a filing
rather than re-parsing the HTML body each time. Modern iXBRL filings
include explicit ``<a name="...">`` or ``<a id="...">`` anchors at
each section heading; older filings may have heading text without
anchors and the agent falls back to text search.

Extraction strategy:

- Find every ``<h1>``..``<h6>`` element and capture its text + the
  nearest preceding or enclosing anchor id.
- Find every ``<a name="X">`` and ``<a id="X">`` and capture the
  text in the next ~120 chars (the heading text usually follows the
  anchor immediately in EDGAR HTML conventions).
- Find typographic heading candidates: lines wrapped in
  ``<font size="X">``, ``<span style="...font-size...">``, or with
  ``<b>``/``<strong>``, when their text is 4 to 200 characters and
  ends without sentence punctuation.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

ARCHIVES_CACHE = Path(".tra_history_cache/edgar_archives")


@dataclass
class TocEntry:
    heading: str
    char_offset: int  # offset within the raw HTML
    anchor_id: str | None
    source: str  # "h_tag" | "named_anchor" | "typographic"


_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(s: str) -> str:
    s = _TAG_STRIP_RE.sub(" ", s)
    s = html.unescape(s)
    s = _WS_RE.sub(" ", s).strip()
    return s


# Match <hN>...</hN> with optional nested anchor id.
_H_RE = re.compile(
    r"(?is)<h([1-6])(?P<attrs>[^>]*)>(?P<body>.*?)</h\1>"
)

# Match <a name="X"> or <a id="X">, the kind of EDGAR section anchor
# that is followed shortly by the heading text.
_ANCHOR_RE = re.compile(
    r"(?is)<a[^>]*?(?:name|id)\s*=\s*[\"']([^\"']+)[\"'][^>]*>"
)

# Typographic heading candidate: large <font size="N"> or
# <span style="...font-size:Xpx..."> blocks, or <b>/<strong>.
_TYPOGRAPHIC_RE = re.compile(
    r"(?is)"
    r"<(?:font\s+size\s*=\s*[\"']?(?:[4-7]|\+\d)[\"']?[^>]*"
    r"|span[^>]*?font-size\s*:\s*1[2-9]p[txt]"
    r"|span[^>]*?font-size\s*:\s*[2-9]\dp[txt]"
    r"|b\b|strong\b)"
    r"[^>]*>(?P<body>.{1,300}?)</(?:font|span|b|strong)>"
)


def _attr_id(attrs: str) -> str | None:
    m = re.search(r"""(?i)(?:name|id)\s*=\s*[\"']([^\"']+)[\"']""", attrs)
    return m.group(1) if m else None


def extract_toc(body: str) -> list[TocEntry]:
    """Walk the HTML body and return TOC entries in document order."""
    if not body:
        return []

    out: list[TocEntry] = []

    # 1. <hN> headings.
    for m in _H_RE.finditer(body):
        text = _clean_text(m.group("body"))
        if not (3 <= len(text) <= 250):
            continue
        anchor = _attr_id(m.group("attrs") or "")
        if anchor is None:
            anchor = _attr_id(m.group("body") or "")
        out.append(TocEntry(
            heading=text,
            char_offset=m.start(),
            anchor_id=anchor,
            source="h_tag",
        ))

    # 2. <a name="...">/<a id="..."> immediately followed by short text.
    for m in _ANCHOR_RE.finditer(body):
        anchor = m.group(1)
        tail = body[m.end():m.end() + 400]
        text = _clean_text(tail)
        if not text:
            continue
        text = text[:200].strip()
        if not (3 <= len(text) <= 200):
            continue
        if "." in text.split()[0]:  # filename-shaped anchors skip
            continue
        out.append(TocEntry(
            heading=text,
            char_offset=m.start(),
            anchor_id=anchor,
            source="named_anchor",
        ))

    # 3. Typographic heading candidates. Filter to those that look like
    # a heading (short, no trailing punctuation, mostly capitalized).
    for m in _TYPOGRAPHIC_RE.finditer(body):
        text = _clean_text(m.group("body"))
        if not (4 <= len(text) <= 150):
            continue
        if text.endswith((".", ":", ";", ",")):
            continue
        words = text.split()
        if not words:
            continue
        cap_ratio = sum(1 for w in words if w[0:1].isupper()) / len(words)
        if text == text.upper():
            pass
        elif cap_ratio < 0.6:
            continue
        out.append(TocEntry(
            heading=text,
            char_offset=m.start(),
            anchor_id=None,
            source="typographic",
        ))

    # Sort by char_offset and dedupe near-duplicates (same heading
    # within 500 chars).
    out.sort(key=lambda e: e.char_offset)
    deduped: list[TocEntry] = []
    for e in out:
        if deduped:
            last = deduped[-1]
            if (
                last.heading.lower() == e.heading.lower()
                and abs(e.char_offset - last.char_offset) < 500
            ):
                # Keep the entry with the anchor_id if available.
                if last.anchor_id is None and e.anchor_id is not None:
                    deduped[-1] = e
                continue
        deduped.append(e)
    return deduped


def cache_path_for(cik_unpadded: str, accession: str, filename: str) -> Path:
    acc_nd = accession.replace("-", "")
    return ARCHIVES_CACHE / cik_unpadded / acc_nd / f"{filename}.toc.tsv"


def write_toc_to_cache(
    cik_unpadded: str,
    accession: str,
    filename: str,
    entries: list[TocEntry],
) -> Path:
    p = cache_path_for(cik_unpadded, accession, filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["heading\tchar_offset\tanchor_id\tsource"]
    for e in entries:
        h = e.heading.replace("\t", " ").replace("\n", " ")
        a = e.anchor_id or ""
        lines.append(f"{h}\t{e.char_offset}\t{a}\t{e.source}")
    p.write_text("\n".join(lines) + "\n")
    return p
