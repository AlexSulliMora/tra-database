"""Sweep EDGAR full-text search for TRA-mentioning filings across a date range.

Implements R1, R2, R3, R4 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md. For each month in the
``[start_date, end_date]`` range, runs all 5 query variants from
``queries.ALL_QUERY_VARIANTS`` via ``windows.query_month_with_halving``
(month windows with biweekly halving on overflow). Post-filters the unioned
result by ``queries.ALLOWED_FORMS`` locally -- never passes ``forms`` to
``search_filings`` because the EDGAR parameter parser drops slash-bearing
codes silently. Unions on the document-identity key ``(adsh, primary_doc)``
and aggregates the matched query variants into a pipe-joined
``phrase_variants_matched`` column.

Crucially, this stage does NOT filter to EX-10.* documents. That filter is
what scripts/find_candidates.py applies; Phase 1 keeps the filing whether
the hit was on an EX-10 exhibit, the 10-K MD&A body, an 8-K body, or any
other document inside an allowed form. The acquisition stage (U5) decides
which documents within each filing to actually download.

``WindowOverflowError`` from any one ``(year, month, variant)`` triple is
logged and the exception appended to an accumulator; the sweep keeps going.
Both the final unioned DataFrame and the list of accumulated overflow
errors are returned so the caller can decide what to do with them.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import polars as pl

from sec_edgar.client import EdgarClient

from phase1_discovery.queries import ALL_QUERY_VARIANTS, ALLOWED_FORMS
from phase1_discovery.windows import (
    WindowOverflowError,
    month_iter,
    query_month_with_halving,
)


# Columns the unioned discovery DataFrame is guaranteed to expose. Tracks
# sec_edgar.search.HIT_COLUMNS plus the Phase-1-added
# ``phrase_variants_matched`` aggregation column. ``period_of_report`` and
# ``file_description`` are present when search_filings emits them; they
# are passed through opportunistically but not required.
DISCOVERY_COLUMNS: tuple[str, ...] = (
    "adsh",
    "primary_doc",
    "ciks",
    "form",
    "file_type",
    "display_names",
    "file_date",
    "snippet",
    "phrase_variants_matched",
)


def _union_documents(all_hits: pl.DataFrame) -> pl.DataFrame:
    """Collapse per-variant hit rows down to one row per ``(adsh, primary_doc)``.

    Mirrors the grouping in ``scripts/find_candidates.py::union_month``.
    A null ``primary_doc`` is filled with an accession-scoped sentinel so
    two null-primary-doc rows from different accessions do not merge.
    The matched variants are aggregated into a sorted-unique pipe-joined
    string in ``phrase_variants_matched``.
    """
    if all_hits.height == 0:
        return pl.DataFrame(
            schema={col: pl.String for col in DISCOVERY_COLUMNS}
        )

    with_key = all_hits.with_columns(
        pl.col("primary_doc")
        .fill_null(pl.col("adsh") + ":<no-primary-doc>")
        .alias("_doc_key")
    )

    # First-of-each non-variant column. Build the agg list dynamically
    # because period_of_report / file_description are optional in the
    # underlying search rows.
    agg_cols = [
        pl.col("primary_doc").first(),
        pl.col("ciks").first(),
        pl.col("form").first(),
        pl.col("file_type").first(),
        pl.col("display_names").first(),
        pl.col("file_date").first(),
        pl.col("snippet").first(),
        pl.col("_variant")
        .unique()
        .sort()
        .str.join("|")
        .alias("phrase_variants_matched"),
    ]
    if "period_of_report" in with_key.columns:
        agg_cols.append(pl.col("period_of_report").first())
    if "file_description" in with_key.columns:
        agg_cols.append(pl.col("file_description").first())

    union_df = (
        with_key.group_by("adsh", "_doc_key")
        .agg(*agg_cols)
        .drop("_doc_key")
    )
    return union_df


def sweep_discovery(
    start_date: str,
    end_date: str,
    client: EdgarClient,
    output_path: str = "data/tra-mentions/discovery.parquet",
) -> tuple[pl.DataFrame, list[WindowOverflowError]]:
    """Sweep EDGAR full-text search across ``[start_date, end_date]`` and write a parquet.

    For each ``(year, month)`` in ``month_iter(start_date, end_date)``,
    runs all 5 ``ALL_QUERY_VARIANTS`` via ``query_month_with_halving``.
    ``WindowOverflowError`` from any single variant-month pair is logged
    and appended to an error accumulator; the sweep continues. After all
    months are queried, the per-variant DataFrames are vertically
    concatenated, post-filtered by ``ALLOWED_FORMS`` locally, and unioned
    on the document-identity key ``(adsh, primary_doc)``. The result is
    written as parquet to ``output_path`` and returned alongside the
    accumulated overflow errors.

    ``start_date`` and ``end_date`` are ``YYYY-MM`` strings.
    """
    overflow_errors: list[WindowOverflowError] = []
    per_variant_frames: list[pl.DataFrame] = []

    for year, month in month_iter(start_date, end_date):
        tag = f"{year:04d}-{month:02d}"
        print(f"[{tag}] querying {len(ALL_QUERY_VARIANTS)} variants", flush=True)
        for variant in ALL_QUERY_VARIANTS:
            try:
                df, meta = query_month_with_halving(
                    variant, year, month, client
                )
            except WindowOverflowError as exc:
                print(
                    f"[{tag}] OVERFLOW for variant {variant!r}: {exc}",
                    flush=True,
                )
                overflow_errors.append(exc)
                continue
            print(
                f"  {variant!r}: {df.height} rows "
                f"(relation={meta.get('relation')!r}, "
                f"fetched={meta.get('fetched')}, "
                f"halved={meta.get('halved', False)})",
                flush=True,
            )
            if df.height > 0:
                tagged = df.with_columns(pl.lit(variant).alias("_variant"))
                per_variant_frames.append(tagged)

    if not per_variant_frames:
        print("sweep_discovery: no hits across any window/variant", flush=True)
        empty = pl.DataFrame(
            schema={col: pl.String for col in DISCOVERY_COLUMNS}
        )
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        empty.write_parquet(out)
        return empty, overflow_errors

    all_hits = pl.concat(per_variant_frames, how="vertical_relaxed")
    print(
        f"sweep_discovery: concatenated {all_hits.height} raw hits across "
        f"{len(per_variant_frames)} per-variant frames",
        flush=True,
    )

    # R4: local post-filter on ``form`` against ALLOWED_FORMS. Never
    # pass ``forms`` to search_filings (EDGAR parser drops slash-bearing
    # codes silently).
    allowed = list(ALLOWED_FORMS)
    pre_form_filter = all_hits.height
    all_hits = all_hits.filter(pl.col("form").is_in(allowed))
    print(
        f"sweep_discovery: form filter {pre_form_filter} -> {all_hits.height} "
        f"({pre_form_filter - all_hits.height} dropped as outside ALLOWED_FORMS)",
        flush=True,
    )

    union_df = _union_documents(all_hits)
    print(
        f"sweep_discovery: unioned to {union_df.height} unique "
        f"(adsh, primary_doc) rows",
        flush=True,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    union_df.write_parquet(out)
    print(
        f"sweep_discovery: wrote {union_df.height} rows -> {out} "
        f"({len(overflow_errors)} overflow errors)",
        flush=True,
    )
    return union_df, overflow_errors


def _self_test() -> None:
    """Operator-invoked sanity check.

    Runs a small live-EDGAR sweep over a single known month (June 2024)
    into a tempfile so the real ``data/tra-mentions/discovery.parquet``
    is not clobbered. Asserts the returned DataFrame has the expected
    columns and prints OK on success.
    """
    start = "2024-06"
    end = "2024-06"
    with tempfile.NamedTemporaryFile(
        suffix=".parquet", delete=False
    ) as tmp:
        tmp_path = tmp.name
    print(
        f"running discovery sweep for {start}..{end} -> {tmp_path}",
        flush=True,
    )

    with EdgarClient() as client:
        df, errors = sweep_discovery(start, end, client, tmp_path)

    for col in DISCOVERY_COLUMNS:
        assert col in df.columns, (
            f"expected column {col!r} missing from discovery output; "
            f"got {df.columns}"
        )

    print(
        f"  result: df.height={df.height} columns={df.columns} "
        f"overflow_errors={len(errors)}",
        flush=True,
    )
    if df.height > 0:
        sample = df.head(3).select(
            "adsh", "form", "file_type", "phrase_variants_matched"
        )
        print(f"  sample rows:\n{sample}", flush=True)

    # Clean up temp parquet.
    Path(tmp_path).unlink(missing_ok=True)
    print("OK", flush=True)


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
