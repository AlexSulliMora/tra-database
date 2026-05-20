"""Sweep EDGAR full-text search for TRA-mentioning filings, by month-window.

For each month in [start, end], query the four TRA phrase variants and
union the matched *documents*. EDGAR full-text search returns one hit per
matched document, and each hit carries a per-document ``file_type``; the
union groups by document identity ``(adsh, primary_doc)`` so two distinct
EX-10 exhibits in one filing remain two rows. The union is then filtered
to keep only EX-10.* documents -- the documents that themselves matched
the TRA phrase -- and the result is written to a parquet. Exhibit pull is
a separate step; see ``scripts/pull_exhibits.py``.

Invocation::

    PYTHONPATH=scripts pixi run python scripts/find_candidates.py \\
      --start 2024-06 --end 2024-06 \\
      --save-union-parquet data/edgar-query/full-text.parquet

Exit code 0 on success, 1 on unrecoverable error. Per-window errors are
logged but do not halt the run.
"""

from __future__ import annotations

import argparse
import calendar
import sys
import time
import traceback
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from sec_edgar.client import EdgarClient
from sec_edgar.search import DEFAULT_MAX_AGE_S, search_filings

PHRASE_VARIANTS: list[str] = [
    '"tax receivable agreement"',
    '"tax receivable agreements"',
    '"tax receivables agreement"',
    '"tax receivables agreements"',
]

# EDGAR full-text-search ``file_type`` values for the EX-10 ("material
# contracts") exhibit class. The class spans bare ``EX-10`` plus every
# sub-exhibit form seen in the cached search responses: numeric
# (``EX-10.1``, ``EX-10.27``, ``EX-10.100``), lettered (``EX-10.A``,
# ``EX-10.(A)``, ``EX-10.(III)``), mixed (``EX-10.1A``, ``EX-10.13B``),
# and a few oddities (``EX-10.HTM``, ``EX-10.55 MATERIAL CO``). The
# pattern is "EX-10 at the start, then either end-of-string or a
# non-digit character", so ``EX-100``/``EX-101`` (a different exhibit
# class, should it ever appear) is excluded while every genuine EX-10
# sub-form is kept. No ``EX-10<digit>`` value occurs in the cached
# corpus, confirmed empirically. Written without look-ahead because
# polars' regex engine (Rust ``regex``) does not support it; matched
# case-insensitively.
EX10_FILE_TYPE_PATTERN = r"(?i)^EX-10($|[^0-9])"


def search_with_retry(
    *args, max_attempts: int = 3, backoff_s: float = 1.5, **kwargs
):
    """Retry search_filings on HTTP 5xx; pass through everything else."""
    for attempt in range(max_attempts):
        try:
            return search_filings(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_attempts - 1:
                time.sleep(backoff_s)
                continue
            raise


def month_iter(start: str, end: str):
    """Yield (year, month) tuples inclusive over [start, end] in YYYY-MM form."""
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13:
            m = 1
            y += 1


def month_bounds(year: int, month: int) -> tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def biweekly_bounds(year: int, month: int) -> list[tuple[str, str]]:
    last = calendar.monthrange(year, month)[1]
    return [
        (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-15"),
        (f"{year:04d}-{month:02d}-16", f"{year:04d}-{month:02d}-{last:02d}"),
    ]


def run_query_with_halving(
    q: str,
    startdt: str,
    enddt: str,
    client: EdgarClient,
    cache_max_age_s: float,
) -> tuple[pl.DataFrame, dict]:
    """Run one phrase query for one window; if the 10K cap is hit, halve."""
    lf, meta = search_with_retry(
        q=q,
        startdt=startdt,
        enddt=enddt,
        client=client,
        cache_max_age_s=cache_max_age_s,
    )
    if meta.get("relation") == "gte":
        return lf.collect(), meta
    return lf.collect(), meta


def union_month(
    year: int,
    month: int,
    client: EdgarClient,
    log,
    cache_max_age_s: float,
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Run the four queries for one month-window, union on document identity.

    Returns (union_df, per-variant raw-hit counts).
    """
    startdt, enddt = month_bounds(year, month)
    per_variant_counts: dict[str, int] = {}
    frames: list[pl.DataFrame] = []
    for variant in PHRASE_VARIANTS:
        df, meta = run_query_with_halving(
            variant, startdt, enddt, client, cache_max_age_s
        )
        if meta.get("relation") == "gte":
            log(
                f"  CAP HIT for variant {variant} in {year:04d}-{month:02d}; "
                "halving to biweekly"
            )
            bw_frames = []
            for bw_start, bw_end in biweekly_bounds(year, month):
                bw_df, bw_meta = search_with_retry(
                    q=variant,
                    startdt=bw_start,
                    enddt=bw_end,
                    client=client,
                    cache_max_age_s=cache_max_age_s,
                )
                bw_df = bw_df.collect()
                if bw_meta.get("relation") == "gte":
                    log(
                        f"  ANOMALY: biweekly window {bw_start}..{bw_end} also "
                        f"hit 10K cap for {variant}; results truncated"
                    )
                bw_frames.append(bw_df)
            df = pl.concat(bw_frames, how="vertical_relaxed") if bw_frames else df
        per_variant_counts[variant] = df.height
        if df.height > 0:
            df = df.with_columns(pl.lit(variant).alias("_variant"))
            frames.append(df)

    if not frames:
        return pl.DataFrame(schema={"adsh": pl.String}), per_variant_counts

    all_hits = pl.concat(frames, how="vertical_relaxed")
    # Group by document identity, not by filing. ``file_type`` is a
    # per-document field, so collapsing on ``adsh`` alone would merge two
    # distinct EX-10 exhibits in one filing into a single row and lose one
    # of their file_type values. The document key is (adsh, primary_doc).
    # ``primary_doc`` can in principle be null (an _id with no colon); a
    # null group key would silently merge every doc-less hit in a filing,
    # so fill nulls with a per-row sentinel from the (always-present)
    # accession before grouping.
    all_hits = all_hits.with_columns(
        pl.col("primary_doc")
        .fill_null(pl.col("adsh") + ":<no-primary-doc>")
        .alias("_doc_key")
    )
    agg_cols = [
        pl.col("primary_doc").first(),
        pl.col("ciks").first(),
        pl.col("form").first(),
        pl.col("file_type").first(),
        pl.col("display_names").first(),
        pl.col("file_date").first(),
        pl.col("snippet").first(),
        pl.col("_variant").unique().sort().str.join("|").alias(
            "phrase_variants_matched"
        ),
    ]
    if "period_of_report" in all_hits.columns:
        agg_cols.append(pl.col("period_of_report").first())
    if "file_description" in all_hits.columns:
        agg_cols.append(pl.col("file_description").first())
    union_df = (
        all_hits.group_by("adsh", "_doc_key")
        .agg(*agg_cols)
        .drop("_doc_key")
    )
    return union_df, per_variant_counts


def main() -> int:
    today = date.today()
    default_end = f"{today.year:04d}-{today.month:02d}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2001-01")
    parser.add_argument("--end", default=default_end)
    parser.add_argument(
        "--save-union-parquet",
        type=Path,
        default=Path("data/edgar-query/full-text.parquet"),
        help=(
            "After unioning the four phrase-variant query results by "
            "document identity and filtering to EX-10.* documents, write "
            "the result to this parquet path. "
            "Default: data/edgar-query/full-text.parquet."
        ),
    )
    parser.add_argument(
        "--cache-max-age-s",
        type=float,
        default=None,
        help=(
            "Max age in seconds for a cached search page to count as a "
            "hit. The search cache otherwise expires after 1 day; pass a "
            "large value (e.g. 31536000 for a year) to re-run from the "
            "existing cache with no network calls. Default: the "
            "search module's 1-day default."
        ),
    )
    args = parser.parse_args()
    # search_filings defaults cache_max_age_s when None is passed.
    cache_max_age_s = (
        args.cache_max_age_s
        if args.cache_max_age_s is not None
        else DEFAULT_MAX_AGE_S
    )

    union_accum: list[pl.DataFrame] = []

    def log(msg: str) -> None:
        print(msg, flush=True)

    log(
        f"find_candidates: sweeping {args.start}..{args.end} -> "
        f"{args.save_union_parquet}"
    )

    with EdgarClient() as client:
        for year, month in month_iter(args.start, args.end):
            tag = f"{year:04d}-{month:02d}"
            log(f"[{tag}] querying 4 phrase variants")
            try:
                union_df, variant_counts = union_month(
                    year, month, client, log, cache_max_age_s
                )
            except Exception as e:
                log(
                    f"[{tag}] UNION ERROR: {type(e).__name__}: {e}\n"
                    + traceback.format_exc()
                )
                continue
            for v, n in variant_counts.items():
                log(f"  {v}: {n} raw hits")
            log(f"  union (unique documents): {union_df.height}")

            if union_df.height > 0:
                union_accum.append(union_df)

    out_path: Path = args.save_union_parquet
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if union_accum:
        full = pl.concat(union_accum, how="diagonal_relaxed")
    else:
        full = pl.DataFrame(
            schema={"adsh": pl.String, "file_type": pl.String}
        )

    # Keep only the documents that themselves matched the TRA phrase and
    # are EX-10.* exhibits. EDGAR returns one hit per matched document, so
    # a non-EX-10 file_type means the phrase matched some other document
    # in the filing (the 10-K body, an EX-99, a proxy, ...), not an
    # EX-10 contract.
    pre_filter = full.height
    if "file_type" in full.columns:
        ex10_mask = pl.col("file_type").str.contains(
            EX10_FILE_TYPE_PATTERN
        )
        kept = full.filter(ex10_mask.fill_null(False))
        dropped = full.filter(~ex10_mask.fill_null(False))
        n_null = dropped.filter(pl.col("file_type").is_null()).height
        log(
            f"EX-10 filter: {pre_filter} union rows -> {kept.height} kept, "
            f"{dropped.height} dropped ({n_null} of those had a null "
            "file_type)"
        )
        # Report TRA-relevant hits the filter drops on a null or
        # non-standard file_type, so an oddly-typed EX-10 contract is not
        # lost silently.
        if n_null > 0:
            log(
                f"  NOTE: {n_null} hit(s) dropped for a null file_type; "
                "inspect if any are EX-10 contracts:"
            )
            for r in dropped.filter(
                pl.col("file_type").is_null()
            ).head(25).iter_rows(named=True):
                log(
                    f"    null file_type: adsh={r.get('adsh')} "
                    f"form={r.get('form')} "
                    f"primary_doc={r.get('primary_doc')}"
                )
        full = kept
    else:
        log("WARNING: no file_type column present; EX-10 filter skipped")

    full.write_parquet(out_path)
    log(f"union parquet: {out_path} ({full.height} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
