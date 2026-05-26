"""Month/biweekly date-window helpers and the halving query wrapper.

Implements R3 of the Phase 1 brainstorm at
docs/brainstorms/2026-05-25-phase-1-requirements.md: month-window
iteration, leap-year-aware month bounds, biweekly halving, and a
``query_month_with_halving`` helper that calls EDGAR full-text search
once per month, splitting into two biweekly halves on overflow.

The halving floor is biweekly (Key Technical Decision in the plan): if
both biweekly halves still overflow, ``WindowOverflowError`` is raised
so the operator can investigate. Going finer is reserved for future
work; empirically the TRA corpus does not need it.

``search_filings`` is wrapped in a small 5xx-retry (3 attempts, 1.5s
backoff) matching the ``search_with_retry`` pattern in
scripts/find_candidates.py.
"""

from __future__ import annotations

import calendar
import sys
import time
from collections.abc import Iterator

import httpx
import polars as pl

from sec_edgar.client import EdgarClient
from sec_edgar.search import DEFAULT_MAX_AGE_S, search_filings


# Empirical-safe-window-hits early-warning threshold from
# scripts/tra_master_cik_list.py (SAFE_WINDOW_HITS = 700). EDGAR full-
# text search becomes unreliable past offset ~800 well before the 10k
# theoretical cap, so we halve aggressively when fetched count
# approaches the cap. Per the plan: trigger halving on
# meta["relation"] == "gte" OR meta["fetched"] >= 9500.
HALVING_FETCHED_THRESHOLD: int = 9500


class WindowOverflowError(Exception):
    """Raised when both biweekly halves of a month also overflow.

    Carries the failing window (year, month, half-start, half-end,
    query) in its message so the operator can investigate.
    """


def month_iter(start: str, end: str) -> Iterator[tuple[int, int]]:
    """Yield ``(year, month)`` pairs inclusive over [start, end].

    ``start`` and ``end`` are ``YYYY-MM`` strings.
    """
    start_year, start_month = (int(x) for x in start.split("-"))
    end_year, end_month = (int(x) for x in end.split("-"))
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m == 13:
            m = 1
            y += 1


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return ``(start_date, end_date)`` for the whole month in YYYY-MM-DD form.

    Leap-year-aware via ``calendar.monthrange``.
    """
    last = calendar.monthrange(year, month)[1]
    return (
        f"{year:04d}-{month:02d}-01",
        f"{year:04d}-{month:02d}-{last:02d}",
    )


def biweekly_bounds(year: int, month: int) -> list[tuple[str, str]]:
    """Return the two halves of a month as ``[(YYYY-MM-01, YYYY-MM-15), (YYYY-MM-16, YYYY-MM-EOM)]``.

    Leap-year-aware via ``calendar.monthrange``.
    """
    last = calendar.monthrange(year, month)[1]
    return [
        (
            f"{year:04d}-{month:02d}-01",
            f"{year:04d}-{month:02d}-15",
        ),
        (
            f"{year:04d}-{month:02d}-16",
            f"{year:04d}-{month:02d}-{last:02d}",
        ),
    ]


def _search_with_retry(
    *,
    q: str,
    startdt: str,
    enddt: str,
    client: EdgarClient,
    cache_max_age_s: float,
    max_attempts: int = 3,
    backoff_s: float = 1.5,
) -> tuple[pl.LazyFrame, dict]:
    """Retry ``search_filings`` on HTTP 5xx; pass through everything else.

    Mirrors ``search_with_retry`` in scripts/find_candidates.py. Three
    attempts, 1.5s backoff between them; non-5xx HTTP errors raise on
    the first failure.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return search_filings(
                q=q,
                startdt=startdt,
                enddt=enddt,
                client=client,
                cache_max_age_s=cache_max_age_s,
            )
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code >= 500 and attempt < max_attempts - 1:
                time.sleep(backoff_s)
                continue
            raise
    # Unreachable: the loop either returns or re-raises. Defensive.
    raise RuntimeError(
        f"_search_with_retry exhausted {max_attempts} attempts"
    ) from last_exc


def _is_overflow(meta: dict) -> bool:
    """Whether a search-meta dict indicates the window should be halved."""
    if meta.get("relation") == "gte":
        return True
    if int(meta.get("fetched", 0)) >= HALVING_FETCHED_THRESHOLD:
        return True
    return False


def _merge_relation(left: str, right: str) -> str:
    """Worst-case relation across two windows: ``gte`` dominates ``eq``."""
    if left == "gte" or right == "gte":
        return "gte"
    return "eq"


def query_month_with_halving(
    query: str,
    year: int,
    month: int,
    client: EdgarClient,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
) -> tuple[pl.DataFrame, dict]:
    """Query EDGAR full-text search for one month; halve to biweekly on overflow.

    Calls ``search_filings`` for the full month. If the result overflows
    (``meta["relation"] == "gte"`` OR ``meta["fetched"] >= 9500``),
    splits the month into the two biweekly halves and re-queries each.
    If either biweekly half also overflows, raises
    ``WindowOverflowError`` with the failing window in the message.

    Returns ``(concatenated DataFrame, merged meta dict)``. The merged
    meta sums ``fetched`` and takes the worst-case ``relation``.
    """
    startdt, enddt = month_bounds(year, month)
    lf, meta = _search_with_retry(
        q=query,
        startdt=startdt,
        enddt=enddt,
        client=client,
        cache_max_age_s=cache_max_age_s,
    )
    if not _is_overflow(meta):
        return lf.collect(), dict(meta)

    # Overflow: halve into the two biweekly windows and re-query each.
    halves = biweekly_bounds(year, month)
    half_frames: list[pl.DataFrame] = []
    merged_fetched = 0
    merged_relation = "eq"
    merged_hit_cap = False
    merged_total = 0
    for half_start, half_end in halves:
        half_lf, half_meta = _search_with_retry(
            q=query,
            startdt=half_start,
            enddt=half_end,
            client=client,
            cache_max_age_s=cache_max_age_s,
        )
        if _is_overflow(half_meta):
            raise WindowOverflowError(
                f"biweekly window {half_start}..{half_end} also overflowed "
                f"for query {query!r} in {year:04d}-{month:02d} "
                f"(relation={half_meta.get('relation')!r}, "
                f"fetched={half_meta.get('fetched')})"
            )
        half_frames.append(half_lf.collect())
        merged_fetched += int(half_meta.get("fetched", 0))
        merged_relation = _merge_relation(
            merged_relation, half_meta.get("relation", "eq")
        )
        merged_hit_cap = merged_hit_cap or bool(half_meta.get("hit_cap", False))
        merged_total += int(half_meta.get("total", 0))

    concat = pl.concat(half_frames, how="vertical_relaxed")
    merged_meta = {
        "total": merged_total,
        "fetched": merged_fetched,
        "hit_cap": merged_hit_cap,
        "relation": merged_relation,
        "halved": True,
    }
    return concat, merged_meta


def _self_test() -> None:
    """Operator-invoked sanity check.

    Pure-function checks first, then ONE live-network call to
    ``query_month_with_halving`` against a known small window.
    """
    # month_iter: simple range.
    assert list(month_iter("2024-01", "2024-03")) == [
        (2024, 1),
        (2024, 2),
        (2024, 3),
    ]
    # month_iter: year rollover.
    assert list(month_iter("2024-12", "2025-02")) == [
        (2024, 12),
        (2025, 1),
        (2025, 2),
    ]
    # month_bounds: leap and non-leap Feb.
    assert month_bounds(2024, 2) == ("2024-02-01", "2024-02-29")
    assert month_bounds(2023, 2) == ("2023-02-01", "2023-02-28")
    assert month_bounds(2024, 1) == ("2024-01-01", "2024-01-31")
    # biweekly_bounds: leap Feb covers 16-29.
    assert biweekly_bounds(2024, 2) == [
        ("2024-02-01", "2024-02-15"),
        ("2024-02-16", "2024-02-29"),
    ]
    # biweekly_bounds: non-leap Feb ends on 28.
    bw_2023_feb = biweekly_bounds(2023, 2)
    assert bw_2023_feb[1][1] == "2023-02-28"

    # Overflow predicate.
    assert _is_overflow({"relation": "gte", "fetched": 10}) is True
    assert _is_overflow({"relation": "eq", "fetched": 9500}) is True
    assert _is_overflow({"relation": "eq", "fetched": 9499}) is False

    # Relation merger.
    assert _merge_relation("eq", "eq") == "eq"
    assert _merge_relation("eq", "gte") == "gte"
    assert _merge_relation("gte", "eq") == "gte"

    # ONE live-network call: a known small window for the canonical
    # phrase variant. June 2024 is well under the 10k cap for the
    # phrase "tax receivable agreement" alone, so this should not
    # trigger halving and should not raise.
    print("running one live EDGAR call for June 2024 ...", flush=True)
    with EdgarClient() as client:
        df, meta = query_month_with_halving(
            '"tax receivable agreement"', 2024, 6, client
        )
    assert df.height >= 0
    print(
        f"  live call returned: df.height={df.height} "
        f"relation={meta.get('relation')!r} fetched={meta.get('fetched')} "
        f"halved={meta.get('halved', False)}",
        flush=True,
    )

    print("OK", flush=True)


if __name__ == "__main__":
    _self_test()
    sys.exit(0)
