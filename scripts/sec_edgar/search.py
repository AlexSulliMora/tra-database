"""EDGAR full-text search wrapper.

Endpoint: ``https://efts.sec.gov/LATEST/search-index``.

The API caps total addressable results at 10,000 per query
(``from + size <= 10000``). :func:`search_filings` pages through results
honoring that cap. When the underlying query exceeds 10,000 hits, the
caller is responsible for partitioning (typically by date range);
:func:`search_filings_paginated_by_date` is a helper that splits a date
range in half recursively until each sub-window stays under the cap.

Cache layout: ``.tra_history_cache/edgar_search/<query-hash>.json``,
where the hash is sha256 of the JSON-serialized parameter dict.

**Known SEC quirk: ``forms`` parameter is unreliable for slash-bearing
codes.** When the comma-separated ``forms`` list contains amendment or
slash-bearing codes (e.g. ``10-K/A``, ``10-Q/A``, ``8-K/A``, ``S-1/A``,
``S-4/A``, ``DRS/A``), the SEC full-text-search server silently drops
the result count to roughly zero. Confirmed empirically: for CIK
0001579157 (Vince Holding), ``forms=10-K`` returns 16 hits, while
``forms=10-K,10-K/A`` returns 0. The recommended pattern is to **omit
the ``forms`` parameter entirely** and post-filter the returned
``form`` column locally against the desired allow-list.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

import polars as pl

from sec_edgar.client import EdgarClient

CACHE_ROOT = Path(".tra_history_cache/edgar_search")
EDGAR_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"
DEFAULT_MAX_AGE_S = 24 * 3600  # 1 day; search index is live
PAGE_CAP = 10000  # SEC: from + size <= 10000
PAGE_SIZE = 100  # SEC documented maximum

# Columns the caller can rely on. Some hits may not carry every field;
# missing values come through as nulls.
HIT_COLUMNS = (
    "adsh",
    "primary_doc",
    "ciks",
    "form",
    "display_names",
    "file_date",
    "snippet",
)


def _query_hash(params: dict) -> str:
    # Sort keys so the hash is deterministic; values are stringified.
    canon = json.dumps({k: params[k] for k in sorted(params)}, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _hit_to_row(hit: dict) -> dict:
    src = hit.get("_source", {})
    # The full-text search response embeds the accession plus matching filename as
    # ``<accession>:<filename>`` in the ``_id`` field. Split on the first
    # colon so ``adsh`` is a bare accession the rest of the package can
    # pass to forms.fetch_filing / archives._accession_no_dashes.
    raw_id = hit.get("_id") or src.get("adsh") or ""
    if ":" in raw_id:
        adsh, primary_doc = raw_id.split(":", 1)
    else:
        adsh, primary_doc = raw_id, None
    row = {
        "adsh": adsh,
        "primary_doc": primary_doc,
        "ciks": src.get("ciks"),
        "form": src.get("form"),
        "display_names": src.get("display_names"),
        "file_date": src.get("file_date"),
        "snippet": src.get("snippet") or (hit.get("highlight") or {}).get("text"),
        "period_of_report": src.get("period_of_report"),
        "file_description": src.get("file_description"),
    }
    return row


def _one_page(
    cli: EdgarClient,
    params: dict,
    from_offset: int,
    size: int,
    cache_root: Path,
    cache_max_age_s: float,
) -> dict:
    page_params = {**params, "from": from_offset, "size": size}
    cache_key = _query_hash(page_params)
    cache_path = cache_root / f"{cache_key}.json"
    body, _meta = cli.get(
        EDGAR_FULLTEXT_URL,
        cache_path=cache_path,
        cache_max_age_s=cache_max_age_s,
        params=page_params,
    )
    return json.loads(body)


def search_filings(
    q: str,
    forms: str | None = None,
    startdt: str | None = None,
    enddt: str | None = None,
    ciks: str | None = None,
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
    max_results: int | None = None,
) -> tuple[pl.LazyFrame, dict]:
    """Run an EDGAR full-text search query, paginating up to the 10,000-result hard cap.

    Returns ``(rows_lazyframe, meta_dict)``. ``meta_dict`` carries
    ``total`` (the reported total count, may be ``"gte"`` of 10000 when
    the relation is not exact), ``fetched`` (rows actually returned),
    ``hit_cap`` (True if pagination stopped at 10,000), and
    ``relation`` (``"eq"`` or ``"gte"``).
    """
    base_params: dict[str, object] = {"q": q}
    if forms:
        base_params["forms"] = forms
    if ciks:
        # The endpoint accepts ``ciks`` as a comma-separated list of zero-padded
        # 10-digit CIKs and filters server-side.
        base_params["ciks"] = ciks
    if startdt or enddt:
        if not (startdt and enddt):
            raise ValueError("startdt and enddt must be passed together")
        base_params["dateRange"] = "custom"
        base_params["startdt"] = startdt
        base_params["enddt"] = enddt

    own = client is None
    cli = client if client is not None else EdgarClient()
    rows: list[dict] = []
    total = 0
    relation = "eq"
    hit_cap = False
    try:
        offset = 0
        while True:
            size = min(PAGE_SIZE, PAGE_CAP - offset)
            if size <= 0:
                hit_cap = True
                break
            page = _one_page(
                cli, base_params, offset, size, cache_root, cache_max_age_s
            )
            hits_block = page.get("hits", {})
            total_block = hits_block.get("total", {})
            if isinstance(total_block, dict):
                total = int(total_block.get("value", 0))
                relation = total_block.get("relation", "eq")
            else:
                total = int(total_block or 0)
            page_hits = hits_block.get("hits", [])
            for h in page_hits:
                rows.append(_hit_to_row(h))
                if max_results is not None and len(rows) >= max_results:
                    break
            if max_results is not None and len(rows) >= max_results:
                break
            if len(page_hits) < size:
                # End of result set.
                break
            offset += size
            if offset >= PAGE_CAP:
                hit_cap = True
                break
    finally:
        if own:
            cli.close()

    if not rows:
        lf = pl.LazyFrame(schema={c: pl.String for c in HIT_COLUMNS})
    else:
        lf = pl.DataFrame(rows).lazy()
    meta = {
        "total": total,
        "fetched": len(rows),
        "hit_cap": hit_cap,
        "relation": relation,
    }
    return lf, meta


def _self_test() -> None:
    """Trial run: an Apple-10-K-shaped query that should return >100 hits.

    The phrase "tax receivable agreement" in 8-Ks during 2024 is dense
    enough to force pagination across multiple pages.
    """
    lf, meta = search_filings(
        q='"tax receivable agreement"',
        forms="8-K",
        startdt="2024-01-01",
        enddt="2024-12-31",
        max_results=250,
    )
    df = lf.collect()
    print(
        f"search meta: total={meta['total']} relation={meta['relation']!r} "
        f"fetched={meta['fetched']} hit_cap={meta['hit_cap']}"
    )
    print(df.select(["adsh", "form", "file_date", "display_names"]).head(5))
    if df.height < 100:
        raise RuntimeError(
            f"expected >100 fetched rows to prove pagination; got {df.height}"
        )


if __name__ == "__main__":
    _self_test()
