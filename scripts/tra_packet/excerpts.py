"""Plain-text-near-TRA-mention excerpter with non-GAAP table exclusion.

For each TRA mention in a filing body, emit a window of stripped
plain text around it. Matches that fall inside a non-GAAP
reconciliation table are dropped, because those tables produced the
false-positive "tax receivable agreement (benefit) expense" hits the
prior cancel-proximity regex was catching.

The output for a filing is saved alongside the cached HTML, at
``.tra_history_cache/edgar_archives/<CIK>/<accession>/<filename>.tra_excerpts.txt``.
The skill's reviewer agent loads this file rather than re-stripping
HTML on every navigation.

Format: one excerpt per blank-line-separated block, prefixed by a
metadata header line: ``[offset=<int> in_table=<bool> heading_hint=<str>]``.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

ARCHIVES_CACHE = Path(".tra_history_cache/edgar_archives")

_TRA_PATTERN = re.compile(r"(?i)tax\s+receivables?\s+agreements?")

# Phrases that, when they appear as a recent heading or as a caption
# above the TRA mention, indicate the mention is inside a non-GAAP
# reconciliation table. Drop the excerpt in that case.
_NON_GAAP_HEADERS = (
    r"adjusted\s+ebitda",
    r"adjusted\s+net\s+income",
    r"adjusted\s+earnings",
    r"adjusted\s+operating\s+income",
    r"reconciliation\s+of\s+",
    r"non[\s\-]gaap\s+(?:measures?|reconciliation)",
    r"non[\s\-]gaap\s+financial\s+measures?",
    r"reconciliation\s+to\s+(?:gaap|adjusted)",
    r"ebitda\s+reconciliation",
    r"definition\s+of\s+adjusted",
    r"summary\s+of\s+non[\s\-]gaap",
)
_NON_GAAP_RE = re.compile(
    r"(?i)(" + "|".join(_NON_GAAP_HEADERS) + r")"
)


def _strip_html(body: str) -> str:
    """HTML to plain text. Drops <script>, <style>, and <table>-tagged
    table tags' structure (keeps cell text). Decodes entities. Collapses
    whitespace. Does NOT preserve heading structure; the
    non-GAAP-table check operates on the stripped text directly.
    """
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    # Replace block-level tags with newlines so the table-context
    # detector can find recent headings via line-wise scanning.
    text = re.sub(
        r"(?i)</?(p|div|tr|h[1-6]|li|br|table)[^>]*>", "\n", text
    )
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    # Collapse runs of spaces but preserve newlines so line-wise
    # context retrieval works.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class Excerpt:
    offset: int  # char offset within the stripped text
    text: str
    in_non_gaap_table: bool
    heading_hint: str | None  # nearest preceding short ALL-CAPS or
    # title-cased line that could be a section header


def _find_heading_hint(text: str, position: int, look_back: int = 1500) -> str | None:
    """Walk backward from ``position`` looking for the nearest line
    that resembles a section heading. Heuristic: a line of 4 to 120
    characters that is either ALL CAPS or Title Case Without Trailing
    Punctuation. Returns the line text or None.
    """
    start = max(0, position - look_back)
    window = text[start:position]
    lines = window.split("\n")
    for line in reversed(lines[:-1]):
        s = line.strip()
        if 4 <= len(s) <= 120 and not s.endswith(("."  , ":", ";", ",")):
            # All caps or title case (most words start uppercase).
            words = s.split()
            if not words:
                continue
            if s == s.upper() and any(c.isalpha() for c in s):
                return s
            cap_words = [w for w in words if w[0:1].isupper()]
            if len(cap_words) >= max(1, int(0.6 * len(words))):
                return s
    return None


def _is_in_non_gaap_table(text: str, position: int, look_back: int = 800) -> bool:
    """Return True if a non-GAAP heading appears within the immediate
    context preceding ``position``. The window is shorter than the
    heading-hint window because non-GAAP tables tend to live close to
    their captions.
    """
    start = max(0, position - look_back)
    window = text[start:position]
    return _NON_GAAP_RE.search(window) is not None


def extract_tra_excerpts(
    body: str,
    window_chars: int = 600,
) -> list[Excerpt]:
    """Return one :class:`Excerpt` per TRA mention in the body.

    Excerpts inside non-GAAP reconciliation tables carry
    ``in_non_gaap_table=True`` rather than being dropped silently;
    the caller decides whether to filter them.
    """
    if not body:
        return []
    text = _strip_html(body)
    out: list[Excerpt] = []
    for m in _TRA_PATTERN.finditer(text):
        a = max(0, m.start() - window_chars // 2)
        b = min(len(text), m.end() + window_chars // 2)
        chunk = text[a:b]
        chunk = re.sub(r"\s+", " ", chunk).strip()
        out.append(Excerpt(
            offset=m.start(),
            text=chunk,
            in_non_gaap_table=_is_in_non_gaap_table(text, m.start()),
            heading_hint=_find_heading_hint(text, m.start()),
        ))
    return out


def cache_path_for(cik_unpadded: str, accession: str, filename: str) -> Path:
    acc_nd = accession.replace("-", "")
    return ARCHIVES_CACHE / cik_unpadded / acc_nd / f"{filename}.tra_excerpts.txt"


def write_excerpts_to_cache(
    cik_unpadded: str,
    accession: str,
    filename: str,
    excerpts: list[Excerpt],
) -> Path:
    """Write excerpts to the per-filing cache file. Returns the path."""
    p = cache_path_for(cik_unpadded, accession, filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# {len(excerpts)} TRA mention(s); window=600 chars")
    lines.append(
        "# format: blank-line-separated blocks; each starts with "
        "[offset=N in_table=BOOL heading_hint='HEADING_OR_NONE']"
    )
    lines.append("")
    for ex in excerpts:
        h = ex.heading_hint.replace("'", "’") if ex.heading_hint else "None"
        lines.append(
            f"[offset={ex.offset} in_table={ex.in_non_gaap_table} heading_hint='{h}']"
        )
        lines.append(ex.text)
        lines.append("")
    p.write_text("\n".join(lines))
    return p


def excerpts_filtered(excerpts: list[Excerpt]) -> list[Excerpt]:
    """Convenience: return only excerpts NOT in a non-GAAP table."""
    return [e for e in excerpts if not e.in_non_gaap_table]
