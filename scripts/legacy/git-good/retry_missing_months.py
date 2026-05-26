"""One-off recovery: retry ten month-windows that 500'd during the full sweep.

Reuses union_month from find_candidates.py (which uses search_with_retry
internally). Appends recovered rows to data/edgar-query/full-text.parquet
and dedups on adsh.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import polars as pl

# Make find_candidates importable.
PROJECT_ROOT = Path("/home/sulli/research/tra")
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(
    0, str(PROJECT_ROOT / ".claude/skills/tra-find-candidates/scripts")
)

from sec_edgar.client import EdgarClient  # noqa: E402
from find_candidates import union_month  # noqa: E402

MISSING = [
    (2008, 5), (2008, 6),
    (2012, 1),
    (2015, 11),
    (2017, 11),
    (2019, 12),
    (2020, 8), (2020, 11),
    (2022, 5), (2022, 8),
]

PARQUET_PATH = PROJECT_ROOT / "data/edgar-query/full-text.parquet"


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    existing = pl.read_parquet(PARQUET_PATH)
    log(f"existing rows: {existing.height}")

    recovered_frames: list[pl.DataFrame] = []
    recovered: list[str] = []
    still_failed: list[str] = []

    with EdgarClient() as client:
        for year, month in MISSING:
            tag = f"{year:04d}-{month:02d}"
            log(f"[{tag}] querying")
            try:
                union_df, variant_counts = union_month(year, month, client, log)
            except Exception as e:
                log(f"[{tag}] FAILED: {type(e).__name__}: {e}")
                log(traceback.format_exc())
                still_failed.append(tag)
                continue
            for v, n in variant_counts.items():
                log(f"  {v}: {n} raw hits")
            log(f"  union (unique adsh): {union_df.height}")
            if union_df.height > 0:
                recovered_frames.append(union_df)
            recovered.append(tag)
            # gentle pacing between months
            time.sleep(0.5)

    if recovered_frames:
        new_rows = pl.concat(recovered_frames, how="diagonal_relaxed")
        log(f"recovered rows (pre-dedup): {new_rows.height}")
        combined = pl.concat([existing, new_rows], how="diagonal_relaxed")
        combined = combined.unique(subset=["adsh"], keep="first")
        log(f"combined rows after dedup on adsh: {combined.height}")
        combined.write_parquet(PARQUET_PATH)
    else:
        log("no recovered rows; parquet unchanged")
        combined = existing

    log("")
    log("=" * 60)
    log(f"final row count: {combined.height}")
    log(f"recovered months: {recovered}")
    log(f"still failed: {still_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
