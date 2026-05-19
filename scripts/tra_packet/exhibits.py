r"""TRA exhibit identification, content-hash dedup, and download.

Walks each filing in a firm's history, identifies exhibit documents
(``EX-10.*`` family by SGML ``<TYPE>`` header) that ARE the TRA
contract itself (not credit agreements that merely reference the
TRA as a carve-out), dedupes by content hash so an exhibit re-filed
in a later 10-K does not produce a second copy, and saves the
unique exhibits under
``coauthor/2026-05-12-edgar-scrape/findings/packets/<slug>/exhibits/``.

A TRA exhibit is identified by:

1. SGML ``<TYPE>EX-10.*`` (material contract) AND
2. The document's TITLE block (first ~600 stripped characters)
   contains a TRA-title phrase: "TAX RECEIVABLE AGREEMENT" (case
   insensitive) or "TRA WAIVER" or "TRA AMENDMENT" or
   "AMENDMENT ... TO ... TAX RECEIVABLE AGREEMENT". This rejects
   credit-agreement amendments that simply reference the TRA in
   their body.

The title check is the load-bearing filter: a real TRA contract
declares itself in its first heading; a credit agreement does not.

Saved filename:
``<filing-date>_<accession>_<slug-from-first-heading-or-type>.htm``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from sec_edgar.archives import fetch_document
from sec_edgar.client import EdgarClient

_TRA_PATTERN = re.compile(r"(?i)tax\s+receivables?\s+agreements?")

# SGML envelope parser (the ``<accession>.txt`` full-submission file
# carries every document's TYPE / SEQUENCE / FILENAME / DESCRIPTION).
_SGML_DOC_RE = re.compile(
    r"<TYPE>(?P<type>[^\n<]+)\s*"
    r"<SEQUENCE>(?P<seq>[^\n<]+)\s*"
    r"<FILENAME>(?P<fname>[^\n<]+)\s*"
    r"(?:<DESCRIPTION>(?P<desc>[^\n<]+))?"
)

_EX10_RE = re.compile(r"^EX-10[.\-]", re.IGNORECASE)

_CONTRACT_SHAPE = re.compile(
    r"(?is)\b(?:WHEREAS|NOW,?\s+THEREFORE|IN\s+WITNESS\s+WHEREOF"
    r"|ARTICLE\s+[IVX]+|Section\s+1\.0?1)\b"
)

# Title patterns that indicate the document IS a TRA contract. Each
# matches text in the document's first ~600 stripped characters.
_TRA_TITLE = re.compile(
    r"(?is)\b("
    r"(?:income\s+)?tax\s+receivables?\s+agreements?\b"
    r"|tra\s+waiver(?:\s+and\s+assignment)?"
    r"|tra\s+amendment"
    r"|waiver\s+and\s+assignment\s+agreement.{0,80}tax\s+receivable"
    r")"
)

# Title patterns that indicate the document is NOT a TRA contract,
# even if "tax receivable agreement" appears in its body. These cover
# the credit-agreement false-positive class.
_NON_TRA_TITLE = re.compile(
    r"(?is)\b("
    r"credit\s+agreement"
    r"|loan\s+agreement"
    r"|indenture"
    r"|guarantee\s+(?:agreement|and\s+collateral)"
    r"|security\s+agreement"
    r"|registration\s+rights\s+agreement"
    r"|stockholders?\s+agreement"
    r"|amended\s+and\s+restated\s+credit"
    r"|.*amendment\s+to\s+(?:the\s+)?credit\s+agreement"
    r")"
)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _exhibit_title_window(body: str, window: int = 600) -> str:
    """Strip HTML and return the first ``window`` characters."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:window]


@dataclass
class ExhibitCandidate:
    accession: str
    filing_date: str
    filename: str
    sgml_type: str
    sgml_description: str | None


@dataclass
class SavedExhibit:
    accession: str
    filing_date: str
    filename: str
    sgml_type: str
    saved_path: Path
    content_hash: str
    tra_phrase_count: int
    byte_size: int


def _slugify(s: str, max_len: int = 60) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if len(s) > max_len:
        s = s[:max_len]
    return s or "exhibit"


def list_ex10_candidates(
    cik_unpadded: str,
    accession: str,
    filing_date: str,
    client: EdgarClient,
) -> list[ExhibitCandidate]:
    """Read the full-submission SGML wrapper; return every EX-10.* doc."""
    sgml = fetch_document(
        cik_unpadded, accession, f"{accession}.txt", client=client
    )
    if isinstance(sgml, (bytes, bytearray)):
        sgml = sgml.decode("utf-8", errors="replace")
    out: list[ExhibitCandidate] = []
    for m in _SGML_DOC_RE.finditer(sgml):
        sgml_type = (m.group("type") or "").strip()
        if not _EX10_RE.match(sgml_type):
            continue
        fname = (m.group("fname") or "").strip()
        if not fname or fname.lower().endswith((".jpg", ".png", ".gif")):
            continue
        out.append(ExhibitCandidate(
            accession=accession,
            filing_date=filing_date,
            filename=fname,
            sgml_type=sgml_type,
            sgml_description=(m.group("desc") or "").strip() or None,
        ))
    return out


def is_tra_contract(body: str) -> tuple[bool, int]:
    """Return (is_tra_contract, tra_phrase_count).

    Identification rules (all must hold):

    1. The document's title block (first ~600 stripped chars)
       contains a TRA-title phrase. This is the discriminative test
       between an actual TRA contract and a credit agreement that
       references the TRA.
    2. The title block does NOT match a credit-agreement /
       indenture / etc. shape.
    3. The body looks like a contract (WHEREAS / Section 1.01 / etc.).
    4. The TRA phrase appears at least three times in the body.
    """
    if not body:
        return False, 0
    title = _exhibit_title_window(body)
    if _NON_TRA_TITLE.search(title):
        return False, 0
    if not _TRA_TITLE.search(title):
        return False, 0
    count = len(_TRA_PATTERN.findall(body))
    if count < 3:
        return False, count
    if not _CONTRACT_SHAPE.search(body):
        return False, count
    return True, count


def _hash_bytes(b: bytes | str) -> str:
    if isinstance(b, str):
        b = b.encode("utf-8", errors="replace")
    return hashlib.sha256(b).hexdigest()


def collect_tra_exhibits(
    cik_unpadded: str,
    filings: list,  # list of FilingRow from tra_packet.timeline
    exhibits_dir: Path,
    client: EdgarClient,
) -> list[SavedExhibit]:
    """Walk every filing; collect unique TRA-contract exhibits.

    Returns the saved manifest. Idempotent: an exhibit already saved
    on disk with the same content hash is reused, not rewritten.
    """
    exhibits_dir.mkdir(parents=True, exist_ok=True)
    seen_hashes: dict[str, SavedExhibit] = {}

    # Pre-load any hashes from the directory so reruns dedupe across
    # invocations. The hash is computed on read.
    for existing in exhibits_dir.glob("*.htm"):
        try:
            payload = existing.read_bytes()
        except FileNotFoundError:
            continue
        h = _hash_bytes(payload)
        # We do not reconstruct the SavedExhibit metadata from disk;
        # the marker is enough to suppress re-writes.
        seen_hashes.setdefault(h, SavedExhibit(
            accession="(prior run)",
            filing_date="(prior run)",
            filename=existing.name,
            sgml_type="",
            saved_path=existing,
            content_hash=h,
            tra_phrase_count=0,
            byte_size=existing.stat().st_size,
        ))

    saved: list[SavedExhibit] = []

    for f in filings:
        try:
            candidates = list_ex10_candidates(
                cik_unpadded, f.accession, f.filing_date, client
            )
        except httpx.HTTPStatusError as e:
            # Older filings sometimes have an SGML wrapper that 404s.
            # Skip the filing and continue; other status codes still
            # propagate.
            if e.response.status_code == 404:
                continue
            raise
        for cand in candidates:
            try:
                body = fetch_document(
                    cik_unpadded, cand.accession, cand.filename, client=client
                )
            except httpx.HTTPStatusError as e:
                # Individual exhibit document missing; skip just this
                # candidate, not the whole filing.
                if e.response.status_code == 404:
                    continue
                raise
            if isinstance(body, (bytes, bytearray)):
                body_str = body.decode("utf-8", errors="replace")
                hash_input = bytes(body)
            else:
                body_str = body
                hash_input = body.encode("utf-8", errors="replace")
            is_tra, count = is_tra_contract(body_str)
            if not is_tra:
                continue
            h = _hash_bytes(hash_input)
            if h in seen_hashes:
                continue
            slug = _slugify(cand.sgml_description or cand.sgml_type)
            outfile = exhibits_dir / (
                f"{cand.filing_date}_{cand.accession}_{slug}.htm"
            )
            outfile.write_bytes(hash_input)
            entry = SavedExhibit(
                accession=cand.accession,
                filing_date=cand.filing_date,
                filename=cand.filename,
                sgml_type=cand.sgml_type,
                saved_path=outfile,
                content_hash=h,
                tra_phrase_count=count,
                byte_size=len(hash_input),
            )
            seen_hashes[h] = entry
            saved.append(entry)
    return saved
