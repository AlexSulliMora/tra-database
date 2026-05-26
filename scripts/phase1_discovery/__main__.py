"""CLI entrypoint stub for the Phase 1 discovery and acquisition pipeline.

This stub exists so ``python -m phase1_discovery`` runs without an
ImportError while later units of the Phase 1 plan are still in flight. U7
replaces this with the full argparse-driven driver that orchestrates
discovery, registry, and acquisition.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "phase1_discovery: not yet implemented; "
        "see docs/plans/2026-05-25-001-feat-phase-1-discovery-and-acquisition-plan.md",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
