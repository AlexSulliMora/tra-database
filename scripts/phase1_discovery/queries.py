"""Query constants for the Phase 1 discovery sweep.

Implements R1 (5 query variants), R4 (ALLOWED_FORMS) of the Phase 1
brainstorm at docs/brainstorms/2026-05-25-phase-1-requirements.md. Also
exposes the EX-10 file_type regex reused by acquisition (U5) and the
TRA-keyword description regex used to classify EX-10 exhibits by their
HTML-filing-index description text.

No I/O; pure constants. ``_self_test()`` at the bottom is the operator-
invoked sanity check, gated on ``if __name__ == "__main__"``.
"""

from __future__ import annotations

import re
import sys


# Four phrase variants (R1). Kept verbatim from
# scripts/find_candidates.py PHRASE_VARIANTS so the pre-pivot script and
# Phase 1 remain bit-identical on the phrase side while the pre-pivot
# script's duplicate copy continues to exist until the deferred-cleanup
# PR removes it.
PHRASE_VARIANTS: tuple[str, str, str, str] = (
    '"tax receivable agreement"',
    '"tax receivable agreements"',
    '"tax receivables agreement"',
    '"tax receivables agreements"',
)

# Fifth query variant (R1): the acronym "TRA" sent as an EDGAR phrase
# query with embedded quotation marks (``q='"TRA"'``). Unquoted single
# tokens are subject to EDGAR full-text-search tokenization that returns
# unrelated matches (e.g., JPMorgan 424B2 prospectus supplements where
# "TRA" appears as a ticker or CUSIP fragment); the quoted form forces
# whole-word matching on the exact 3-character string.
TRA_TOKEN_QUERY: str = '"TRA"'

# Union of all 5 query variants used by the discovery sweep (R1).
ALL_QUERY_VARIANTS: tuple[str, ...] = (*PHRASE_VARIANTS, TRA_TOKEN_QUERY)

# R4. The ALLOWED_FORMS list as enumerated in the Phase 1 brainstorm.
# Note: the brainstorm's parenthetical "(21 forms)" is a counting error
# in the source document; the enumerated list below contains 24 entries
# and that enumeration is authoritative. Form filtering is applied
# locally on the returned LazyFrame; the EDGAR ``forms`` query
# parameter is NOT used (parser bug silently drops slash-bearing codes).
ALLOWED_FORMS: frozenset[str] = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-Q",
        "10-Q/A",
        "20-F",
        "40-F",
        "6-K",
        "DEF 14A",
        "DEFA14A",
        "DEFM14A",
        "PRE 14A",
        "8-K",
        "8-K/A",
        "S-1",
        "S-1/A",
        "S-4",
        "S-4/A",
        "424B1",
        "424B2",
        "424B3",
        "424B4",
        "424B5",
        "DRS",
        "DRS/A",
    }
)

# EDGAR full-text-search ``file_type`` values for the EX-10 ("material
# contracts") exhibit class. Matches bare ``EX-10`` plus every sub-
# exhibit form: numeric (``EX-10.1``, ``EX-10.27``, ``EX-10.100``),
# lettered (``EX-10.A``, ``EX-10.(A)``), mixed (``EX-10.1A``), and
# oddities (``EX-10.HTM``). Excludes ``EX-100``/``EX-101`` (a distinct
# exhibit class). Verbatim pattern from
# scripts/find_candidates.py EX10_FILE_TYPE_PATTERN.
EX10_FILE_TYPE_PATTERN: re.Pattern[str] = re.compile(r"(?i)^EX-10($|[^0-9])")

# TRA-keyword regex applied to the HTML filing-index Description column
# during acquisition (U5). Case-insensitive. Matches the phrase
# "tax receivable" anywhere, and the bare token "TRA" only as a whole
# word (so "transfer" and "transaction" do not match). The phrase side
# is not wrapped in word boundaries so plurals and possessives are
# tolerated naturally.
TRA_DESCRIPTION_REGEX: re.Pattern[str] = re.compile(
    r"tax receivable|\bTRA\b", re.IGNORECASE
)


def _self_test() -> None:
    """Operator-invoked sanity check for the module's exposed surface."""
    # R1: 5 query variants total.
    assert len(ALL_QUERY_VARIANTS) == 5, (
        f"expected 5 query variants, got {len(ALL_QUERY_VARIANTS)}"
    )
    assert PHRASE_VARIANTS == (
        '"tax receivable agreement"',
        '"tax receivable agreements"',
        '"tax receivables agreement"',
        '"tax receivables agreements"',
    )
    assert TRA_TOKEN_QUERY == '"TRA"', (
        "TRA token query must include embedded double quotes so EDGAR "
        "full-text search treats it as a phrase match, not a tokenized "
        f"single word; got {TRA_TOKEN_QUERY!r}"
    )
    assert ALL_QUERY_VARIANTS[-1] == TRA_TOKEN_QUERY

    # R4: the enumerated list contains 24 forms. (The brainstorm's
    # parenthetical "(21 forms)" is a counting error; the enumeration is
    # authoritative.)
    assert len(ALLOWED_FORMS) == 24, (
        f"expected 24 enumerated forms, got {len(ALLOWED_FORMS)}"
    )
    for required in ("10-K", "10-K/A", "DEF 14A", "DEFM14A", "424B5", "DRS/A"):
        assert required in ALLOWED_FORMS, (
            f"required form {required!r} missing from ALLOWED_FORMS"
        )

    # EX-10 file_type pattern: matches the EX-10 family, excludes EX-100.
    assert EX10_FILE_TYPE_PATTERN.match("EX-10")
    assert EX10_FILE_TYPE_PATTERN.match("EX-10.1")
    assert EX10_FILE_TYPE_PATTERN.match("EX-10.A")
    assert EX10_FILE_TYPE_PATTERN.match("EX-10.HTM")
    assert EX10_FILE_TYPE_PATTERN.match("EX-100") is None
    assert EX10_FILE_TYPE_PATTERN.match("EX-101") is None

    # TRA description regex: phrase match anywhere; "TRA" only as a
    # whole token; "transfer" and "transaction" do not match.
    assert TRA_DESCRIPTION_REGEX.search("Tax Receivable Agreement")
    assert TRA_DESCRIPTION_REGEX.search("tax receivable agreements (the TRAs)")
    assert TRA_DESCRIPTION_REGEX.search("TRA Amendment")
    assert TRA_DESCRIPTION_REGEX.search("transfer") is None
    assert TRA_DESCRIPTION_REGEX.search("transaction") is None

    print("OK", flush=True)


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
