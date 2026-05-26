"""Index-first per-accession acquisition: fetch and write TRA-relevant documents.

Implements R8-R10 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md. For one accession from
the discovery output, fetches the per-accession HTML filing-index page (via
``sec_edgar.archives.fetch_filing_index_html``), classifies each document
into one of three R9 classes -- the primary doc, a phrase-matched EX-10
(the discovery hit's named doc, when it is an EX-10), or a description-
matched EX-10 (any EX-10 whose index ``description`` matches
``queries.TRA_DESCRIPTION_REGEX``) -- and downloads only the matched
documents. Every other doc in the index (other EX-10s, EX-99s, graphics,
the complete-submission text file) is skipped.

Per R10, document writes are atomic: ``fetch_document`` returns full bytes
or str, we write to ``<dest>.tmp.<pid>`` and ``os.rename`` to ``<dest>``.
On a re-run, an already-on-disk file with a corresponding terminal manifest
row (caller's responsibility) is skipped without an HTTP call; if the file
exists on disk but the manifest row was lost, a new manifest row is
emitted from the discovery row + classification + ``os.stat`` so the
discovery-derived columns are never NULL on the rebuilt row.

Fetch errors are captured as manifest rows with no on-disk file: HTTP 404
becomes ``fetch_status='not-found-404'``, HTTP 403 becomes
``'redacted-403'``, HTTP 429 (post-EdgarClient-retry-exhaustion) becomes
``'rate-limited'``, BeautifulSoup or parquet parse failures become
``'parse-error'``, and any other exception becomes ``'other-error'``. None
of these abort the run.

The returned list of manifest-row dicts is consumed by U6's manifest
module and U7's per-firm flush loop.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from sec_edgar.archives import fetch_document, fetch_filing_index_html
from sec_edgar.client import EdgarClient

from phase1_discovery.queries import (
    EX10_FILE_TYPE_PATTERN,
    TRA_DESCRIPTION_REGEX,
)


# 14-field manifest schema (R11). Column order pinned for downstream
# readers (Phase 2 and the U6 manifest module). Kept here as a local
# tuple so acquisition can construct manifest rows without importing U6
# (which has not yet been written at the time U5 lands).
MANIFEST_FIELDS: tuple[str, ...] = (
    "firm_slug",
    "cik",
    "accession",
    "form",
    "filed_date",
    "doc_filename",
    "doc_type",
    "doc_description",
    "url",
    "phrase_variants_matched",
    "exhibit_match_source",
    "fetch_status",
    "fetch_ts",
    "byte_size",
)

ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


def _accession_no_dashes(accession: str) -> str:
    """Strip dashes from an accession; validate 18-digit canonical form."""
    s = accession.replace("-", "")
    if len(s) != 18 or not s.isdigit():
        raise ValueError(
            f"accession must be 18 digits with dashes (e.g. "
            f"0000320193-23-000106); got {accession!r}"
        )
    return s


def _pad_cik(cik: str | int) -> str:
    """Zero-pad to 10-digit canonical form."""
    s = str(cik).strip().lstrip("0") or "0"
    if not s.isdigit():
        raise ValueError(f"CIK must be digits, got {cik!r}")
    return s.zfill(10)


def _unpadded_cik(cik_padded: str) -> str:
    """Strip leading zeros for use in EDGAR Archives URLs."""
    return cik_padded.lstrip("0") or "0"


def _classify_status(exc: BaseException) -> str:
    """Map a fetch exception to the manifest's ``fetch_status`` vocabulary."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 404:
            return "not-found-404"
        if code == 403:
            return "redacted-403"
        if code == 429:
            return "rate-limited"
        return "other-error"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        # ``fetch_document``'s decode step and any downstream parse step
        # would surface as one of these.
        return "parse-error"
    return "other-error"


def _now_iso() -> str:
    """ISO-8601 UTC second-precision timestamp for manifest ``fetch_ts``."""
    return (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def _stat_iso(path: Path) -> str:
    """ISO-8601 UTC timestamp from a file's mtime (for re-emitted rows)."""
    ts = _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.timezone.utc)
    return ts.replace(microsecond=0).isoformat()


def _atomic_write_bytes(dest: Path, payload: bytes) -> None:
    """Write ``payload`` to ``dest`` via write-tmp-then-rename for crash safety."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp.{os.getpid()}")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _lookup_firm_slug(registry_df: pl.DataFrame, cik_padded: str) -> str:
    """Look up the slug for a CIK in the registry; raise if not present."""
    matches = registry_df.filter(pl.col("cik") == cik_padded)
    if matches.height == 0:
        raise ValueError(
            f"CIK {cik_padded} not in registry; build_or_update_registry "
            f"must run before acquire_filing"
        )
    return matches["slug"][0]


def _select_targets(
    index_df: pl.DataFrame, discovery_primary_doc: str | None
) -> list[dict]:
    """Decide which documents to fetch and tag each with its match source.

    R9 classes:
      - primary doc (form body): the index row whose ``name`` equals
        ``discovery_primary_doc``, OR -- when discovery's primary_doc is
        null OR points to an EX-10 -- the first non-EX-10 row in the
        index (skipping rows with empty type, e.g. the complete-
        submission text-file footer).
      - phrase-match: an EX-10 row whose ``name`` equals
        ``discovery_primary_doc`` (the search hit landed on this exhibit).
      - description-match: any other EX-10 row whose ``description``
        matches ``TRA_DESCRIPTION_REGEX``.
      - both: an EX-10 that is both the discovery hit AND has a TRA
        keyword in its description.

    Returns a list of ``{row, source}`` dicts in index order. Each
    ``row`` is the underlying index DataFrame row as a named dict;
    ``source`` is one of ``{'primary-doc', 'phrase-match',
    'description-match', 'both'}``. A document is emitted at most once
    even if it qualifies under multiple classes (the EX-10 classes
    coalesce into ``'both'``; the primary-doc class is suppressed for an
    EX-10 that is already in the EX-10 classes).
    """
    rows = list(index_df.iter_rows(named=True))

    # Build EX-10 match decisions per row.
    selected: dict[str, dict] = {}  # name -> {row, source}

    # First, classify EX-10s.
    for row in rows:
        name = row["name"]
        typ = row["type"] or ""
        desc = row["description"] or ""
        if not name:
            continue
        if not EX10_FILE_TYPE_PATTERN.match(typ):
            continue
        is_phrase = (
            discovery_primary_doc is not None and name == discovery_primary_doc
        )
        is_desc = bool(TRA_DESCRIPTION_REGEX.search(desc))
        if is_phrase and is_desc:
            selected[name] = {"row": row, "source": "both"}
        elif is_phrase:
            selected[name] = {"row": row, "source": "phrase-match"}
        elif is_desc:
            selected[name] = {"row": row, "source": "description-match"}

    # Now identify the primary doc. Heuristic:
    #   1. If discovery_primary_doc names a non-EX-10 row in the index,
    #      that row is the primary.
    #   2. Otherwise (discovery_primary_doc is null OR the hit was on an
    #      EX-10), the primary is the first index row whose ``type`` is
    #      a non-EX-10, non-empty value. The empty-type row at the
    #      bottom ("Complete submission text file") is intentionally
    #      skipped.
    primary_row: dict | None = None
    if discovery_primary_doc is not None:
        for row in rows:
            if row["name"] == discovery_primary_doc and not (
                EX10_FILE_TYPE_PATTERN.match(row["type"] or "")
            ):
                primary_row = row
                break
    if primary_row is None:
        for row in rows:
            typ = row["type"] or ""
            if typ and not EX10_FILE_TYPE_PATTERN.match(typ):
                primary_row = row
                break

    # If we found a primary row that isn't already in the EX-10 selection
    # (impossible by construction since EX-10s are excluded above, but
    # defended in case the heuristic changes), add it.
    if primary_row is not None and primary_row["name"] not in selected:
        selected[primary_row["name"]] = {
            "row": primary_row,
            "source": "primary-doc",
        }

    # Return targets in index order (stable, debuggable).
    ordered: list[dict] = []
    selected_names = set(selected.keys())
    for row in rows:
        if row["name"] in selected_names:
            ordered.append(selected[row["name"]])
            selected_names.discard(row["name"])
    return ordered


def acquire_filing(
    accession_row: dict[str, Any],
    registry_df: pl.DataFrame,
    output_root: str | Path,
    client: EdgarClient,
    done_set: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Acquire one accession's TRA-relevant documents.

    Returns a list of 14-field manifest-row dicts -- one per fetched (or
    attempted-and-failed) document. Documents NOT attempted in this call
    (because they were already on disk AND already had a terminal
    manifest row) are the caller's responsibility to skip; this function
    has no view of the existing manifest. A file that exists on disk
    with no manifest row produces a re-emitted manifest row populated
    from discovery + ``os.stat``; the discovery-derived columns are
    never NULL on this path.

    ``accession_row`` keys:
      - ``adsh`` (str, with dashes), ``primary_doc`` (str | None),
        ``ciks`` (list[str]), ``form`` (str), ``file_date`` (str
        ``YYYY-MM-DD``), ``phrase_variants_matched`` (str, pipe-joined).

    ``done_set`` is an optional set of ``(accession, doc_filename)``
    tuples already present in the persisted manifest with a terminal
    ``fetch_status``. When provided, U7's driver passes the current
    ``done_fetches(manifest)`` so this function can skip BOTH the HTTP
    fetch AND the manifest re-emission for documents the persisted
    manifest already records -- the caller will keep the existing
    manifest row unchanged, so re-emitting would create a duplicate.
    Documents not in ``done_set`` are processed normally (fetch or
    on-disk re-emit).
    """
    output_root = Path(output_root)
    accession = accession_row["adsh"]
    acc_nd = _accession_no_dashes(accession)
    ciks = accession_row.get("ciks") or []
    if not ciks:
        raise ValueError(
            f"accession_row for {accession!r} has empty 'ciks'; cannot "
            f"determine firm directory"
        )
    cik_padded = _pad_cik(ciks[0])
    cik_unpadded = _unpadded_cik(cik_padded)
    firm_slug = _lookup_firm_slug(registry_df, cik_padded)
    form = accession_row.get("form") or ""
    filed_date = accession_row.get("file_date") or ""
    phrase_variants = accession_row.get("phrase_variants_matched") or ""
    discovery_primary_doc = accession_row.get("primary_doc")

    firm_dir = output_root / f"{firm_slug}_{cik_padded}" / acc_nd

    # Fetch + parse the index page. A failure here is fatal for this
    # accession (no documents can be classified) and is reported as a
    # single ``parse-error`` manifest row keyed on the accession itself.
    try:
        index_df = fetch_filing_index_html(cik_padded, accession, client=client)
    except Exception as exc:
        return [
            {
                "firm_slug": firm_slug,
                "cik": cik_padded,
                "accession": accession,
                "form": form,
                "filed_date": filed_date,
                "doc_filename": "",
                "doc_type": "",
                "doc_description": "",
                "url": (
                    f"{ARCHIVES_BASE}/{cik_unpadded}/{acc_nd}/"
                    f"{accession}-index.htm"
                ),
                "phrase_variants_matched": phrase_variants,
                "exhibit_match_source": "primary-doc",
                "fetch_status": _classify_status(exc),
                "fetch_ts": _now_iso(),
                "byte_size": None,
            }
        ]

    targets = _select_targets(index_df, discovery_primary_doc)
    if not targets:
        # An index with no classifiable documents is unusual but
        # possible (e.g., a 6-K from a foreign issuer with only data
        # files). Emit no manifest rows.
        return []

    out_rows: list[dict[str, Any]] = []
    for tgt in targets:
        row = tgt["row"]
        source = tgt["source"]
        filename = row["name"]
        doc_type = row["type"] or ""
        doc_description = row["description"] or ""
        url = f"{ARCHIVES_BASE}/{cik_unpadded}/{acc_nd}/{filename}"
        dest = firm_dir / filename

        # R15 fast-path: if the persisted manifest already records a
        # terminal row for this (accession, filename), skip both the
        # fetch and the manifest re-emission. The driver keeps the
        # existing manifest row untouched.
        if done_set is not None and (accession, filename) in done_set:
            continue

        if dest.exists():
            # File-tree-only re-emit: discovery-derived fields are NOT
            # NULL; size from ``os.stat``.
            stat = dest.stat()
            out_rows.append(
                {
                    "firm_slug": firm_slug,
                    "cik": cik_padded,
                    "accession": accession,
                    "form": form,
                    "filed_date": filed_date,
                    "doc_filename": filename,
                    "doc_type": doc_type,
                    "doc_description": doc_description,
                    "url": url,
                    "phrase_variants_matched": phrase_variants,
                    "exhibit_match_source": source,
                    "fetch_status": "success",
                    "fetch_ts": _stat_iso(dest),
                    "byte_size": int(stat.st_size),
                }
            )
            continue

        # New fetch.
        try:
            body = fetch_document(
                cik_padded, accession, filename, client=client
            )
        except Exception as exc:
            out_rows.append(
                {
                    "firm_slug": firm_slug,
                    "cik": cik_padded,
                    "accession": accession,
                    "form": form,
                    "filed_date": filed_date,
                    "doc_filename": filename,
                    "doc_type": doc_type,
                    "doc_description": doc_description,
                    "url": url,
                    "phrase_variants_matched": phrase_variants,
                    "exhibit_match_source": source,
                    "fetch_status": _classify_status(exc),
                    "fetch_ts": _now_iso(),
                    "byte_size": None,
                }
            )
            continue

        # ``fetch_document`` returns bytes for binary docs, str for text.
        if isinstance(body, str):
            payload = body.encode("utf-8")
        else:
            payload = body
        _atomic_write_bytes(dest, payload)

        out_rows.append(
            {
                "firm_slug": firm_slug,
                "cik": cik_padded,
                "accession": accession,
                "form": form,
                "filed_date": filed_date,
                "doc_filename": filename,
                "doc_type": doc_type,
                "doc_description": doc_description,
                "url": url,
                "phrase_variants_matched": phrase_variants,
                "exhibit_match_source": source,
                "fetch_status": "success",
                "fetch_ts": _now_iso(),
                "byte_size": int(dest.stat().st_size),
            }
        )

    return out_rows


def _self_test() -> None:
    """Operator-invoked sanity check against a known TRA 8-K accession.

    Uses the Repay Holdings 2019-07-17 8-K (CIK 1720592, accession
    0001213900-19-013004), which has 17 EX-10.* exhibits, of which
    exactly one (EX-10.2) is the TRA. The discovery row in the test
    fixture names that EX-10.2 as the ``primary_doc`` (i.e. the full-
    text-search hit landed on the TRA exhibit), so the expected
    classification is: one ``phrase-match`` (or ``both`` if the TRA's
    description also matches the regex, which it does -- ``TAX
    RECEIVABLE AGREEMENT, DATED JULY 11, 2019, ...``) on the EX-10.2,
    plus one ``primary-doc`` on the 8-K body. No other EX-10s match the
    description regex, so no further documents are fetched.
    """
    test_cik_padded = "0001720592"
    test_accession = "0001213900-19-013004"
    expected_8k = "f8k0719_repayholdings.htm"
    expected_tra_ex10 = "f8k0719ex10-2_repayhold.htm"

    # Synthetic 1-row registry.
    registry_df = pl.DataFrame(
        {
            "cik": [test_cik_padded],
            "current_name": ["Repay Holdings Corp"],
            "slug": ["repay-holdings-corp"],
            "former_names": ["[]"],
            "first_filing_date": ["2017-08-21"],
            "last_filing_date": ["2025-01-01"],
            "sic": ["6199"],
        },
        schema={
            "cik": pl.String,
            "current_name": pl.String,
            "slug": pl.String,
            "former_names": pl.String,
            "first_filing_date": pl.String,
            "last_filing_date": pl.String,
            "sic": pl.String,
        },
    )

    # Synthetic accession_row. ``primary_doc`` points at the TRA EX-10
    # to exercise the phrase-match branch (the search hit landed on the
    # exhibit, not the 8-K body).
    accession_row = {
        "adsh": test_accession,
        "primary_doc": expected_tra_ex10,
        "ciks": [test_cik_padded],
        "form": "8-K",
        "file_date": "2019-07-17",
        "phrase_variants_matched": '"tax receivable agreement"',
    }

    tmp_dir = Path(
        tempfile.mkdtemp(prefix="phase1-acquisition-selftest-")
    )
    try:
        with EdgarClient() as client:
            rows = acquire_filing(
                accession_row, registry_df, tmp_dir, client
            )

        # Basic shape.
        assert rows, "acquire_filing returned no manifest rows"
        for row in rows:
            assert set(row.keys()) == set(MANIFEST_FIELDS), (
                f"manifest row keys {sorted(row.keys())} != "
                f"MANIFEST_FIELDS {sorted(MANIFEST_FIELDS)}"
            )

        sources = [r["exhibit_match_source"] for r in rows]
        filenames = [r["doc_filename"] for r in rows]
        statuses = [r["fetch_status"] for r in rows]

        # The 8-K body and the TRA EX-10 must both be fetched.
        assert expected_8k in filenames, (
            f"expected primary 8-K {expected_8k!r} in filenames {filenames}"
        )
        assert expected_tra_ex10 in filenames, (
            f"expected TRA EX-10 {expected_tra_ex10!r} in filenames {filenames}"
        )

        # At least one primary-doc and at least one of phrase-match/both
        # must appear among the sources.
        assert "primary-doc" in sources, (
            f"expected at least one primary-doc row; sources={sources}"
        )
        assert ("phrase-match" in sources) or ("both" in sources), (
            f"expected at least one phrase-match or both row; sources={sources}"
        )

        # No description-only EX-10 in this fixture (only EX-10.2 has a
        # TRA-matching description, and it is the phrase hit so it is
        # classified as 'both' rather than 'description-match'). Other
        # EX-10s must therefore NOT have been fetched.
        for unmatched in (
            "f8k0719ex10-1_repayhold.htm",
            "f8k0719ex10-3_repayhold.htm",
        ):
            assert unmatched not in filenames, (
                f"unmatched EX-10 {unmatched!r} was fetched; "
                f"filenames={filenames}"
            )

        # All attempted fetches should have terminal status; for this
        # fixture, all should be 'success'.
        for row in rows:
            assert row["fetch_status"] == "success", (
                f"unexpected non-success status for {row['doc_filename']!r}: "
                f"{row['fetch_status']}"
            )
            # File must exist on disk and match the manifest byte_size.
            dest = (
                tmp_dir
                / f"repay-holdings-corp_{test_cik_padded}"
                / _accession_no_dashes(test_accession)
                / row["doc_filename"]
            )
            assert dest.exists(), f"expected file on disk: {dest}"
            assert row["byte_size"] == dest.stat().st_size, (
                f"manifest byte_size {row['byte_size']} != on-disk "
                f"{dest.stat().st_size} for {dest}"
            )

        # Idempotency check: a second call should not refetch (files
        # already on disk) and should emit re-emitted rows with the same
        # source classification and the same byte_size.
        with EdgarClient() as client:
            rows2 = acquire_filing(
                accession_row, registry_df, tmp_dir, client
            )
        assert len(rows2) == len(rows), (
            f"second-call row count {len(rows2)} != first-call {len(rows)}"
        )
        for r in rows2:
            assert r["fetch_status"] == "success"
            # discovery-derived field carried through on the re-emit
            assert r["phrase_variants_matched"], (
                f"phrase_variants_matched lost on re-emit: {r}"
            )

        # Report the source breakdown so the operator can spot-check.
        from collections import Counter

        breakdown = Counter(sources)
        print(
            f"acquired {len(rows)} documents; "
            f"source breakdown: {dict(breakdown)}",
            flush=True,
        )
        for r in rows:
            print(
                f"  {r['exhibit_match_source']:>17}  "
                f"{r['doc_type']:>8}  {r['doc_filename']}  "
                f"({r['byte_size']} bytes, status={r['fetch_status']})",
                flush=True,
            )

        print("OK", flush=True)
    finally:
        # Clean up temp tree recursively.
        for root, dirs, files in os.walk(tmp_dir, topdown=False):
            for name in files:
                Path(root, name).unlink()
            for name in dirs:
                Path(root, name).rmdir()
        tmp_dir.rmdir()


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
