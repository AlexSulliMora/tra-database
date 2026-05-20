"""Pull the EX-10.* exhibits listed in a candidates parquet.

Reads a parquet of matched EX-10 documents (the output of
``scripts/find_candidates.py``). That parquet now carries one row per
matched EX-10 document: EDGAR full-text search already identified the
exact document the TRA phrase matched, so each row is exactly one file to
download. No filing-index round-trip and no filename guessing is needed.

Output layout::

    data/edgar-query/exhibits/
    ├── manifest.csv
    └── <CIK>/
        └── <accession>_<primary_doc>

Invocation::

    PYTHONPATH=scripts pixi run python scripts/pull_exhibits.py \\
      --parquet data/edgar-query/full-text.parquet \\
      --output-dir data/edgar-query/exhibits/

Idempotent: documents already on disk are skipped. The manifest is
written fresh each run (overwritten, not appended): one row per document
in the input parquet that was successfully fetched or already on disk.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx
import polars as pl

from sec_edgar.client import EdgarClient
from sec_edgar.archives import fetch_document


def _retry_5xx(fn, *args, max_attempts: int = 3, backoff_s: float = 1.5, **kwargs):
    """Retry fn on HTTP 5xx; pass through everything else."""
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_attempts - 1:
                time.sleep(backoff_s)
                continue
            raise


MANIFEST_HEADER = [
    "cik",
    "accession",
    "filename",
    "file_type",
    "filing_date",
    "form",
    "phrase_variants_matched",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet",
        type=Path,
        default=Path("data/edgar-query/full-text.parquet"),
        help="Input parquet of EX-10 documents (output of find_candidates.py).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/edgar-query/exhibits"),
        help="Directory for per-CIK exhibit folders and manifest.csv.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of input documents (for testing).",
    )
    args = parser.parse_args()

    parquet_path: Path = args.parquet
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"

    def log(msg: str) -> None:
        print(msg, flush=True)

    if not parquet_path.exists():
        log(f"ERROR: input parquet not found: {parquet_path}")
        return 1

    df = pl.read_parquet(parquet_path)
    if args.limit is not None:
        df = df.head(args.limit)
    log(f"pull_exhibits: {df.height} EX-10 documents from {parquet_path}")

    # Manifest is written fresh each run (overwrite, not append): the old
    # broad pull is being replaced, so a stale appended manifest would be
    # wrong.
    manifest_f = manifest_path.open("w", newline="", encoding="utf-8")
    writer = csv.DictWriter(manifest_f, fieldnames=MANIFEST_HEADER)
    writer.writeheader()
    manifest_f.flush()

    total_pulled = 0
    total_skipped = 0
    total_failed = 0
    total_no_doc = 0
    with EdgarClient() as client:
        for row in df.iter_rows(named=True):
            ciks = row.get("ciks")
            if not ciks:
                log(f"  skip: row with no ciks adsh={row.get('adsh')}")
                total_no_doc += 1
                continue
            cik = ciks[0]
            adsh = row["adsh"]
            filename = row.get("primary_doc")
            if not filename:
                log(f"  skip: row with no primary_doc cik={cik} adsh={adsh}")
                total_no_doc += 1
                continue

            dest_dir = output_dir / cik
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{adsh}_{filename}"

            if dest.exists():
                total_skipped += 1
            else:
                try:
                    body = _retry_5xx(
                        fetch_document, cik, adsh, filename, client=client
                    )
                except Exception as e:
                    log(
                        f"  fetch_document failed cik={cik} adsh={adsh} "
                        f"file={filename}: {type(e).__name__}: {e}"
                    )
                    total_failed += 1
                    continue
                if isinstance(body, str):
                    dest.write_text(body, encoding="utf-8")
                else:
                    dest.write_bytes(body)
                total_pulled += 1

            writer.writerow(
                {
                    "cik": cik,
                    "accession": adsh,
                    "filename": filename,
                    "file_type": row.get("file_type") or "",
                    "filing_date": row.get("file_date") or "",
                    "form": row.get("form") or "",
                    "phrase_variants_matched": row.get(
                        "phrase_variants_matched"
                    )
                    or "",
                }
            )
            manifest_f.flush()

    manifest_f.close()

    log(
        f"done. documents downloaded this run: {total_pulled}; "
        f"already on disk: {total_skipped}; "
        f"fetch failures: {total_failed}; "
        f"rows with no document reference: {total_no_doc}"
    )
    log(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
