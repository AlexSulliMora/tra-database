"""Archives bulk-data handler.

Fetches primary filing documents from
``https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-no-dashes>/<filename>``.

Three operations:

- :func:`fetch_filing_index` reads the filing's ``index.json``, which
  lists every document in the submission (filename, file-icon hint,
  size, last-modified). The ``type`` column from ``index.json`` is a
  file-icon hint (``text.gif``, ``image2.gif``), NOT the exhibit class.
- :func:`fetch_filing_index_html` reads the filing's per-accession
  HTML index page and parses its Documents table; this exposes the
  real exhibit ``Type`` (``EX-10.1``, ``EX-99``, ...) and the
  ``Description`` column that callers like Phase 1 acquisition need
  but which ``index.json`` does not carry.
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

import polars as pl
from bs4 import BeautifulSoup

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


def accession_no_dashes(accession: str) -> str:
    s = accession.strip()
    out = s.replace("-", "")
    if len(out) != 18 or not out.isdigit():
        raise ValueError(
            f"accession must be 18 digits with dashes (e.g. "
            f"0000320193-23-000106); got {accession!r}"
        )
    return out


def _filing_dir(cik: str | int, accession: str) -> str:
    return f"{_strip_cik(cik)}/{accession_no_dashes(accession)}"


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
    acc_nd = accession_no_dashes(accession)
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


# Polars schema for fetch_filing_index_html's return value. Column order
# is part of the contract with callers (Phase 1 acquisition pins on it).
_INDEX_HTML_SCHEMA: dict[str, pl.DataType] = {
    "seq": pl.Int64,
    "description": pl.String,
    "name": pl.String,
    "type": pl.String,
    "size": pl.String,
}


def fetch_filing_index_html(
    cik: str | int,
    accession: str,
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
) -> pl.DataFrame:
    """Fetch and parse the per-accession HTML filing-index page.

    Returns a polars DataFrame with one row per document in the filing,
    columns ``seq`` (Int64; null for rows where EDGAR leaves Seq blank,
    e.g. the bottom ``Complete submission text file`` row), ``description``
    (str), ``name`` (str), ``type`` (str), ``size`` (str). The ``type``
    column holds the real exhibit class (``EX-10.1``, ``EX-99.1``,
    ``8-K``, ``GRAPHIC``), distinct from :func:`fetch_filing_index`'s
    ``type`` which is a file-icon hint.

    The HTML page is fetched from the canonical
    ``<accession-with-dashes>-index.htm`` URL form (not the directory-
    listing form, which 301-redirects to add a trailing slash and
    interacts badly with the URL-keyed response cache).

    Parses both the ``summary='Document Format Files'`` table and the
    ``summary='Data Files'`` table (XBRL extension files), concatenated.
    A handful of historical filings predate the ``summary`` attribute;
    those fall back to ``class='tableFile'``.
    """
    cik_n = _strip_cik(cik)
    acc_nd = accession_no_dashes(accession)
    # Accession-with-dashes is the original ``accession`` string after a
    # canonicalization-safe round-trip via ``accession_no_dashes`` (which
    # validates length and digits-only). Reinsert the two dashes.
    acc_dashed = f"{acc_nd[:10]}-{acc_nd[10:12]}-{acc_nd[12:]}"
    url = f"{ARCHIVES_BASE}/{cik_n}/{acc_nd}/{acc_dashed}-index.htm"
    cache_path = cache_root / cik_n / acc_nd / "index.htm"

    own = client is None
    cli = client if client is not None else EdgarClient()
    try:
        body, _meta = cli.get(
            url, cache_path=cache_path, cache_max_age_s=cache_max_age_s
        )
    finally:
        if own:
            cli.close()

    soup = BeautifulSoup(body, "html.parser")

    # Preferred: locate tables by ``summary`` attribute. Empirically the
    # filings index page has two: 'Document Format Files' (primary doc +
    # exhibits) and 'Data Files' (XBRL). Both share the same column
    # order, so we parse and concatenate.
    candidate_tables: list = []
    for summ in ("Document Format Files", "Data Files"):
        t = soup.find("table", summary=summ)
        if t is not None:
            candidate_tables.append(t)
    # Fallback: any ``class='tableFile'`` not already collected. This
    # covers older filings that may lack the ``summary`` attribute.
    if not candidate_tables:
        for t in soup.find_all("table", class_="tableFile"):
            candidate_tables.append(t)
    if not candidate_tables:
        raise ValueError(
            f"no Documents table found in index HTML at {url}"
        )

    rows: list[dict] = []
    for table in candidate_tables:
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 5:
                # Header row (th cells) or malformed row -- skip.
                continue
            seq_raw = cells[0].get_text(strip=True)
            try:
                seq: int | None = int(seq_raw) if seq_raw else None
            except ValueError:
                seq = None
            description = cells[1].get_text(strip=True)
            # Prefer the anchor text (clean filename); fall back to the
            # cell text. The Document cell sometimes contains an iXBRL
            # link with a styled span suffix; the anchor text is the
            # canonical filename without that decoration.
            doc_cell = cells[2]
            anchor = doc_cell.find("a")
            if anchor is not None:
                name = anchor.get_text(strip=True)
                if not name:
                    href = anchor.get("href", "")
                    name = href.rsplit("/", 1)[-1] if href else ""
            else:
                name = doc_cell.get_text(strip=True)
            typ = cells[3].get_text(strip=True)
            size = cells[4].get_text(strip=True)
            rows.append(
                {
                    "seq": seq,
                    "description": description,
                    "name": name,
                    "type": typ,
                    "size": size,
                }
            )

    if not rows:
        return pl.DataFrame(schema=_INDEX_HTML_SCHEMA)
    return pl.DataFrame(rows, schema=_INDEX_HTML_SCHEMA)


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
    acc_nd = accession_no_dashes(accession)
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
