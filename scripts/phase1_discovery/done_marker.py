"""Phase 1 done marker: write / read / delete .phase1-done.

Implements R14 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md.

The done marker lives at ``data/tra-mentions/.phase1-done`` and is the
gate Phase 2 reads to know that the corresponding manifest is complete:
its absence means "in progress or never run", its presence means "the
manifest at ``manifest_path`` is the canonical Phase 1 output for the
recorded date range". The marker is deleted unconditionally at the
start of a Phase 1 run (R15) and rewritten on successful completion.

The marker carries enough state for Phase 2 to detect a manifest that
has drifted out from under the marker (e.g., the operator hand-edited
the parquet between runs): the recorded ``manifest_sha256`` is the
SHA-256 of the manifest file bytes at write time. A mismatch on read
is Phase 2's signal to refuse to consume the manifest.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import polars as pl
import yaml

from phase1_discovery.manifest import (
    MANIFEST_SCHEMA,
    _now_iso,
    write_manifest_atomic,
)


MARKER_PATH: Path = Path("data/tra-mentions/.phase1-done")


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file's bytes, streaming in 1 MiB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_marker(
    start_date: str,
    end_date: str,
    manifest_path: str | Path,
    marker_path: str | Path | None = None,
    manifest_rows: int | None = None,
) -> None:
    """Write the done-marker YAML at ``marker_path`` (default ``MARKER_PATH``).

    Computes the SHA-256 of the manifest file bytes. The manifest must
    exist on disk at ``manifest_path`` before this is called --
    ``write_marker`` is the last step of a successful Phase 1 run,
    after the manifest has been atomically committed.

    ``manifest_rows`` is the row count to record in the marker. When
    None (the default and the ``_self_test`` path), the manifest
    parquet is re-read from disk to count rows. The driver passes
    ``manifest_rows=len(manifest_df)`` to avoid re-reading a parquet
    it already has in memory.
    """
    manifest_p = Path(manifest_path)
    if not manifest_p.exists():
        raise FileNotFoundError(
            f"manifest does not exist at {manifest_p}; write_marker is "
            f"called after the manifest is committed"
        )

    if manifest_rows is None:
        manifest_rows = int(pl.read_parquet(manifest_p).height)

    payload = {
        "start_date": start_date,
        "end_date": end_date,
        "manifest_path": str(manifest_path),
        "manifest_rows": int(manifest_rows),
        "manifest_sha256": _sha256_file(manifest_p),
        "completed_at": _now_iso(),
    }

    dest = Path(marker_path) if marker_path is not None else MARKER_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    # yaml.safe_dump with sort_keys=False preserves the canonical order
    # documented in the plan (start_date, end_date, manifest_path,
    # manifest_rows, manifest_sha256, completed_at).
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    dest.write_text(text, encoding="utf-8")


def delete_marker_if_exists(marker_path: str | Path | None = None) -> None:
    """Silently delete the marker if present; no-op if absent."""
    dest = Path(marker_path) if marker_path is not None else MARKER_PATH
    try:
        dest.unlink()
    except FileNotFoundError:
        pass


def read_marker(marker_path: str | Path | None = None) -> dict | None:
    """Parse and return the marker YAML; return ``None`` if absent."""
    dest = Path(marker_path) if marker_path is not None else MARKER_PATH
    if not dest.exists():
        return None
    text = dest.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _self_test() -> None:
    """Round-trip the marker against a synthetic manifest in a temp dir.

    No live EDGAR calls. Exercises:
      - ``write_marker`` writes valid YAML with the documented six fields.
      - ``read_marker`` parses it back to a dict.
      - The recorded ``manifest_sha256`` matches a recomputed digest.
      - ``delete_marker_if_exists`` removes it; a subsequent
        ``read_marker`` returns ``None``.
      - ``delete_marker_if_exists`` on an absent marker is a no-op.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="phase1-done-marker-selftest-"))
    try:
        # Synthetic 2-row manifest committed via the manifest module.
        manifest_path = tmp_dir / "manifest.parquet"
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
        ]
        df = pl.DataFrame(rows, schema=MANIFEST_SCHEMA)
        write_manifest_atomic(df, manifest_path)

        marker_path = tmp_dir / ".phase1-done"

        # read on absent returns None.
        assert read_marker(marker_path) is None

        # delete on absent is a no-op.
        delete_marker_if_exists(marker_path)
        assert not marker_path.exists()

        # write, then read.
        write_marker(
            "2024-06-01",
            "2024-06-30",
            manifest_path,
            marker_path=marker_path,
        )
        assert marker_path.exists()

        parsed = read_marker(marker_path)
        assert isinstance(parsed, dict)
        expected_keys = {
            "start_date",
            "end_date",
            "manifest_path",
            "manifest_rows",
            "manifest_sha256",
            "completed_at",
        }
        assert set(parsed.keys()) == expected_keys, (
            f"marker keys {sorted(parsed.keys())} != {sorted(expected_keys)}"
        )
        assert parsed["start_date"] == "2024-06-01"
        assert parsed["end_date"] == "2024-06-30"
        assert parsed["manifest_path"] == str(manifest_path)
        assert parsed["manifest_rows"] == 2
        # Recompute the digest and verify match.
        expected_sha = _sha256_file(manifest_path)
        assert parsed["manifest_sha256"] == expected_sha, (
            f"recorded sha {parsed['manifest_sha256']!r} != recomputed "
            f"{expected_sha!r}"
        )
        # completed_at is an ISO-8601 string we can parse.
        _dt.datetime.fromisoformat(parsed["completed_at"])

        # delete; subsequent read returns None.
        delete_marker_if_exists(marker_path)
        assert not marker_path.exists()
        assert read_marker(marker_path) is None

        # write_marker on a missing manifest raises.
        try:
            write_marker(
                "2024-06-01",
                "2024-06-30",
                tmp_dir / "no-such-manifest.parquet",
                marker_path=marker_path,
            )
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(
                "write_marker accepted a missing manifest path"
            )

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
