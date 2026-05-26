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

The CSV must be FLATTENED -- the operator is responsible for collapsing
transitive chains. If A->B is already on file and a B->C merger occurs,
the operator updates the existing A->B row to A->C rather than appending
a new B->C row. Phase 1 enforces this by rejecting any map where a
successor also appears as a predecessor: that pattern signals an
unflattened chain that would cause a one-hop merger-map lookup to
return a dead intermediate. See the plan's Key Technical Decisions
section.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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


def _slugify(name: str) -> str:
    """Lowercase ``name``, collapse non-alphanumeric runs to single hyphens.

    Verbatim from scripts/tra_download.py::_slugify. Raises ``ValueError``
    on a name that slugifies to the empty string (e.g. all-punctuation
    input). Examples::

        "Vince Holding Corp." -> "vince-holding-corp"
        "PG&E Corporation"    -> "pg-e-corporation"
    """
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not base:
        raise ValueError(f"slug for name={name!r} is empty after slugify")
    return base


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

    Also enforces the FLATTENED-CSV invariant: a successor must not
    itself appear as a predecessor in the same map. The merger-map
    lookup is one-hop only; if A->B and B->C both have rows, looking
    up A returns the dead intermediate B. The operator's contract per
    the plan's Key Technical Decisions is to update A->B in place to
    A->C rather than append a second row. A violation raises
    ``ValueError`` with the offending pair in the message.
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
    # Flattened-CSV invariant: a successor must NOT also be a predecessor
    # in the same map. The one-hop lookup in build_or_update_registry
    # would otherwise return a dead intermediate. The operator is
    # responsible for collapsing A->B + B->C into A->C in place; see the
    # plan's Key Technical Decisions section.
    predecessors = set(merger_map.keys())
    for pred, succ in merger_map.items():
        if succ in predecessors:
            raise ValueError(
                f"merger CSV {mergers_csv_path} has unflattened chain: "
                f"{pred} -> {succ}, but {succ} also has a row "
                f"({succ} -> {merger_map[succ]}). Operator must flatten "
                f"this chain by updating the {pred} row to point at the "
                f"terminal successor -- see plan Key Technical Decisions."
            )
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

        try:
            base_slug = _slugify(name)
        except ValueError as exc:
            raise ValueError(
                f"slug for CIK {cik} (name={name!r}) is empty after slugify"
            ) from exc

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

    Pure-function and error-path tests first; then a 3-CIK live
    integration smoke at the end. Synthetic tests cover slug rules,
    collision suffix, AE2 (merger CSV first-encounter), AE3 (existing
    row lock), and every documented merger-map error path.
    """
    # ----------------------------------------------------------------
    # Slug-rule tests on _slugify.
    # ----------------------------------------------------------------
    assert _slugify("Vince Holding Corp.") == "vince-holding-corp", (
        f"got {_slugify('Vince Holding Corp.')!r}"
    )
    assert _slugify("PG&E Corporation") == "pg-e-corporation", (
        f"got {_slugify('PG&E Corporation')!r}"
    )
    # All-punctuation slugifies to empty -> raises ValueError.
    raised_empty = False
    try:
        _slugify("!!!")
    except ValueError:
        raised_empty = True
    assert raised_empty, "_slugify on all-punctuation should raise"

    # ----------------------------------------------------------------
    # _read_merger_map error-path tests.
    # ----------------------------------------------------------------
    err_tmp = Path(tempfile.mkdtemp(prefix="phase1-registry-mergers-"))
    try:
        # Non-existent path -> empty dict, no warning, no error.
        absent = err_tmp / "does-not-exist.csv"
        assert _read_merger_map(absent) == {}

        # 8-digit (non-padded) CIK row -> logs warning, skips row.
        short_csv = err_tmp / "short.csv"
        short_csv.write_text(
            "predecessor_cik,successor_cik\n12345678,0000000002\n",
            encoding="utf-8",
        )
        # Should NOT raise; row is skipped.
        result = _read_merger_map(short_csv)
        assert result == {}, (
            f"expected empty map after skipping short CIK row; got {result}"
        )

        # Two rows naming same predecessor with different successors -> ValueError.
        conflict_csv = err_tmp / "conflict.csv"
        conflict_csv.write_text(
            "predecessor_cik,successor_cik\n"
            "0000000001,0000000002\n"
            "0000000001,0000000003\n",
            encoding="utf-8",
        )
        raised_conflict = False
        try:
            _read_merger_map(conflict_csv)
        except ValueError as exc:
            raised_conflict = True
            assert "conflicting successors" in str(exc), (
                f"unexpected error message: {exc}"
            )
        assert raised_conflict, "conflict CSV should raise ValueError"

        # Unflattened chain A->B and B->C in same CSV -> ValueError (R3).
        unflattened_csv = err_tmp / "unflattened.csv"
        unflattened_csv.write_text(
            "predecessor_cik,successor_cik\n"
            "0000000001,0000000002\n"
            "0000000002,0000000003\n",
            encoding="utf-8",
        )
        raised_chain = False
        try:
            _read_merger_map(unflattened_csv)
        except ValueError as exc:
            raised_chain = True
            assert "unflattened chain" in str(exc), (
                f"unexpected error message: {exc}"
            )
        assert raised_chain, "unflattened chain CSV should raise ValueError"

        # Identical-duplicate row -> silently deduplicated.
        dup_csv = err_tmp / "dup.csv"
        dup_csv.write_text(
            "predecessor_cik,successor_cik\n"
            "0000000001,0000000002\n"
            "0000000001,0000000002\n",
            encoding="utf-8",
        )
        dup_map = _read_merger_map(dup_csv)
        assert dup_map == {"0000000001": "0000000002"}, (
            f"identical-dup CSV: got {dup_map}"
        )
    finally:
        for child in err_tmp.iterdir():
            child.unlink()
        err_tmp.rmdir()

    # ----------------------------------------------------------------
    # AE2: merger CSV first-encounter applies successor's name to
    # the predecessor's registry row.
    # AE3: existing rows are never re-keyed even if the CSV grows.
    # Both use a monkeypatched fetch_submissions so they avoid the live
    # network and run deterministically.
    # ----------------------------------------------------------------

    # Canned static_dicts keyed by zero-padded CIK so the patched
    # fetch_submissions can return the right name for each call.
    canned_submissions = {
        "0000000001": ("Predecessor Corp.", "2010-01-01", "2020-12-31"),
        "0000000002": ("Successor Holdings", "2018-06-01", "2025-01-01"),
        "0000000003": ("Third Co.", "2015-01-01", "2024-01-01"),
    }

    def fake_fetch(cik, client=None, cache_root=None, cache_max_age_s=None):
        name, first, last = canned_submissions[cik]
        lf = pl.LazyFrame(
            {"filingDate": [first, last]},
            schema={"filingDate": pl.String},
        )
        static = {"name": name, "formerNames": [], "sic": "6199"}
        return lf, static

    ae_tmp = Path(tempfile.mkdtemp(prefix="phase1-registry-ae-"))
    try:
        # AE2: discovery has the predecessor CIK only; merger CSV maps
        # 0000000001 -> 0000000002. After build_or_update_registry, the
        # predecessor's row should carry the SUCCESSOR's name + slug,
        # but the row's ``cik`` column is the originally-discovered CIK.
        ae2_csv = ae_tmp / "ae2-mergers.csv"
        ae2_csv.write_text(
            "predecessor_cik,successor_cik\n0000000001,0000000002\n",
            encoding="utf-8",
        )
        ae2_registry = ae_tmp / "ae2-registry.parquet"
        discovery_ae2 = pl.DataFrame(
            {
                "adsh": ["acc-ae2"],
                "primary_doc": ["doc.htm"],
                "ciks": [["0000000001"]],
            },
            schema={
                "adsh": pl.String,
                "primary_doc": pl.String,
                "ciks": pl.List(pl.String),
            },
        )
        this_module = sys.modules[__name__]
        with patch.object(this_module, "fetch_submissions", side_effect=fake_fetch):
            ae2_result = build_or_update_registry(
                discovery_ae2, ae2_csv, ae2_registry, client=None
            )
        assert ae2_result.height == 1
        ae2_row = ae2_result.row(0, named=True)
        assert ae2_row["cik"] == "0000000001", (
            f"AE2: registry row's CIK should be the discovered (predecessor) CIK; "
            f"got {ae2_row['cik']!r}"
        )
        assert ae2_row["current_name"] == "Successor Holdings", (
            f"AE2: registry row should carry SUCCESSOR's name; got {ae2_row['current_name']!r}"
        )
        assert ae2_row["slug"] == "successor-holdings", (
            f"AE2: slug should derive from successor name; got {ae2_row['slug']!r}"
        )

        # AE3: existing-row lock. Persist the AE2 registry, then update
        # the CSV to map 0000000001 -> 0000000003 (a different
        # successor). Re-run with no new CIKs in discovery -- the
        # existing 0000000001 row should be byte-identical.
        ae3_csv = ae_tmp / "ae3-mergers.csv"
        ae3_csv.write_text(
            "predecessor_cik,successor_cik\n0000000001,0000000003\n",
            encoding="utf-8",
        )
        # Re-run with same discovery_df (no new CIKs).
        original_bytes = ae2_registry.read_bytes()
        with patch.object(this_module, "fetch_submissions", side_effect=fake_fetch):
            ae3_result = build_or_update_registry(
                discovery_ae2, ae3_csv, ae2_registry, client=None
            )
        assert ae3_result.height == 1
        ae3_row = ae3_result.row(0, named=True)
        assert ae3_row == ae2_row, (
            f"AE3: existing row was modified across re-run with new merger CSV. "
            f"before={ae2_row} after={ae3_row}"
        )
        # On-disk bytes should also be unchanged (no rewrite needed
        # since no new rows, but atomic_write_parquet does rewrite --
        # so we accept byte difference here and only require the row
        # dict to be unchanged, which we just checked).
        del original_bytes

        # ----------------------------------------------------------------
        # Collision suffix: two distinct CIKs that produce the same base
        # slug -> first gets bare, second gets "-2".
        # ----------------------------------------------------------------
        canned_submissions["0000000004"] = ("Acme Corp", "2010-01-01", "2020-01-01")
        canned_submissions["0000000005"] = ("ACME Corp.", "2011-01-01", "2021-01-01")
        coll_csv = ae_tmp / "coll-mergers.csv"
        coll_csv.write_text(
            "predecessor_cik,successor_cik\n", encoding="utf-8"
        )
        coll_registry = ae_tmp / "coll-registry.parquet"
        discovery_coll = pl.DataFrame(
            {
                "adsh": ["a", "b"],
                "primary_doc": ["d", "d"],
                "ciks": [["0000000004"], ["0000000005"]],
            },
            schema={
                "adsh": pl.String,
                "primary_doc": pl.String,
                "ciks": pl.List(pl.String),
            },
        )
        with patch.object(this_module, "fetch_submissions", side_effect=fake_fetch):
            coll_result = build_or_update_registry(
                discovery_coll, coll_csv, coll_registry, client=None
            )
        coll_map = {
            r["cik"]: r["slug"] for r in coll_result.iter_rows(named=True)
        }
        assert coll_map.get("0000000004") == "acme-corp", (
            f"first encounter should get bare slug; got {coll_map}"
        )
        assert coll_map.get("0000000005") == "acme-corp-2", (
            f"second encounter should get -2 suffix; got {coll_map}"
        )
    finally:
        for child in ae_tmp.iterdir():
            child.unlink()
        ae_tmp.rmdir()

    # ----------------------------------------------------------------
    # Live integration smoke (existing test, kept as-is).
    # ----------------------------------------------------------------
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
