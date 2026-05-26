"""Phase 1 discovery and acquisition pipeline for the per-firm TRA corpus.

Sweeps EDGAR full-text search across a date range with five Tax Receivable
Agreement query variants, resolves each hit to a canonical firm (CIK plus
slug), fetches the per-accession HTML filing index, downloads the primary
document plus matched EX-10 exhibits, and writes a manifest parquet plus a
done marker that Phase 2 reads. The package mirrors the shape of
``scripts/sec_edgar/`` and reuses its rate-limited ``EdgarClient``.

Invocation::

    PYTHONPATH=scripts pixi run python -m phase1_discovery \\
        --start 2024-06-01 --end 2024-06-30 \\
        --output-root data/tra-mentions

See ``docs/plans/2026-05-25-001-feat-phase-1-discovery-and-acquisition-plan.md``
for the full design and unit breakdown.
"""

from __future__ import annotations

from phase1_discovery.driver import run_phase1

__version__ = "0.1.0"

__all__ = ["run_phase1"]
