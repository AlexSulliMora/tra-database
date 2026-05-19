"""TRA-mention detection.

Single regex check: does a filing body mention "tax receivable
agreement[s]"? Section extraction was previously implemented here
(heading-walk + flat-window fallback). It was dropped because the
flat-window fallback produced noisy excerpts (EBITDA non-GAAP
definitions, exhibit lists, mid-sentence truncations) on modern iXBRL
filings, which use typographic markers rather than semantic heading
tags. Better to omit excerpts than mislead the reviewer.

Cancel-proximity detection was also removed: the regex flagged
"tax receivable agreement (benefit) expense" wording in non-GAAP
measure definitions as cancel signals across multiple years of
periodic filings for at least one test firm.
"""

from __future__ import annotations

import re

_TRA_PATTERN = re.compile(r"(?i)tax\s+receivables?\s+agreements?")


def has_tra_mention(body: str) -> bool:
    """Return True if the filing body mentions a tax receivable agreement."""
    return _TRA_PATTERN.search(body) is not None
