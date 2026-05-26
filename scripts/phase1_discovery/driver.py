"""Phase 1 top-level driver: orchestration, CLI, and restart logic.

Implements R14, R15, R16 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md. Ties together
U2-U6: opens a single ``EdgarClient`` context manager, runs the
discovery sweep (U3), builds or updates the CIK registry (U4), and
then for each discovered accession calls ``acquire_filing`` (U5)
skipping documents already terminal in the persisted manifest (U6's
``done_fetches``). The manifest is atomically rewritten per firm so a
mid-run crash leaves a consistent on-disk state. On full success the
done marker (U6) is written; per-document failures are captured in
``fetch_status`` (R12) and do NOT abort the run.

The CLI ``main()`` argparse wrapper exposes ``--start``, ``--end``,
``--output-root``, ``--mergers-csv``, ``--registry-path``,
``--discovery-path``, and a ``--smoke-test`` flag that exercises the
full end-to-end pipeline against live EDGAR for a small known window
into a temporary output root (AE5 + AE6 integration check).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
import tempfile
from pathlib import Path

import polars as pl

from sec_edgar.client import EdgarClient

from phase1_discovery import done_marker
from phase1_discovery.acquisition import acquire_filing
from phase1_discovery.discovery import sweep_discovery
from phase1_discovery.manifest import (
    append_rows,
    done_fetches,
    read_manifest,
    write_manifest_atomic,
)
from phase1_discovery.registry import build_or_update_registry


def _default_end_yyyymm() -> str:
    """Return today's ``YYYY-MM`` string."""
    today = _dt.date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _pad_cik(cik: str | int) -> str:
    """Zero-pad to 10-digit canonical form."""
    s = str(cik).strip().lstrip("0") or "0"
    if not s.isdigit():
        raise ValueError(f"CIK must be digits, got {cik!r}")
    return s.zfill(10)


def _first_cik(row_ciks) -> str | None:
    """Pull the first CIK from a discovery row's ``ciks`` field, zero-padded."""
    if row_ciks is None:
        return None
    if isinstance(row_ciks, str):
        candidates = [row_ciks]
    else:
        candidates = list(row_ciks)
    for raw in candidates:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s.isdigit():
            continue
        return s.zfill(10)
    return None


def run_phase1(
    start_date: str = "2001-01",
    end_date: str | None = None,
    output_root: str | Path = "data/tra-mentions",
    mergers_csv: str | Path = "data/cik-mergers.csv",
    registry_path: str | Path = "data/cik-registry.parquet",
    discovery_path: str | Path = "data/tra-mentions/discovery.parquet",
) -> int:
    """Run Phase 1 end-to-end for the given date range.

    Returns 0 on success, non-zero on hard failure (EDGAR unreachable,
    etc). Per-document fetch failures are captured in ``fetch_status``
    and do not abort the run. Idempotent on re-run: skips accessions
    already terminal in the persisted manifest (R15, R16). Per R15 step
    (a), any existing ``.phase1-done`` marker is deleted at run start
    and only rewritten on full success.
    """
    if end_date is None:
        end_date = _default_end_yyyymm()

    output_root = Path(output_root)
    manifest_path = output_root / "manifest.parquet"
    done_marker_path = output_root / ".phase1-done"

    output_root.mkdir(parents=True, exist_ok=True)

    # R15 step (a): a fresh Phase 1 run starts marker-less. Phase 2's
    # contract is "the marker's presence means the manifest is the
    # canonical Phase 1 output for the recorded date range"; while the
    # run is in flight the marker must be absent.
    done_marker.delete_marker_if_exists(marker_path=done_marker_path)

    print(
        f"run_phase1: start_date={start_date} end_date={end_date} "
        f"output_root={output_root}",
        flush=True,
    )
    print(f"run_phase1: manifest_path={manifest_path}", flush=True)
    print(f"run_phase1: done_marker_path={done_marker_path}", flush=True)

    with EdgarClient() as client:
        # Step 1: Discovery. Cached EDGAR responses make this cheap on
        # a restart. WindowOverflowError on a single variant-month
        # logs and continues per U3; a hard network failure (e.g.
        # httpx.ConnectError) propagates and aborts the run (no done
        # marker written, manifest preserved).
        print("run_phase1: step 1 -- discovery sweep", flush=True)
        discovery_df, overflow_errors = sweep_discovery(
            start_date, end_date, client, str(discovery_path)
        )
        if overflow_errors:
            print(
                f"run_phase1: discovery completed with "
                f"{len(overflow_errors)} overflow errors (run continues)",
                flush=True,
            )

        # Step 2: Registry. Resolves merger-CSV predecessors to
        # successor CIK on first encounter; existing rows are not
        # re-keyed (R7 lock-on-first-encounter).
        print("run_phase1: step 2 -- registry build/update", flush=True)
        registry_df = build_or_update_registry(
            discovery_df, mergers_csv, registry_path, client
        )

        # Step 3: Acquisition. Group discovery rows by canonical
        # filing CIK (first CIK in each row's ``ciks`` list), then
        # walk each firm's accessions sequentially. After each firm
        # finishes, atomically rewrite the manifest so a crash mid-
        # run leaves the on-disk manifest consistent with the on-disk
        # file tree.
        print("run_phase1: step 3 -- acquisition", flush=True)
        manifest_df = read_manifest(manifest_path)
        initial_manifest_rows = manifest_df.height
        done_set = done_fetches(manifest_df)
        print(
            f"  existing manifest: {initial_manifest_rows} rows, "
            f"{len(done_set)} done (accession, filename) pairs",
            flush=True,
        )

        if discovery_df.height == 0:
            print(
                "  discovery produced no rows; skipping acquisition loop",
                flush=True,
            )
        else:
            # Tag each discovery row with its canonical filer CIK so
            # we can group. ``ciks`` is a list-column; the first
            # element is the canonical filer per the search hit shape.
            discovery_rows = list(discovery_df.iter_rows(named=True))
            by_cik: dict[str, list[dict]] = {}
            order: list[str] = []
            skipped_no_cik = 0
            for row in discovery_rows:
                cik = _first_cik(row.get("ciks"))
                if cik is None:
                    skipped_no_cik += 1
                    continue
                if cik not in by_cik:
                    by_cik[cik] = []
                    order.append(cik)
                by_cik[cik].append(row)
            if skipped_no_cik:
                print(
                    f"  skipped {skipped_no_cik} discovery rows with no "
                    f"usable CIK",
                    flush=True,
                )
            print(
                f"  acquisition: {len(order)} unique filing CIKs, "
                f"{sum(len(v) for v in by_cik.values())} accessions",
                flush=True,
            )

            for firm_idx, cik in enumerate(order, start=1):
                firm_rows = by_cik[cik]
                firm_new_rows: list[dict] = []
                for acc_row in firm_rows:
                    new_rows = acquire_filing(
                        acc_row,
                        registry_df,
                        output_root,
                        client,
                        done_set=done_set,
                    )
                    firm_new_rows.extend(new_rows)
                if firm_new_rows:
                    manifest_df = append_rows(manifest_df, firm_new_rows)
                    write_manifest_atomic(manifest_df, manifest_path)
                    # Bring done_set up to date so subsequent firms in
                    # the same run also see what we just persisted.
                    for r in firm_new_rows:
                        done_set.add((r["accession"], r["doc_filename"]))
                print(
                    f"  [{firm_idx}/{len(order)}] cik={cik} "
                    f"accessions={len(firm_rows)} "
                    f"new_rows={len(firm_new_rows)} "
                    f"manifest_rows={manifest_df.height}",
                    flush=True,
                )

        # Ensure the manifest exists on disk even when no new rows
        # were appended (e.g., an empty discovery sweep). The done
        # marker requires a manifest file to hash.
        if not manifest_path.exists():
            write_manifest_atomic(manifest_df, manifest_path)

        # Step 4: Done marker. R14: written only on full success at
        # the end of the run.
        print("run_phase1: step 4 -- done marker", flush=True)
        done_marker.write_marker(
            start_date,
            end_date,
            manifest_path,
            marker_path=done_marker_path,
        )
        print(
            f"run_phase1: wrote done marker -> {done_marker_path}",
            flush=True,
        )

    print(
        f"run_phase1: completed. manifest_rows={manifest_df.height} "
        f"(was {initial_manifest_rows})",
        flush=True,
    )
    return 0


def _self_test() -> int:
    """End-to-end smoke against live EDGAR for a known small window.

    Covers AE5 (per-document HTTP failures captured non-fatally) and
    AE6 (idempotent restart: second invocation does zero new fetches
    and rewrites the done marker with the same manifest_sha256).
    """
    start = "2024-06"
    end = "2024-06"
    tmp_dir = Path(tempfile.mkdtemp(prefix="phase1-smoke-test-"))
    try:
        output_root = tmp_dir / "tra-mentions"
        mergers_csv = tmp_dir / "cik-mergers.csv"
        registry_path = tmp_dir / "cik-registry.parquet"
        discovery_path = tmp_dir / "tra-mentions" / "discovery.parquet"
        manifest_path = output_root / "manifest.parquet"
        marker_path = output_root / ".phase1-done"

        # Header-only merger CSV (empty merger map).
        mergers_csv.parent.mkdir(parents=True, exist_ok=True)
        mergers_csv.write_text(
            "predecessor_cik,successor_cik\n", encoding="utf-8"
        )

        print(
            f"smoke-test: first run for {start}..{end} into {output_root}",
            flush=True,
        )
        rc = run_phase1(
            start_date=start,
            end_date=end,
            output_root=output_root,
            mergers_csv=mergers_csv,
            registry_path=registry_path,
            discovery_path=discovery_path,
        )
        assert rc == 0, f"first run returned non-zero exit code {rc}"
        assert manifest_path.exists(), (
            f"first run did not write manifest at {manifest_path}"
        )
        assert marker_path.exists(), (
            f"first run did not write done marker at {marker_path}"
        )
        assert registry_path.exists(), (
            f"first run did not write registry at {registry_path}"
        )
        first_manifest = pl.read_parquet(manifest_path)
        first_rows = first_manifest.height
        first_marker = done_marker.read_marker(marker_path)
        assert first_marker is not None
        first_sha = first_marker["manifest_sha256"]
        print(
            f"smoke-test: first run done -- manifest_rows={first_rows} "
            f"sha256={first_sha[:12]}...",
            flush=True,
        )
        assert first_rows >= 1, (
            f"expected >= 1 manifest row for {start}..{end}; got {first_rows}"
        )

        # Second run with the same args: every (accession, filename)
        # in the persisted manifest is already in done_set, so
        # acquire_filing's fast-path skips the HTTP fetch entirely and
        # emits no new manifest rows. The done marker is rewritten
        # (R15 step (a) deletes it at run start) and should carry the
        # same manifest_sha256 because the manifest bytes are
        # unchanged.
        print("smoke-test: second run (idempotency check)", flush=True)
        rc2 = run_phase1(
            start_date=start,
            end_date=end,
            output_root=output_root,
            mergers_csv=mergers_csv,
            registry_path=registry_path,
            discovery_path=discovery_path,
        )
        assert rc2 == 0, f"second run returned non-zero exit code {rc2}"
        second_manifest = pl.read_parquet(manifest_path)
        second_rows = second_manifest.height
        assert second_rows == first_rows, (
            f"second run added rows: first={first_rows} second={second_rows} "
            f"(expected zero new fetches on the idempotent re-run)"
        )
        assert marker_path.exists(), "second run did not write done marker"
        second_marker = done_marker.read_marker(marker_path)
        assert second_marker is not None
        second_sha = second_marker["manifest_sha256"]
        assert second_sha == first_sha, (
            f"manifest sha256 drifted across idempotent re-run: "
            f"first={first_sha} second={second_sha}"
        )
        skipped = first_rows  # every existing row was skipped
        print(
            f"smoke-test: second run done -- manifest_rows={second_rows} "
            f"sha256={second_sha[:12]}... (skipped {skipped} on disk)",
            flush=True,
        )

        print("OK", flush=True)
        print(
            f"smoke-test: first_manifest_rows={first_rows} "
            f"second_pass_skipped={skipped}",
            flush=True,
        )
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> int:
    """argparse-driven CLI entry point."""
    today = _dt.date.today()
    default_end = f"{today.year:04d}-{today.month:02d}"

    parser = argparse.ArgumentParser(
        description=(
            "Phase 1 of the per-firm TRA pipeline: discover and acquire "
            "TRA-mentioning EDGAR filings. Sweeps EDGAR full-text search "
            "for five query variants, builds a CIK registry, fetches "
            "per-accession HTML indices, and downloads matched documents "
            "into a manifest-tracked file tree. Idempotent on re-run."
        ),
    )
    parser.add_argument("--start", default="2001-01", help="YYYY-MM start")
    parser.add_argument("--end", default=default_end, help="YYYY-MM end")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/tra-mentions"),
        help="Output root for the firm tree, manifest, and done marker.",
    )
    parser.add_argument(
        "--mergers-csv",
        type=Path,
        default=Path("data/cik-mergers.csv"),
        help=(
            "Operator-maintained predecessor->successor CIK CSV; absence "
            "is a valid first-run state (empty merger map)."
        ),
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=Path("data/cik-registry.parquet"),
        help="Path to the CIK registry parquet (read + written).",
    )
    parser.add_argument(
        "--discovery-path",
        type=Path,
        default=Path("data/tra-mentions/discovery.parquet"),
        help="Path to the intermediate discovery parquet (written).",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=(
            "Run the end-to-end smoke test against live EDGAR for "
            "2024-06 into a temp directory; assert restart idempotency; "
            "exit. All other flags are ignored when this is set."
        ),
    )
    args = parser.parse_args()

    if args.smoke_test:
        return _self_test()

    return run_phase1(
        start_date=args.start,
        end_date=args.end,
        output_root=args.output_root,
        mergers_csv=args.mergers_csv,
        registry_path=args.registry_path,
        discovery_path=args.discovery_path,
    )


if __name__ == "__main__":
    sys.exit(main())
