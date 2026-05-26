"""Phase 1 manifest: 14-field schema, atomic rewrite, restart-aware read.

Implements R11 (manifest schema), R12 (fetch_status vocabulary), R13
(exhibit_match_source vocabulary), R15 (restart skip via done_fetches),
and R16 (idempotent append + schema preservation) of the Phase 1
brainstorm at docs/brainstorms/2026-05-25-phase-1-requirements.md.

The canonical manifest lives at data/tra-mentions/manifest.parquet. Each
row records one document acquisition attempt: the firm that filed it,
the accession and document identifiers from the EDGAR HTML index, why
the document was classified as TRA-relevant
(``exhibit_match_source``), and the terminal outcome of the fetch
(``fetch_status``). Every one of the six fetch-status values is
terminal -- a successful download and each of the five failure modes
all count as "done" for restart purposes, so a re-run can skip the
accession/filename pair without another HTTP call (R15).

Writes are atomic: ``write_manifest_atomic`` writes to
``<path>.tmp.<pid>`` and then ``os.rename`` to ``<path>``, which is
atomic on the same filesystem. ``append_rows`` validates the two
controlled vocabularies on every row so a typo in the caller (e.g. a
status of ``"success "`` with a trailing space, or a forgotten dash in
``"primary doc"``) fails loudly at append time rather than silently
contaminating the parquet (R16).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import polars as pl


# Controlled vocabularies (R12, R13). Kept as frozensets so they cannot
# be mutated by callers and so membership checks are O(1).
FETCH_STATUS_VALUES: frozenset[str] = frozenset(
    {
        "success",
        "not-found-404",
        "redacted-403",
        "rate-limited",
        "parse-error",
        "other-error",
    }
)

EXHIBIT_MATCH_SOURCE_VALUES: frozenset[str] = frozenset(
    {
        "primary-doc",
        "phrase-match",
        "description-match",
        "both",
    }
)


# 14-field manifest schema (R11). Column order is pinned; downstream
# readers (Phase 2 and the U7 driver) rely on it. Everything is
# ``pl.String`` except ``byte_size`` which is a nullable ``pl.Int64``
# (None for failed fetches that produced no on-disk bytes).
MANIFEST_SCHEMA: dict[str, pl.DataType] = {
    "firm_slug": pl.String,
    "cik": pl.String,
    "accession": pl.String,
    "form": pl.String,
    "filed_date": pl.String,
    "doc_filename": pl.String,
    "doc_type": pl.String,
    "doc_description": pl.String,
    "url": pl.String,
    "phrase_variants_matched": pl.String,
    "exhibit_match_source": pl.String,
    "fetch_status": pl.String,
    "fetch_ts": pl.String,
    "byte_size": pl.Int64,
}

# Tuple form of the column order, for callers that need an ordered
# iterable (e.g. constructing a list[dict] in column order).
MANIFEST_COLUMNS: tuple[str, ...] = tuple(MANIFEST_SCHEMA.keys())


def _empty_manifest() -> pl.DataFrame:
    """Construct a zero-row DataFrame carrying ``MANIFEST_SCHEMA``."""
    return pl.DataFrame(schema=MANIFEST_SCHEMA)


def read_manifest(path: str | Path) -> pl.DataFrame:
    """Read the manifest parquet, or return an empty-schema DF if absent.

    The empty-schema fall-through is the restart-friendly path: a fresh
    Phase 1 run on a new ``output_root`` calls this with no parquet on
    disk and expects an empty DataFrame with the 14-column schema, not
    a ``FileNotFoundError``.
    """
    p = Path(path)
    if not p.exists():
        return _empty_manifest()
    return pl.read_parquet(p)


def write_manifest_atomic(df: pl.DataFrame, path: str | Path) -> None:
    """Write the manifest to ``path`` via write-tmp-then-rename.

    ``os.replace`` is atomic on the same filesystem on POSIX and on
    Windows, so a crash mid-write either leaves the previous committed
    manifest intact at ``path`` (rename has not yet happened) or the
    new manifest committed (rename has happened). The temp file is
    cleaned up on failure.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp.{os.getpid()}")
    try:
        df.write_parquet(tmp)
        os.replace(tmp, dest)
    except Exception:
        # Best-effort cleanup; do not mask the original exception.
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def done_fetches(manifest_df: pl.DataFrame) -> set[tuple[str, str]]:
    """Return the set of ``(accession, doc_filename)`` pairs already done.

    All six ``fetch_status`` values are terminal -- ``success`` and the
    five failure types (``not-found-404``, ``redacted-403``,
    ``rate-limited``, ``parse-error``, ``other-error``) all count as
    "done" for restart purposes (R15). A failed accession is NOT
    retried by Phase 1; the operator triages it separately. An empty
    manifest returns an empty set.
    """
    if manifest_df.height == 0:
        return set()
    rows = manifest_df.select(["accession", "doc_filename"]).iter_rows()
    return {(acc, fn) for acc, fn in rows}


def append_rows(
    existing_df: pl.DataFrame, new_rows: list[dict]
) -> pl.DataFrame:
    """Append ``new_rows`` to ``existing_df`` preserving ``MANIFEST_SCHEMA``.

    Validates every new row's ``fetch_status`` and
    ``exhibit_match_source`` against the controlled vocabularies and
    raises ``ValueError`` on a bad value -- a typo in either field
    silently propagated to the parquet would be hard to detect
    downstream, so we fail loudly at append time.

    Returns a new DataFrame; the input is not mutated.
    """
    if not new_rows:
        return existing_df

    for i, row in enumerate(new_rows):
        status = row.get("fetch_status")
        if status not in FETCH_STATUS_VALUES:
            raise ValueError(
                f"new_rows[{i}]: fetch_status={status!r} not in "
                f"FETCH_STATUS_VALUES {sorted(FETCH_STATUS_VALUES)}"
            )
        source = row.get("exhibit_match_source")
        if source not in EXHIBIT_MATCH_SOURCE_VALUES:
            raise ValueError(
                f"new_rows[{i}]: exhibit_match_source={source!r} not in "
                f"EXHIBIT_MATCH_SOURCE_VALUES "
                f"{sorted(EXHIBIT_MATCH_SOURCE_VALUES)}"
            )

    new_df = pl.DataFrame(new_rows, schema=MANIFEST_SCHEMA)
    if existing_df.height == 0:
        return new_df
    return pl.concat([existing_df, new_df], how="vertical")


def _self_test() -> None:
    """In-memory round-trip plus vocabulary-validation checks.

    No live EDGAR calls. Exercises:
      - 3-row write/read round-trip preserves columns and row count.
      - ``read_manifest`` on a missing path returns the empty schema.
      - ``done_fetches`` counts all terminal statuses, not just success.
      - ``append_rows`` raises on a bad ``fetch_status`` and on a bad
        ``exhibit_match_source``; appends cleanly on valid rows.
      - Atomic write: a mid-write crash leaves the previous committed
        manifest intact at the destination path.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="phase1-manifest-selftest-"))
    try:
        # 1. 3-row round trip.
        rows = [
            {
                "firm_slug": "acme-corp",
                "cik": "0000000001",
                "accession": "0000000001-24-000001",
                "form": "8-K",
                "filed_date": "2024-06-01",
                "doc_filename": "acme8k.htm",
                "doc_type": "8-K",
                "doc_description": "",
                "url": "https://www.sec.gov/Archives/edgar/data/1/000000000124000001/acme8k.htm",
                "phrase_variants_matched": '"tax receivable agreement"',
                "exhibit_match_source": "primary-doc",
                "fetch_status": "success",
                "fetch_ts": "2026-05-26T00:00:00+00:00",
                "byte_size": 12345,
            },
            {
                "firm_slug": "acme-corp",
                "cik": "0000000001",
                "accession": "0000000001-24-000001",
                "form": "8-K",
                "filed_date": "2024-06-01",
                "doc_filename": "ex10-1.htm",
                "doc_type": "EX-10.1",
                "doc_description": "Tax Receivable Agreement",
                "url": "https://www.sec.gov/Archives/edgar/data/1/000000000124000001/ex10-1.htm",
                "phrase_variants_matched": '"tax receivable agreement"',
                "exhibit_match_source": "both",
                "fetch_status": "success",
                "fetch_ts": "2026-05-26T00:00:00+00:00",
                "byte_size": 98765,
            },
            {
                "firm_slug": "beta-inc",
                "cik": "0000000002",
                "accession": "0000000002-24-000007",
                "form": "10-K",
                "filed_date": "2024-06-15",
                "doc_filename": "missing.htm",
                "doc_type": "10-K",
                "doc_description": "",
                "url": "https://www.sec.gov/Archives/edgar/data/2/000000000224000007/missing.htm",
                "phrase_variants_matched": '"TRA"',
                "exhibit_match_source": "primary-doc",
                "fetch_status": "not-found-404",
                "fetch_ts": "2026-05-26T00:00:01+00:00",
                "byte_size": None,
            },
        ]
        df = pl.DataFrame(rows, schema=MANIFEST_SCHEMA)
        assert df.height == 3
        assert df.columns == list(MANIFEST_COLUMNS)

        path = tmp_dir / "manifest.parquet"
        write_manifest_atomic(df, path)
        assert path.exists()
        # No leftover .tmp.<pid>.
        leftover = list(tmp_dir.glob("manifest.parquet.tmp.*"))
        assert not leftover, f"leftover tmp files: {leftover}"

        df_read = read_manifest(path)
        assert df_read.height == 3, f"got {df_read.height} rows, expected 3"
        assert df_read.columns == list(MANIFEST_COLUMNS), (
            f"columns drifted on round-trip: {df_read.columns}"
        )
        # Schema preserved exactly.
        assert dict(df_read.schema) == MANIFEST_SCHEMA, (
            f"schema drift: {dict(df_read.schema)} != {MANIFEST_SCHEMA}"
        )

        # 2. read_manifest on missing path returns empty schema.
        missing = tmp_dir / "does-not-exist.parquet"
        empty = read_manifest(missing)
        assert empty.height == 0
        assert empty.columns == list(MANIFEST_COLUMNS)
        assert dict(empty.schema) == MANIFEST_SCHEMA

        # 3. done_fetches counts all terminal statuses. Build a 5-row
        # manifest with one of each non-success status plus one success.
        five = [
            {**rows[0]},
            {**rows[0], "doc_filename": "f2.htm", "fetch_status": "not-found-404", "byte_size": None},
            {**rows[0], "doc_filename": "f3.htm", "fetch_status": "redacted-403", "byte_size": None},
            {**rows[0], "doc_filename": "f4.htm", "fetch_status": "rate-limited", "byte_size": None},
            {**rows[0], "doc_filename": "f5.htm", "fetch_status": "parse-error", "byte_size": None},
        ]
        five_df = pl.DataFrame(five, schema=MANIFEST_SCHEMA)
        done = done_fetches(five_df)
        assert len(done) == 5, (
            f"done_fetches returned {len(done)} pairs, expected 5 (all "
            f"terminal statuses count)"
        )
        assert (rows[0]["accession"], "f3.htm") in done
        assert (rows[0]["accession"], "f5.htm") in done

        # done_fetches on empty returns empty set.
        assert done_fetches(_empty_manifest()) == set()

        # 4. append_rows validation.
        valid_new = {
            **rows[0],
            "doc_filename": "extra.htm",
            "fetch_status": "success",
            "exhibit_match_source": "description-match",
        }
        bad_status = {**valid_new, "fetch_status": "bogus"}
        bad_source = {**valid_new, "exhibit_match_source": "primary doc"}

        try:
            append_rows(df, [bad_status])
        except ValueError as exc:
            assert "fetch_status" in str(exc)
        else:
            raise AssertionError("append_rows accepted a bogus fetch_status")

        try:
            append_rows(df, [bad_source])
        except ValueError as exc:
            assert "exhibit_match_source" in str(exc)
        else:
            raise AssertionError(
                "append_rows accepted a bogus exhibit_match_source"
            )

        appended = append_rows(df, [valid_new])
        assert appended.height == df.height + 1
        assert appended.columns == list(MANIFEST_COLUMNS)
        assert dict(appended.schema) == MANIFEST_SCHEMA

        # append_rows on empty list is a no-op (returns original DF).
        assert append_rows(df, []).height == df.height

        # 5. Atomic write: a mid-write crash leaves the previous
        # committed manifest intact. Simulate by writing a known-good
        # manifest, then attempting a write whose tmp step raises BEFORE
        # the rename.
        committed_path = tmp_dir / "committed.parquet"
        write_manifest_atomic(df, committed_path)
        original_bytes = committed_path.read_bytes()

        # Patch DataFrame.write_parquet on a sentinel DF to raise. We
        # exercise the same atomic-write code path with a deliberate
        # exception inside the tmp-write step.
        class _ExplodingDF:
            def write_parquet(self, _p):
                raise RuntimeError("simulated crash mid-write")

        try:
            write_manifest_atomic(_ExplodingDF(), committed_path)  # type: ignore[arg-type]
        except RuntimeError as exc:
            assert "simulated crash" in str(exc)
        else:
            raise AssertionError(
                "write_manifest_atomic swallowed the simulated crash"
            )

        # Original file untouched.
        assert committed_path.read_bytes() == original_bytes, (
            "committed manifest was modified by a crashed write"
        )
        # No leftover .tmp.<pid>.
        leftover = list(tmp_dir.glob("committed.parquet.tmp.*"))
        assert not leftover, f"leftover tmp files after crash: {leftover}"

        print("OK", flush=True)
    finally:
        for root, dirs, files in os.walk(tmp_dir, topdown=False):
            for name in files:
                Path(root, name).unlink()
            for name in dirs:
                Path(root, name).rmdir()
        tmp_dir.rmdir()


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
