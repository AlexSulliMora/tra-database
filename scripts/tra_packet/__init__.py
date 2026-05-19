"""Helpers for the tra-packet skill.

Single-firm evidence-packet assembly: filing-list construction,
TRA-mention detection, per-filing plain-text excerpt extraction with
non-GAAP table exclusion, TOC anchor pre-extraction, TRA-exhibit
identification with content-hash dedup, and packet rendering. Wraps
the ``sec_edgar`` primitives; does not duplicate them.
"""

from tra_packet.excerpts import (
    extract_tra_excerpts,
    excerpts_filtered,
    write_excerpts_to_cache,
)
from tra_packet.exhibits import collect_tra_exhibits, is_tra_contract
from tra_packet.sections import has_tra_mention
from tra_packet.timeline import build_filing_list, write_packet
from tra_packet.toc import extract_toc, write_toc_to_cache

__version__ = "0.3.0"

__all__ = [
    "has_tra_mention",
    "build_filing_list",
    "write_packet",
    "extract_tra_excerpts",
    "excerpts_filtered",
    "write_excerpts_to_cache",
    "collect_tra_exhibits",
    "is_tra_contract",
    "extract_toc",
    "write_toc_to_cache",
    "__version__",
]
