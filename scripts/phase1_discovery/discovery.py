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
from unittest.mock import patch

import polars as pl

from sec_edgar.client import EdgarClient

from phase1_discovery.manifest import atomic_write_parquet
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

    Always re-runs regardless of whether ``output_path`` already exists.
    Caching of redundant EDGAR calls is handled at the ``EdgarClient``
    layer (per-query response cache keyed by the search params hash); a
    fresh process invocation that re-issues the same queries pays only
    the cache-hit cost. The discovery parquet itself is therefore
    always rewritten via ``atomic_write_parquet`` -- the rewritten file
    is the success signal, and a crashed run leaves the previous
    committed parquet intact (atomic rename).

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
        atomic_write_parquet(empty, out)
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
    atomic_write_parquet(union_df, out)
    print(
        f"sweep_discovery: wrote {union_df.height} rows -> {out} "
        f"({len(overflow_errors)} overflow errors)",
        flush=True,
    )
    return union_df, overflow_errors


def _hit_row(
    adsh: str,
    primary_doc: str | None,
    form: str,
    variant: str,
    file_type: str = "8-K",
) -> dict:
    """Build a synthetic per-variant hit row matching search_filings shape."""
    return {
        "adsh": adsh,
        "primary_doc": primary_doc,
        "ciks": ["0000000001"],
        "form": form,
        "file_type": file_type,
        "display_names": "Acme Corp [CIK 0000000001]",
        "file_date": "2024-06-01",
        "snippet": "tax receivable agreement",
        "_variant": variant,
    }


def _self_test() -> None:
    """Operator-invoked sanity check.

    Five synthetic ``_union_documents`` / form-filter scenarios + one
    monkeypatched WindowOverflowError accumulator scenario + one
    live-EDGAR smoke at the end.
    """
    # Synthetic test 1: same (adsh, primary_doc), two distinct variants
    # collapse to one row whose phrase_variants_matched joins both.
    frame1 = pl.DataFrame(
        [
            _hit_row("acc-1", "d1.htm", "8-K", '"tax receivable agreement"'),
            _hit_row("acc-1", "d1.htm", "8-K", "TRA"),
        ],
        schema_overrides={"ciks": pl.List(pl.String)},
    )
    u1 = _union_documents(frame1)
    assert u1.height == 1, f"test 1: expected 1 row, got {u1.height}"
    pvm1 = u1["phrase_variants_matched"][0]
    assert '"tax receivable agreement"' in pvm1 and "TRA" in pvm1, (
        f"test 1: variants not joined; got {pvm1!r}"
    )
    assert "|" in pvm1, f"test 1: pipe join missing; got {pvm1!r}"

    # Synthetic test 2: same adsh, NULL primary_doc on two rows -> 1
    # union row (the accession-scoped null-sentinel collapses them).
    frame2 = pl.DataFrame(
        [
            _hit_row("acc-2", None, "8-K", '"tax receivable agreement"'),
            _hit_row("acc-2", None, "8-K", '"tax receivable agreements"'),
        ],
        schema_overrides={"ciks": pl.List(pl.String)},
    )
    u2 = _union_documents(frame2)
    assert u2.height == 1, f"test 2: NULL primary_doc collapse failed; got {u2.height} rows"

    # Synthetic test 3: same adsh, two DISTINCT primary_doc values -> 2
    # union rows (separate documents inside the same accession).
    frame3 = pl.DataFrame(
        [
            _hit_row("acc-3", "ex10-1.htm", "8-K", '"tax receivable agreement"'),
            _hit_row("acc-3", "ex10-2.htm", "8-K", '"tax receivable agreement"'),
        ],
        schema_overrides={"ciks": pl.List(pl.String)},
    )
    u3 = _union_documents(frame3)
    assert u3.height == 2, f"test 3: expected 2 distinct documents, got {u3.height}"
    assert set(u3["primary_doc"].to_list()) == {"ex10-1.htm", "ex10-2.htm"}

    # Synthetic test 4: form post-filter -- 10-K/A and 10-K are kept,
    # N-1A is dropped. Mirror sweep_discovery's filter step inline.
    frame4 = pl.DataFrame(
        [
            _hit_row("acc-4a", "d.htm", "10-K", '"tax receivable agreement"'),
            _hit_row("acc-4b", "d.htm", "10-K/A", '"tax receivable agreement"'),
            _hit_row("acc-4c", "d.htm", "N-1A", '"tax receivable agreement"'),
        ],
        schema_overrides={"ciks": pl.List(pl.String)},
    )
    filtered = frame4.filter(pl.col("form").is_in(list(ALLOWED_FORMS)))
    forms_kept = set(filtered["form"].to_list())
    assert forms_kept == {"10-K", "10-K/A"}, (
        f"test 4: expected {{'10-K', '10-K/A'}}, got {forms_kept}"
    )

    # Synthetic test 5: WindowOverflowError accumulator. Monkeypatch
    # query_month_with_halving to raise on month 2024-07 and return a
    # small frame for 2024-06. Run sweep_discovery over the two-month
    # range and assert the error is captured AND the other month's
    # results land in the returned DataFrame.
    canned_lf_meta = pl.DataFrame(
        [_hit_row("acc-june", "ex10-1.htm", "8-K", '"tax receivable agreement"')],
        schema_overrides={"ciks": pl.List(pl.String)},
    ).drop("_variant")

    def fake_qmh(query, year, month, client, cache_max_age_s=None):
        if (year, month) == (2024, 7):
            raise WindowOverflowError(
                f"synthetic overflow on {year}-{month:02d} for {query!r}"
            )
        # Return the canned frame only for the canonical phrase variant
        # so the other 4 variants return empty; keeps the assertion below
        # simple (1 union row, not 5).
        if query == '"tax receivable agreement"':
            return canned_lf_meta, {"relation": "eq", "fetched": 1, "total": 1}
        empty = pl.DataFrame(
            schema={
                "adsh": pl.String,
                "primary_doc": pl.String,
                "ciks": pl.List(pl.String),
                "form": pl.String,
                "file_type": pl.String,
                "display_names": pl.String,
                "file_date": pl.String,
                "snippet": pl.String,
            }
        )
        return empty, {"relation": "eq", "fetched": 0, "total": 0}

    this_module = sys.modules[__name__]
    tmp5 = Path(tempfile.mkdtemp(prefix="phase1-discovery-r5-")) / "discovery.parquet"
    try:
        with patch.object(this_module, "query_month_with_halving", side_effect=fake_qmh):
            # client is unused under the patch.
            df5, errors5 = sweep_discovery("2024-06", "2024-07", client=None, output_path=str(tmp5))
        assert len(errors5) >= 1, (
            f"expected at least one WindowOverflowError accumulated; got {errors5}"
        )
        # Each of the 5 variants raises in 2024-07, so we accumulate 5
        # overflow errors (one per variant call).
        assert df5.height == 1, (
            f"expected 1 union row from canned June hit; got {df5.height}"
        )
        assert df5["adsh"][0] == "acc-june"
    finally:
        tmp5.unlink(missing_ok=True)
        tmp5.parent.rmdir()

    # Live smoke: small sweep over June 2024 into a tempfile so the
    # canonical data/tra-mentions/discovery.parquet is not clobbered.
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
