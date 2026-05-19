"""Archives bulk-data handler.

Fetches primary filing documents from
``https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-no-dashes>/<filename>``.

Two operations:

- :func:`fetch_filing_index` reads the filing's ``index.json``, which
  lists every document in the submission.
- :func:`fetch_document` reads a named document from the filing folder.

Binary content (PDF, ZIP) is returned as ``bytes``; text content (HTML,
XML, JSON, TXT) is returned as ``str`` decoded as UTF-8 with replacement
on undecodable bytes.

Cache layout:
``.tra_history_cache/edgar_archives/<CIK>/<accession_no_dashes>/<filename>``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import polars as pl

from sec_edgar.client import EdgarClient

CACHE_ROOT = Path(".tra_history_cache/edgar_archives")
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_MAX_AGE_S = 30 * 24 * 3600  # 30 days; filings are immutable once accepted

# Extensions that should be returned as text (str).
_TEXT_EXTS = {".htm", ".html", ".xml", ".json", ".txt", ".css", ".xsd"}


def _strip_cik(cik: str | int) -> str:
    s = str(cik).strip().lstrip("0")
    if not s.isdigit():
        raise ValueError(f"CIK must be digits, got {cik!r}")
    return s


def _accession_no_dashes(accession: str) -> str:
    s = accession.strip()
    out = s.replace("-", "")
    if len(out) != 18 or not out.isdigit():
        raise ValueError(
            f"accession must be 18 digits with dashes (e.g. "
            f"0000320193-23-000106); got {accession!r}"
        )
    return out


def _filing_dir(cik: str | int, accession: str) -> str:
    return f"{_strip_cik(cik)}/{_accession_no_dashes(accession)}"


def fetch_filing_index(
    cik: str | int,
    accession: str,
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
) -> pl.LazyFrame:
    """Fetch ``index.json`` for a filing; return a LazyFrame of documents.

    Columns at minimum: ``name``, ``type``, ``size``, ``last_modified``.
    """
    cik_n = _strip_cik(cik)
    acc_nd = _accession_no_dashes(accession)
    url = f"{ARCHIVES_BASE}/{cik_n}/{acc_nd}/index.json"
    cache_path = cache_root / cik_n / acc_nd / "index.json"

    own = client is None
    cli = client if client is not None else EdgarClient()
    try:
        body, _meta = cli.get(
            url, cache_path=cache_path, cache_max_age_s=cache_max_age_s
        )
    finally:
        if own:
            cli.close()
    payload = json.loads(body)
    items = payload.get("directory", {}).get("item", [])
    if not isinstance(items, list):
        raise ValueError(
            f"unexpected index.json shape at {url}: directory.item not a list"
        )
    if not items:
        return pl.LazyFrame(schema={"name": pl.String})
    return pl.DataFrame(items).lazy()


def fetch_document(
    cik: str | int,
    accession: str,
    filename: str,
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
    as_text: bool | None = None,
) -> bytes | str:
    """Fetch a named document from a filing folder.

    Returns ``bytes`` for binary documents and ``str`` for text documents.
    ``as_text`` overrides the extension-based default if supplied.
    """
    if "/" in filename or ".." in filename:
        raise ValueError(f"filename must be a leaf name, got {filename!r}")
    cik_n = _strip_cik(cik)
    acc_nd = _accession_no_dashes(accession)
    url = f"{ARCHIVES_BASE}/{cik_n}/{acc_nd}/{filename}"
    cache_path = cache_root / cik_n / acc_nd / filename

    own = client is None
    cli = client if client is not None else EdgarClient()
    try:
        body, _meta = cli.get(
            url, cache_path=cache_path, cache_max_age_s=cache_max_age_s
        )
    finally:
        if own:
            cli.close()

    if as_text is None:
        ext = Path(filename).suffix.lower()
        as_text = ext in _TEXT_EXTS
    if as_text:
        return body.decode("utf-8", errors="replace")
    return body


def _self_test() -> None:
    """Trial run: list the Apple 10-K (2023) filing documents, fetch one."""
    cik = "0000320193"
    accession = "0000320193-23-000106"
    lf = fetch_filing_index(cik, accession)
    df = lf.collect()
    print(f"index.json doc count: {df.height}")
    cols_show = [c for c in ("name", "type", "size") if c in df.columns]
    print(df.select(cols_show).head(10))
    # The primary document name for this filing is aapl-20230930.htm.
    primary = "aapl-20230930.htm"
    if primary not in df["name"].to_list():
        raise RuntimeError(
            f"expected {primary} in index, got {df['name'].to_list()[:10]}"
        )
    body = fetch_document(cik, accession, primary)
    if not isinstance(body, str):
        raise RuntimeError(f"expected str body for HTML, got {type(body).__name__}")
    print(f"primary doc bytes: {len(body):,}  first-80: {body[:80]!r}")


if __name__ == "__main__":
    _self_test()
