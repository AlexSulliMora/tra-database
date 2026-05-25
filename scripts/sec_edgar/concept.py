"""SEC Company Concept API wrapper.

Endpoint: ``https://data.sec.gov/api/xbrl/companyconcept/CIK<10>/<taxonomy>/<concept>.json``

Returns the time series of one XBRL fact for one company. Originally
supported XBRL-based verification of TRA-related liability trajectories
during the early scrape pipeline; currently unimported pending integration
into the tra-refresh workflow.

Companies who tagged with a custom (filer-specific) concept do not
appear under the ``us-gaap`` taxonomy; the endpoint returns 404 in
that case. :func:`fetch_concept` surfaces that as an empty LazyFrame
plus a meta-dict flag, rather than as an exception, so callers can
sequence multiple fallback tags.

Cache layout:
``.tra_history_cache/edgar_concept/CIK<10>_<taxonomy>_<concept>.json``
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import polars as pl

from sec_edgar.client import EdgarClient

CACHE_ROOT = Path(".tra_history_cache/edgar_concept")
CONCEPT_BASE = "https://data.sec.gov/api/xbrl/companyconcept"
DEFAULT_MAX_AGE_S = 7 * 24 * 3600  # 7 days


def _pad_cik(cik: str | int) -> str:
    s = str(cik).strip()
    if not s.isdigit():
        raise ValueError(f"CIK must be all digits, got {cik!r}")
    return s.zfill(10)


# Standard TRA-liability tags in order of preference. Custom-tagged
# firms will return 404 for every entry; callers should accept that
# and report it in the packet rather than treat it as a hard error.
TRA_CONCEPT_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("us-gaap", "LiabilitiesUnderTaxReceivableAgreements"),
    ("us-gaap", "LiabilitiesUnderTaxReceivableAgreementCurrent"),
    ("us-gaap", "LiabilitiesUnderTaxReceivableAgreementNoncurrent"),
    ("us-gaap", "DeferredTaxLiabilitiesNoncurrent"),
)


def fetch_concept(
    cik: str | int,
    concept: str,
    taxonomy: str = "us-gaap",
    client: EdgarClient | None = None,
    cache_root: Path = CACHE_ROOT,
    cache_max_age_s: float = DEFAULT_MAX_AGE_S,
    tag_requested: str | None = None,
) -> tuple[pl.LazyFrame, dict]:
    """Fetch one concept's time series for one company.

    Returns ``(lazyframe, meta_dict)``. The LazyFrame has columns
    ``end``, ``val``, ``unit``, ``accn``, ``fy``, ``fp``, ``form``,
    ``filed``, ``frame``, plus ``requires_verification`` (Boolean).
    The meta dict carries ``found`` (bool), ``taxonomy``, ``concept``,
    ``tag_used``, ``tag_requested``, ``requires_verification``,
    ``label`` (human-readable label from the response), and
    ``description``. When ``found`` is False the LazyFrame is empty
    with the same schema.

    ``tag_requested`` is the concept the caller originally asked for
    when invoking this function as part of a fallback walk; when it
    differs from ``concept``, the returned series is flagged as
    requiring verification (the served concept is a fallback, not the
    TRA-specific tag originally requested).
    """
    cik10 = _pad_cik(cik)
    url = f"{CONCEPT_BASE}/CIK{cik10}/{taxonomy}/{concept}.json"
    cache_path = cache_root / f"CIK{cik10}_{taxonomy}_{concept}.json"

    schema = {
        "end": pl.String,
        "val": pl.Float64,
        "unit": pl.String,
        "accn": pl.String,
        "fy": pl.Int64,
        "fp": pl.String,
        "form": pl.String,
        "filed": pl.String,
        "frame": pl.String,
        "requires_verification": pl.Boolean,
    }
    # A row needs verification when the served concept is not the
    # concept the caller originally asked for (a fallback was used).
    requires_verification = (tag_requested is not None) and (
        tag_requested != concept
    )

    own = client is None
    cli = client if client is not None else EdgarClient()
    try:
        try:
            body, _meta = cli.get(
                url, cache_path=cache_path, cache_max_age_s=cache_max_age_s
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return (
                    pl.LazyFrame(schema=schema),
                    {
                        "found": False,
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "tag_used": None,
                        "tag_requested": tag_requested or concept,
                        "requires_verification": False,
                        "label": None,
                        "description": None,
                        "url": url,
                    },
                )
            raise
    finally:
        if own:
            cli.close()

    payload = json.loads(body)
    rows: list[dict] = []
    units_block = payload.get("units", {})
    for unit, vals in units_block.items():
        for v in vals:
            rows.append({
                "end": v.get("end"),
                "val": float(v.get("val")) if v.get("val") is not None else None,
                "unit": unit,
                "accn": v.get("accn"),
                "fy": v.get("fy"),
                "fp": v.get("fp"),
                "form": v.get("form"),
                "filed": v.get("filed"),
                "frame": v.get("frame"),
                "requires_verification": requires_verification,
            })
    if not rows:
        lf = pl.LazyFrame(schema=schema)
    else:
        lf = pl.DataFrame(rows, schema_overrides=schema).lazy()
    return lf, {
        "found": True,
        "taxonomy": taxonomy,
        "concept": concept,
        "tag_used": concept,
        "tag_requested": tag_requested or concept,
        "requires_verification": requires_verification,
        "label": payload.get("label"),
        "description": payload.get("description"),
        "url": url,
    }


def fetch_tra_liability_series(
    cik: str | int,
    client: EdgarClient | None = None,
) -> tuple[pl.LazyFrame, dict]:
    """Walk :data:`TRA_CONCEPT_FALLBACKS` until one returns data.

    Returns the first successful (lazyframe, meta) pair. If every
    fallback returns 404, returns the last (empty) result with the
    accumulated trace under meta['tried'].
    """
    tried: list[dict] = []
    # The "preferred" tag the caller wanted; if a later fallback hits,
    # the returned series carries ``requires_verification = True``.
    preferred_tag = TRA_CONCEPT_FALLBACKS[0][1]
    for taxonomy, concept in TRA_CONCEPT_FALLBACKS:
        lf, meta = fetch_concept(
            cik, concept, taxonomy=taxonomy, client=client,
            tag_requested=preferred_tag,
        )
        tried.append({
            "taxonomy": taxonomy,
            "concept": concept,
            "found": meta["found"],
        })
        if meta["found"]:
            meta["tried"] = tried
            return lf, meta
    # All 404s.
    meta_final = {
        "found": False,
        "taxonomy": None,
        "concept": None,
        "tag_used": None,
        "tag_requested": preferred_tag,
        "requires_verification": False,
        "label": None,
        "description": None,
        "url": None,
        "tried": tried,
    }
    schema = {
        "end": pl.String, "val": pl.Float64, "unit": pl.String,
        "accn": pl.String, "fy": pl.Int64, "fp": pl.String,
        "form": pl.String, "filed": pl.String, "frame": pl.String,
        "requires_verification": pl.Boolean,
    }
    return pl.LazyFrame(schema=schema), meta_final


def _self_test() -> None:
    """Trial run: Surgery Partners TRA liability trajectory.

    Surgery Partners (CIK 1638833) tagged its TRA liability using a
    filer-specific custom concept, not the standard us-gaap
    ``LiabilitiesUnderTaxReceivableAgreements`` tag. The fallback
    chain therefore lands on ``DeferredTaxLiabilitiesNoncurrent``,
    which is the project's documented compromise for firms that
    custom-tag their TRA balance.
    """
    lf, meta = fetch_tra_liability_series("0001638833")
    print(f"resolved: taxonomy={meta['taxonomy']!r} concept={meta['concept']!r}")
    print(f"tag_used={meta['tag_used']!r} tag_requested={meta['tag_requested']!r}")
    print(f"requires_verification={meta['requires_verification']}")
    print(f"label: {meta.get('label')!r}")
    print(f"tried fallbacks: {meta['tried']}")
    df = lf.collect()
    print(f"rows: {df.height}")
    if df.height > 0:
        print(df.sort("end").select(["end", "val", "unit", "form", "filed"]).head(5))
        print(df.sort("end").select(["end", "val", "unit", "form", "filed"]).tail(5))


if __name__ == "__main__":
    _self_test()
