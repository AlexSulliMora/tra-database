"""CIK registry with slug derivation and merger-CSV resolution.

Implements R5-R7 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md. For every unique CIK in
the discovery output, fetches the EDGAR Submissions JSON, derives a
deterministic firm slug (lock-on-first-encounter), applies any predecessor
to successor merger mapping from ``data/cik-mergers.csv`` to existing
entries only (R7: existing rows are never retroactively re-keyed), and
writes ``data/cik-registry.parquet`` atomically.

Slug derivation matches scripts/tra_download.py: lowercase the canonical
registrant name, collapse runs of non-alphanumeric characters to single
hyphens, strip leading and trailing hyphens. Slug collisions across
distinct CIKs are disambiguated with a numeric suffix ``-2``, ``-3``, ...
checked against both the existing registry and the rows added during this
run.

The CSV format is two columns with a header row ``predecessor_cik,
successor_cik``; both columns are 10-digit zero-padded strings. Rows that
do not match are warned about and skipped. Duplicate predecessors with the
same successor are silently deduplicated; duplicate predecessors with
conflicting successors raise ``ValueError``. An absent CSV file is a valid
first-run state and produces an empty merger map without warning.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
from pathlib import Path

import polars as pl

from sec_edgar.client import EdgarClient
from sec_edgar.submissions import fetch_submissions

from phase1_discovery.manifest import atomic_write_parquet


# Polars schema for the registry parquet. Column order is part of the
# contract with downstream readers (Phase 2+).
REGISTRY_SCHEMA: dict[str, pl.DataType] = {
    "cik": pl.String,
    "current_name": pl.String,
    "slug": pl.String,
    "former_names": pl.String,
    "first_filing_date": pl.String,
    "last_filing_date": pl.String,
    "sic": pl.String,
}


def _read_existing_registry(registry_path: Path) -> pl.DataFrame:
    """Read the registry parquet if present; else return an empty-schema DataFrame."""
    if registry_path.exists():
        df = pl.read_parquet(registry_path)
        # Cast to canonical schema to defend against historical writes
        # with slightly different dtypes; column set must already match.
        missing = [c for c in REGISTRY_SCHEMA if c not in df.columns]
        if missing:
            raise ValueError(
                f"existing registry at {registry_path} missing columns "
                f"{missing}; got {df.columns}"
            )
        return df.select(
            [pl.col(c).cast(REGISTRY_SCHEMA[c]) for c in REGISTRY_SCHEMA]
        )
    return pl.DataFrame(schema=REGISTRY_SCHEMA)


def _read_merger_map(mergers_csv_path: Path) -> dict[str, str]:
    """Parse the merger CSV into ``{predecessor_cik: successor_cik}``.

    Validates header, 10-digit zero-padded CIK form on both columns,
    silent dedupe on identical duplicates, and raises ``ValueError`` on
    duplicate predecessors with conflicting successors. Absent file
    returns an empty mapping with no warning (valid first-run state).
    """
    if not mergers_csv_path.exists():
        return {}
    merger_map: dict[str, str] = {}
    with mergers_csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            print(
                f"merger CSV {mergers_csv_path} is empty (no header); "
                f"treating as empty merger map",
                flush=True,
            )
            return {}
        if [c.strip() for c in header] != ["predecessor_cik", "successor_cik"]:
            raise ValueError(
                f"merger CSV {mergers_csv_path} header must be exactly "
                f"['predecessor_cik', 'successor_cik']; got {header}"
            )
        for line_no, row in enumerate(reader, start=2):
            if len(row) == 0 or all(not c.strip() for c in row):
                continue  # blank line
            if len(row) != 2:
                print(
                    f"merger CSV {mergers_csv_path} line {line_no}: "
                    f"expected 2 columns, got {len(row)} -- skipping row {row!r}",
                    flush=True,
                )
                continue
            pred, succ = row[0].strip(), row[1].strip()
            if not (
                len(pred) == 10
                and pred.isdigit()
                and len(succ) == 10
                and succ.isdigit()
            ):
                print(
                    f"merger CSV {mergers_csv_path} line {line_no}: both CIKs "
                    f"must be 10-digit zero-padded strings; got "
                    f"predecessor={pred!r} successor={succ!r} -- skipping",
                    flush=True,
                )
                continue
            if pred in merger_map:
                if merger_map[pred] == succ:
                    continue  # silent dedupe on identical duplicate
                raise ValueError(
                    f"merger CSV {mergers_csv_path}: predecessor {pred} maps "
                    f"to conflicting successors {merger_map[pred]} and {succ}"
                )
            merger_map[pred] = succ
    return merger_map


def _flatten_discovery_ciks(discovery_df: pl.DataFrame) -> list[str]:
    """Return unique CIKs from ``discovery_df["ciks"]`` in encounter order.

    The discovery output (per sec_edgar.search) carries ``ciks`` as a
    list-column; a single accession can name multiple CIKs (co-filers).
    Encounter order matters: lock-on-first-encounter slug derivation is
    deterministic only if the order is stable. We iterate rows top-down,
    each row's CIK list left-to-right, normalize to 10-digit zero-padded
    form, and emit each CIK the first time it appears.
    """
    if "ciks" not in discovery_df.columns:
        raise ValueError(
            f"discovery_df missing 'ciks' column; got {discovery_df.columns}"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for row_ciks in discovery_df["ciks"].to_list():
        if row_ciks is None:
            continue
        # ``ciks`` may be a Python list (when sourced from a list-column) or
        # a string (when the underlying search hit had a single CIK and the
        # schema collapsed). Normalize.
        if isinstance(row_ciks, str):
            candidates = [row_ciks]
        else:
            candidates = list(row_ciks)
        for raw in candidates:
            if raw is None:
                continue
            cik = str(raw).strip()
            if not cik.isdigit():
                print(
                    f"discovery row had non-digit CIK {raw!r}; skipping",
                    flush=True,
                )
                continue
            padded = cik.zfill(10)
            if padded not in seen:
                seen.add(padded)
                ordered.append(padded)
    return ordered


def build_or_update_registry(
    discovery_df: pl.DataFrame,
    mergers_csv_path: str | Path,
    registry_path: str | Path,
    client: EdgarClient,
) -> pl.DataFrame:
    """Build or extend the CIK registry from discovery output.

    For each unique CIK in ``discovery_df["ciks"]`` that is not already in
    the existing registry at ``registry_path``, fetches the Submissions
    JSON (resolving via merger map first if the CIK is a known
    predecessor), derives a slug, applies collision suffixes, and appends
    a row. Existing rows are never modified (R7: lock-on-first-encounter).
    Writes the combined registry atomically to ``registry_path`` and
    returns it as a DataFrame.

    The discovery DataFrame must carry a ``ciks`` column shaped as
    ``sec_edgar.search`` produces (list of zero-padded CIK strings per
    row, or a bare string when the row was sourced with one CIK).
    """
    registry_path = Path(registry_path)
    mergers_csv_path = Path(mergers_csv_path)

    existing = _read_existing_registry(registry_path)
    existing_ciks: set[str] = set(existing["cik"].to_list())
    # Lookup of slug -> set-of-CIKs for collision detection. A slug may be
    # in use by multiple distinct CIKs (one bare + one or more numerically
    # suffixed); we want to know all in-use slugs.
    in_use_slugs: set[str] = set(existing["slug"].to_list())

    merger_map = _read_merger_map(mergers_csv_path)

    ordered_ciks = _flatten_discovery_ciks(discovery_df)
    new_ciks = [c for c in ordered_ciks if c not in existing_ciks]
    print(
        f"build_or_update_registry: {len(ordered_ciks)} unique CIKs in discovery; "
        f"{len(new_ciks)} new (existing registry has {existing.height} rows; "
        f"merger map has {len(merger_map)} entries)",
        flush=True,
    )

    new_rows: list[dict] = []
    for cik in new_ciks:
        # R7: resolve via merger map (one hop only; transitive chains are
        # the operator's responsibility per Key Technical Decisions). The
        # slug-bearing entity is the successor; the registry row's cik
        # column still records the original discovered CIK so downstream
        # joins on (discovered) CIK still work.
        resolved_cik = merger_map.get(cik, cik)
        if resolved_cik != cik:
            print(
                f"  CIK {cik} -> resolved to successor {resolved_cik} via merger map",
                flush=True,
            )

        lf, static_dict = fetch_submissions(resolved_cik, client=client)

        name = static_dict.get("name")
        if not name:
            raise ValueError(
                f"Submissions JSON for CIK {resolved_cik} has no 'name' field; "
                f"static_dict={static_dict!r}"
            )

        # Slug derivation -- verbatim from scripts/tra_download.py::_slugify.
        base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not base_slug:
            raise ValueError(
                f"slug for CIK {cik} (name={name!r}) is empty after slugify"
            )

        slug = base_slug
        suffix = 2
        while slug in in_use_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        in_use_slugs.add(slug)

        # First/last filing date from the Submissions LazyFrame. Empty
        # filings history is unusual for a registered CIK but handled.
        df = lf.select("filingDate").collect()
        if df.height == 0:
            first_date = ""
            last_date = ""
        else:
            dates = df["filingDate"].drop_nulls()
            if dates.len() == 0:
                first_date = ""
                last_date = ""
            else:
                first_date = str(dates.min())
                last_date = str(dates.max())

        former_names = static_dict.get("formerNames") or []
        sic_raw = static_dict.get("sic")
        sic = "" if sic_raw is None else str(sic_raw)

        row = {
            "cik": cik,  # the ORIGINAL discovered CIK, not the successor
            "current_name": name,
            "slug": slug,
            "former_names": json.dumps(former_names),
            "first_filing_date": first_date,
            "last_filing_date": last_date,
            "sic": sic,
        }
        new_rows.append(row)
        print(
            f"  + {cik}: name={name!r} slug={slug!r} "
            f"filings={first_date}..{last_date}",
            flush=True,
        )

    if new_rows:
        new_df = pl.DataFrame(new_rows, schema=REGISTRY_SCHEMA)
        combined = pl.concat([existing, new_df], how="vertical")
    else:
        combined = existing

    atomic_write_parquet(combined, registry_path)
    print(
        f"build_or_update_registry: wrote {combined.height} rows -> {registry_path} "
        f"({len(new_rows)} new this run)",
        flush=True,
    )
    return combined


def _self_test() -> None:
    """Operator-invoked sanity check against live EDGAR.

    Builds a synthetic 3-row discovery DataFrame for three known TRA-filer
    CIKs (Vince Holding, Surgery Partners, Parsley Energy), writes an
    empty merger CSV, calls ``build_or_update_registry``, and asserts the
    returned DataFrame is well-formed. Cleans up the temp directory.
    """
    test_ciks = [
        "0001579298",  # Vince Holding Corp
        "0001638833",  # Surgery Partners
        "0001594466",  # Parsley Energy
    ]

    # Synthetic discovery DataFrame: one row per CIK with the canonical
    # ``ciks`` list-column shape from sec_edgar.search.
    discovery_df = pl.DataFrame(
        {
            "adsh": [f"acc-{i}" for i in range(len(test_ciks))],
            "primary_doc": [f"doc-{i}.htm" for i in range(len(test_ciks))],
            "ciks": [[c] for c in test_ciks],
        },
        schema={
            "adsh": pl.String,
            "primary_doc": pl.String,
            "ciks": pl.List(pl.String),
        },
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="phase1-registry-selftest-"))
    try:
        mergers_csv = tmp_dir / "cik-mergers.csv"
        # Header-only CSV (empty merger map).
        mergers_csv.write_text(
            "predecessor_cik,successor_cik\n", encoding="utf-8"
        )
        registry_path = tmp_dir / "cik-registry.parquet"

        with EdgarClient() as client:
            result = build_or_update_registry(
                discovery_df, mergers_csv, registry_path, client
            )

        # Shape checks.
        assert list(result.columns) == list(REGISTRY_SCHEMA), (
            f"registry columns {result.columns} != schema {list(REGISTRY_SCHEMA)}"
        )
        assert result.height == len(test_ciks), (
            f"expected {len(test_ciks)} registry rows, got {result.height}"
        )

        # CIK + slug checks.
        ciks_out = result["cik"].to_list()
        assert set(ciks_out) == set(test_ciks), (
            f"registry CIKs {sorted(ciks_out)} != input {sorted(test_ciks)}"
        )
        slugs_out = result["slug"].to_list()
        for slug in slugs_out:
            assert slug and slug.strip(), f"empty slug in registry: {slugs_out}"

        # Parquet should have been written atomically.
        assert registry_path.exists(), f"registry parquet not written to {registry_path}"

        # Print the derived (cik, name, slug) so the operator can spot-check.
        print("derived registry rows:", flush=True)
        for row in result.iter_rows(named=True):
            print(
                f"  cik={row['cik']} name={row['current_name']!r} "
                f"slug={row['slug']!r}",
                flush=True,
            )

        print("OK", flush=True)
    finally:
        # Clean up the temp directory (parquet + csv + any temp files).
        for child in tmp_dir.iterdir():
            child.unlink()
        tmp_dir.rmdir()


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
