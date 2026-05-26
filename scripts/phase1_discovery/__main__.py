"""Phase 1 entry point: discover and acquire TRA-mentioning EDGAR filings.

Implements R14, R15, R16 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md.

Invocation::

    PYTHONPATH=scripts pixi run python -m phase1_discovery \\
      --start 2001-01 --end 2026-05

Defaults to start=2001-01, end=today. Idempotent on re-run: skips
accessions already fetched in the manifest with terminal fetch_status.

A ``--smoke-test`` flag runs the full end-to-end pipeline against live
EDGAR for a known small window (2024-06) into a temp directory and
asserts restart idempotency.

This module is a thin shim over ``phase1_discovery.driver``; all logic
lives in ``driver.py`` so it can be imported as a function
(``from phase1_discovery import run_phase1``) without re-running
``__main__``.
"""

from __future__ import annotations

import sys

from phase1_discovery.driver import main

if __name__ == "__main__":
    sys.exit(main())
