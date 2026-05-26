"""Submissions JSON resolver.

Fetches ``https://data.sec.gov/submissions/CIK<10-digit>.json`` for a
given CIK and returns:

- a polars LazyFrame of the ``filings.recent.*`` parallel arrays
  (one row per filing), and
- a static-fields dict (entity name, CIK, SIC, tickers, exchanges,
  formerNames, addresses).

Continuation files referenced under ``filings.files[]`` are fetched and
their rows concatenated onto the recent frame.

Cache layout: ``.tra_history_cache/edgar_submissions/CIK<10-digit>.json``
(matches the directory the existing TRA pipeline already populates).
Continuation files land beside the base file under their published
names: ``CIK<10-digit>-submissions-NNN.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from sec_edgar.client import EdgarClient

CACHE_ROOT = Path(".tra_history_cache/edgar_submissions")
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
DEFAULT_MAX_AGE_S = 7 * 24 * 3600  # 7 days


def pad_cik(cik: str | int) -> str:
    s = str(cik).strip()
    if not s.isdigit():
        raise ValueError(f"CIK must be all digits, got {cik!r}")
    return s.zfill(10)


def _recent_to_lazyframe(recent: dict) -> pl.LazyFrame:
    """Parallel-array dict to LazyFrame.

    The Submissions API guarantees the recent arrays are equal length;
    we validate that here and fail loud if not.
    """
    if not recent:
        return pl.LazyFrame(schema={"accessionNumber": pl.String})
    lengths = {k: len(v) for k, v in recent.items() if isinstance(v, list)}
    if len(set(lengths.values())) > 1:
        raise ValueError(
            f"Submissions recent arrays disagree in length: {lengths}"
        )
    # Cast all to string-ish first; downstream callers narrow as needed.
    cols = {k: v for k, v in recent.items() if isinstance(v, list)}
    return pl.DataFrame(cols).lazy()


def fetch_submissions(
    cik: str | int,
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
    include_continuations: bool = True,
) -> tuple[pl.LazyFrame, dict]:
    """Fetch the Submissions JSON for ``cik``.

    Returns ``(filings_lazyframe, static_fields_dict)``. The lazyframe
    contains the ``filings.recent`` parallel-array rows plus, if
    ``include_continuations=True``, the rows referenced under
    ``filings.files[]``.
    """
    cik10 = pad_cik(cik)
    own_client = client is None
    cli = client if client is not None else EdgarClient()
    try:
        base_url = f"{SUBMISSIONS_BASE}/CIK{cik10}.json"
        base_cache = cache_root / f"CIK{cik10}.json"
        body, _meta = cli.get(
            base_url, cache_path=base_cache, cache_max_age_s=cache_max_age_s
        )
        payload = json.loads(body)

        recent = payload.get("filings", {}).get("recent", {})
        lf = _recent_to_lazyframe(recent)

        if include_continuations:
            extra_frames: list[pl.LazyFrame] = []
            for ent in payload.get("filings", {}).get("files", []):
                name = ent.get("name")
                if not name:
                    raise ValueError(f"continuation entry missing 'name': {ent}")
                cont_url = f"{SUBMISSIONS_BASE}/{name}"
                cont_cache = cache_root / name
                cbody, _ = cli.get(
                    cont_url,
                    cache_path=cont_cache,
                    cache_max_age_s=cache_max_age_s,
                )
                cont_payload = json.loads(cbody)
                # Continuation files are bare parallel-array dicts (no
                # surrounding "filings.recent" wrapper).
                extra_frames.append(_recent_to_lazyframe(cont_payload))
            if extra_frames:
                lf = pl.concat([lf, *extra_frames], how="diagonal_relaxed")

        static_fields = {
            k: payload.get(k)
            for k in (
                "cik",
                "name",
                "sic",
                "sicDescription",
                "tickers",
                "exchanges",
                "addresses",
                "formerNames",
                "category",
                "fiscalYearEnd",
            )
        }
        return lf, static_fields
    finally:
        if own_client:
            cli.close()


def _self_test() -> None:
    """Trial run: fetch Apple (CIK 0000320193); print head."""
    lf, static = fetch_submissions("0000320193")
    df = lf.collect()
    print(f"static: name={static['name']!r} sic={static['sic']} cik={static['cik']}")
    print(f"filings rows: {df.height}")
    cols_we_care_about = [
        c
        for c in ("accessionNumber", "filingDate", "form", "primaryDocument")
        if c in df.columns
    ]
    print(df.select(cols_we_care_about).head(5))
    # Sanity: at least one 10-K should be present in Apple's filing history.
    ten_ks = df.filter(pl.col("form") == "10-K") if "form" in df.columns else None
    if ten_ks is None or ten_ks.height == 0:
        raise RuntimeError("no 10-K rows found for Apple; submissions parse failed")
    print(f"10-K count: {ten_ks.height}")


if __name__ == "__main__":
    _self_test()
