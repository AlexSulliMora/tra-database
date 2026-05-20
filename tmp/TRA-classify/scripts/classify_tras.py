#!/usr/bin/env python3
"""Filter a directory of SEC EX-10.* exhibits down to plausible Tax
Receivable Agreements (TRAs).

Given a source directory, recursively finds every exhibit file
(``.htm``, ``.html``, ``.txt``, ``.pdf``), classifies each as "definitely
not a TRA" (drop) or "needs manual review" (keep), and writes the
keep-list to a CSV. ``.txt`` filings are keyword-scanned in place;
``.pdf`` exhibits cannot be keyword-scanned without text extraction and
are routed straight to the keep-list. The filter is deliberately
conservative: a false drop discards a real TRA (the costly error), a
false keep just adds one file to the manual-review pile. The logic
therefore favors recall.

Distinguishing signals (learned from 5 confirmed reference TRAs vs. an
18-file random EX-10 contrast set):

1. Centered title block. A contract opens with a run of centered lines
   (exhibit identifier, document title, parties, date) ending at the first
   long left-aligned paragraph. A TRA's centered title block contains the
   phrase "TAX RECEIVABLE AGREEMENT". This is the strongest, cheapest
   signal: every reference TRA had it; no contrast-set file did.
2. Phrase presence. "tax receivable agreement" appearing anywhere in the
   document is a weaker cue (credit agreements and proxies mention TRAs
   without being one). Used only as a fallback when the title block could
   not be parsed.
3. Defining terminology. TRA-specific defined terms ("Realized Tax
   Benefit", "Exchange Basis Schedule", "Tax Benefit Schedule", "Early
   Termination Payment", etc.). Used as corroboration.
4. Disqualifying titles. If the centered title is a clearly different
   instrument (credit agreement, employment agreement, RSU/incentive
   plan, LLC operating agreement, exchange agreement, ...) and shows no
   TRA phrase, drop.
5. File-size bounds. Real TRAs in the reference corpus run roughly
   40 kB-260 kB. Tiny files (under ~8 kB) are too short to be a full
   contract; multi-megabyte files are large filings (credit agreements,
   S-4s) -- but a large file is only dropped when it ALSO lacks the TRA
   phrase entirely, since a TRA can be embedded in a bigger filing.

WSL safety: large HTML files are never read fully. The title check reads
only a bounded leading window (TITLE_WINDOW_BYTES); the phrase / term
scan reads a larger but still bounded window (SCAN_WINDOW_BYTES).

Usage:
    pixi run -- python classify_tras.py <source_dir> [-o <keeplist.csv>]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

# Random seed derived from today's date (2026-05-19). No sampling happens
# in this script, but the project rule fixes a non-42 seed from the date.
SEED = 20260519

# --- bounded read windows (WSL crash guard) -------------------------------
TITLE_WINDOW_BYTES = 80_000   # leading slice scanned for the centered title
SCAN_WINDOW_BYTES = 400_000   # leading slice scanned for phrase / terms

# --- file-size bounds -----------------------------------------------------
# Reference TRAs ran 116 kB-192 kB; corpus TRAs go smaller (short
# amendments and waivers) and somewhat larger. Bounds are generous: size
# only ever contributes to a drop in combination with other negative
# signals. The smallest confirmed TRA-class instrument in the reference
# corpus (a Veritiv "Amendment No. 1") is ~6.7 kB, so MIN_BYTES sits
# below that and a tiny file is dropped only when it ALSO lacks the TRA
# phrase -- a tiny file with the phrase is still kept.
MIN_BYTES = 4_000             # below this AND no phrase: too short to be a TRA
LARGE_BYTES = 1_200_000       # above this, a big filing; drop only if no phrase

TRA_PHRASE_RE = re.compile(r"tax\s+receivable\s+agreement", re.IGNORECASE)
INCOME_TRA_PHRASE_RE = re.compile(
    r"income\s+tax\s+receivable\s+agreement", re.IGNORECASE
)

# TRA-specific defined terminology (from tra-process-filings SKILL.md,
# "What a Tax Receivable Agreement looks like"). Presence of several of
# these strongly corroborates a TRA.
TRA_TERMS = [
    re.compile(r"realized\s+tax\s+benefit", re.IGNORECASE),
    re.compile(r"hypothetical\s+tax\s+liability", re.IGNORECASE),
    re.compile(r"actual\s+tax\s+liability", re.IGNORECASE),
    re.compile(r"exchange\s+basis\s+schedule", re.IGNORECASE),
    re.compile(r"tax\s+benefit\s+schedule", re.IGNORECASE),
    re.compile(r"net\s+tax\s+benefit\s+payment", re.IGNORECASE),
    re.compile(r"early\s+termination\s+payment", re.IGNORECASE),
    re.compile(r"basis\s+adjustment", re.IGNORECASE),
    re.compile(r"section\s+754\s+election", re.IGNORECASE),
    re.compile(r"pre-?ipo\s+(?:holders|tax\s+assets)", re.IGNORECASE),
]

# Centered titles that name a clearly different instrument. If the title
# block matches one of these AND no TRA phrase appears, drop with high
# confidence. The Up-C-adjacent ones (exchange / registration rights /
# stockholders / LLC / operating partnership agreements) are common
# co-filings with a TRA but are themselves not TRAs.
NON_TRA_TITLE_RES = [
    re.compile(r"\bcredit\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bemployment\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bseparation\b", re.IGNORECASE),
    re.compile(r"\bindemnification\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bclearing\s+services\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bsupport\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bexchange\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bregistration\s+rights\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bstockholders?\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bvoting\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bunit\s+(?:award\s+)?(?:plan|agreement)\b", re.IGNORECASE),
    re.compile(r"\brestricted\s+stock\s+unit\b", re.IGNORECASE),
    re.compile(r"\bincentive\s+plan\b", re.IGNORECASE),
    re.compile(r"\blimited\s+(?:liability\s+company|partnership)\s+agreement\b",
               re.IGNORECASE),
    re.compile(r"\bagreement\s+of\s+limited\s+partnership\b", re.IGNORECASE),
    re.compile(r"\boperating\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bmerger\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bpurchase\s+agreement\b", re.IGNORECASE),
    re.compile(r"\blease\b", re.IGNORECASE),
    re.compile(r"\bpromissory\s+note\b", re.IGNORECASE),
    re.compile(r"\bwarrant\b", re.IGNORECASE),
]

# Connector-only lines inside a centered title block, dropped so the title
# string is the substantive content. Mirrors consolidate_title_block in
# tra-htm-to-md/scripts/preprocess_html.py.
CONNECTOR_RE = re.compile(
    r"^(and|or|between|among|by and among|by and between|with|by|as|the|of|"
    r"in|to|dated|dated as of|dated as|as of|execution\s+version|"
    r"execution\s+copy|form\s+of)\.?$",
    re.IGNORECASE,
)
EXHIBIT_ID_RE = re.compile(r"^(exhibit|ex)[\s\-.]*\d", re.IGNORECASE)
SECTION_STOP_RE = re.compile(
    r"^(table\s+of\s+contents|contents|recitals|witnesseth|signatures?|"
    r"article\s+[ivxlcdm0-9]+)",
    re.IGNORECASE,
)


def is_centered(tag) -> bool:
    """Centering signal: align=center attribute or text-align:center style.

    Mirrors _is_centered in tra-htm-to-md/scripts/preprocess_html.py.
    """
    style = (tag.get("style") or "").lower()
    if "text-align" in style and "center" in style:
        return True
    if (tag.get("align") or "").lower() == "center":
        return True
    return False


def extract_title_block(html_window: str) -> str:
    """Return the centered title block as a single normalized string.

    Walks <p>/<div> elements in document order, collecting the leading run
    of centered ones until a substantial (>50 char) left-aligned paragraph
    is reached -- that left-aligned block is the contract's first operative
    paragraph (the preamble). Connector-only lines and the SEC exhibit
    identifier are dropped. A centered structural marker (TABLE OF
    CONTENTS, RECITALS, ARTICLE N, ...) ends the block.

    Operates on a bounded leading window only; never the whole file.
    """
    soup = BeautifulSoup(html_window, "html.parser")
    body = soup.body or soup

    lines: list[str] = []
    started = False
    for el in body.find_all(["p", "div"]):
        text = re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True))
        if not text:
            continue
        if is_centered(el):
            if SECTION_STOP_RE.match(text):
                break
            if EXHIBIT_ID_RE.match(text) or CONNECTOR_RE.match(text):
                started = True
                continue
            lines.append(text)
            started = True
        else:
            # First substantial left-aligned paragraph ends the title block.
            if started and len(text) > 50:
                break
            continue
        if len(lines) > 25:
            break

    return " | ".join(lines)


def scan_window(path: Path, n_bytes: int) -> str:
    """Read at most n_bytes from a file, decoding leniently."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read(n_bytes)


def classify_file(path: Path) -> dict:
    """Classify one exhibit file. Returns a record with the computed
    signals and a keep/drop decision.

    Handles three exhibit file types:
      - .htm / .html / .txt: keyword-scannable. The centered-title parse
        and the phrase / term scan run as normal. A .txt filing has no
        HTML <p> tags so the title block comes back empty, but the
        phrase and defined-term scan still apply.
      - .pdf: not keyword-scannable without text extraction. Routed
        straight to KEEP (needs manual review) so it is never dropped
        unseen.

    Decision rules for keyword-scannable files, in order:
      1. Title block contains "tax receivable agreement": KEEP.
      2. Title block names a clearly different instrument AND no TRA
         phrase anywhere in the scanned window: drop.
      3. TRA phrase present anywhere: KEEP (covers files whose centered
         title could not be parsed, embedded TRAs, and short amendments
         or waivers).
      4. >= 3 TRA-specific defined terms present: KEEP (phrase-free
         corroboration -- conservative safety net).
      5. Tiny file (< MIN_BYTES) with no TRA phrase: drop -- too short to
         be a full contract. Checked only after the phrase test, so a
         short TRA amendment that mentions the phrase still survives.
      6. Very large file (> LARGE_BYTES) with no TRA phrase and no terms:
         drop -- a big non-TRA filing.
      7. Otherwise: drop -- no positive TRA signal found.
    """
    size = path.stat().st_size

    rec: dict = {
        "path": str(path),
        "size_bytes": size,
        "title_block": "",
        "title_has_tra": False,
        "title_is_non_tra": False,
        "phrase_present": False,
        "income_tra_phrase": False,
        "tra_term_count": 0,
        "decision": "",
        "reason": "",
    }

    # PDF exhibits cannot be keyword-scanned without text extraction.
    # Route them straight to the manual-review keep-list rather than
    # drop them unseen.
    if path.suffix.lower() == ".pdf":
        rec["decision"] = "keep"
        rec["reason"] = "PDF exhibit; not keyword-scannable, needs manual review"
        return rec

    title_window = scan_window(path, TITLE_WINDOW_BYTES)
    title = extract_title_block(title_window)
    rec["title_block"] = title[:300]
    title_has_tra = bool(TRA_PHRASE_RE.search(title))
    title_is_non_tra = any(r.search(title) for r in NON_TRA_TITLE_RES)
    rec["title_has_tra"] = title_has_tra
    rec["title_is_non_tra"] = title_is_non_tra and not title_has_tra

    scan_text = scan_window(path, SCAN_WINDOW_BYTES)
    phrase_present = bool(TRA_PHRASE_RE.search(scan_text))
    rec["phrase_present"] = phrase_present
    rec["income_tra_phrase"] = bool(INCOME_TRA_PHRASE_RE.search(scan_text))
    term_count = sum(1 for r in TRA_TERMS if r.search(scan_text))
    rec["tra_term_count"] = term_count

    # Rule 1: centered title says it is a TRA -- strongest signal.
    if title_has_tra:
        rec["decision"] = "keep"
        rec["reason"] = "centered title contains 'tax receivable agreement'"
        return rec

    # Rule 2: title names a different instrument and no TRA phrase at all.
    if rec["title_is_non_tra"] and not phrase_present:
        rec["decision"] = "drop"
        rec["reason"] = "title names a non-TRA instrument; no TRA phrase"
        return rec

    # Rule 3: phrase present anywhere -- keep (title parse may have failed,
    # or the TRA is embedded in a larger filing, or a short amendment).
    if phrase_present:
        rec["decision"] = "keep"
        rec["reason"] = "'tax receivable agreement' phrase present in body"
        return rec

    # Rule 4: phrase-free but heavy TRA terminology -- keep, conservatively.
    if term_count >= 3:
        rec["decision"] = "keep"
        rec["reason"] = f"{term_count} TRA-specific defined terms present"
        return rec

    # Rule 5: tiny file with no TRA phrase -- too short to be a contract.
    if size < MIN_BYTES:
        rec["decision"] = "drop"
        rec["reason"] = f"file too small ({size} B < {MIN_BYTES}), no phrase"
        return rec

    # Rule 6: very large file, no TRA signal at all.
    if size > LARGE_BYTES:
        rec["decision"] = "drop"
        rec["reason"] = (
            f"large filing ({size} B) with no TRA phrase or terms"
        )
        return rec

    # Rule 7: default drop -- no positive TRA signal.
    rec["decision"] = "drop"
    rec["reason"] = "no TRA title, phrase, or defining terminology"
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter a directory of EX-10 exhibits to plausible TRAs."
    )
    parser.add_argument(
        "source_dir", type=Path,
        help="directory searched recursively for .htm/.html/.txt/.pdf files",
    )
    parser.add_argument(
        "-o", "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "tra_keeplist.csv",
        help="keep-list CSV destination",
    )
    parser.add_argument(
        "--drop-csv", type=Path, default=None,
        help="optional CSV of dropped files (for auditing false drops)",
    )
    args = parser.parse_args()

    if not args.source_dir.is_dir():
        sys.exit(f"not a directory: {args.source_dir}")

    # Glob every exhibit file type, not only .htm: .txt filings are
    # keyword-scanned in place; .pdf exhibits are routed to manual review
    # by classify_file. Globbing only .htm would silently skip both.
    exhibit_exts = ("*.htm", "*.html", "*.txt", "*.pdf")
    exhibit_files = sorted(
        p for ext in exhibit_exts for p in args.source_dir.rglob(ext)
    )
    if not exhibit_files:
        sys.exit(
            f"no .htm/.html/.txt/.pdf files found under {args.source_dir}"
        )

    records = [classify_file(p) for p in exhibit_files]
    df = pl.DataFrame(records)

    keep = df.filter(pl.col("decision") == "keep")
    drop = df.filter(pl.col("decision") == "drop")

    keep.write_csv(args.output)
    if args.drop_csv is not None:
        drop.write_csv(args.drop_csv)

    total = df.height
    n_keep = keep.height
    n_drop = drop.height
    ext_counts = (
        df.with_columns(
            pl.col("path").str.to_lowercase().str.tail(4).alias("_ext")
        )
        .group_by("_ext")
        .len()
        .sort("_ext")
    )
    print(f"source directory : {args.source_dir}")
    print(f"total found      : {total}")
    print(
        "by extension     : "
        + ", ".join(
            f"{r['_ext']}={r['len']}" for r in ext_counts.iter_rows(named=True)
        )
    )
    print(f"dropped          : {n_drop} ({n_drop / total:.1%})")
    print(f"kept (review)    : {n_keep} ({n_keep / total:.1%})")
    print(f"keep-list CSV    : {args.output}")
    if args.drop_csv is not None:
        print(f"drop-list CSV    : {args.drop_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
