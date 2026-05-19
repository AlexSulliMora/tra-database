"""Split phrase-OR hits for selected forms into body vs exhibit using the
primary_doc filename. No SEC requests; local cache only.
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))

from sec_edgar.client import EdgarClient  # noqa: E402
from sec_edgar.search import search_filings  # noqa: E402

START_DATE = date(2001, 1, 1)
END_DATE = date(2026, 5, 14)
PHRASE_Q = (
    '"tax receivable agreement" OR "tax receivable agreements" '
    'OR "tax receivables agreement" OR "tax receivables agreements"'
)
SAFE_WINDOW_HITS = 700
CACHE_MAX_AGE_S = 365 * 24 * 3600

EXHIBIT_PATTERNS = [
    re.compile(r"^ex[-_\.]?\d", re.IGNORECASE),
    re.compile(r"exhibit\d", re.IGNORECASE),
    re.compile(r"_exhibit_", re.IGNORECASE),
    re.compile(r"dex\d", re.IGNORECASE),
    re.compile(r"ex99", re.IGNORECASE),
]


def is_exhibit(primary_doc: str | None) -> bool:
    if primary_doc is None:
        return False
    # Use only the basename for pattern matching.
    name = primary_doc.rsplit("/", 1)[-1]
    return any(p.search(name) for p in EXHIBIT_PATTERNS)


def search_window(q, s, e, cli, max_results=None):
    lf, meta = search_filings(
        q=q, startdt=s, enddt=e, client=cli,
        cache_max_age_s=CACHE_MAX_AGE_S, max_results=max_results,
    )
    return lf.collect(), meta


def collect_partitioned(q, startdt, enddt, cli, rows):
    if startdt > enddt:
        return
    s, e = startdt.isoformat(), enddt.isoformat()
    _, meta = search_window(q, s, e, cli, max_results=10)
    total = int(meta.get("total", 0))
    relation = meta.get("relation", "eq")
    if total == 0:
        return
    if (total > SAFE_WINDOW_HITS or relation == "gte") and startdt < enddt:
        mid = startdt + (enddt - startdt) // 2
        collect_partitioned(q, startdt, mid, cli, rows)
        collect_partitioned(q, mid + timedelta(days=1), enddt, cli, rows)
        return
    df, meta2 = search_window(q, s, e, cli)
    if df.height > 0:
        rows.extend(df.to_dicts())
    fetched = int(meta2.get("fetched", 0))
    total2 = int(meta2.get("total", 0))
    if fetched < total2 and startdt < enddt:
        del rows[-df.height :]
        mid = startdt + (enddt - startdt) // 2
        collect_partitioned(q, startdt, mid, cli, rows)
        collect_partitioned(q, mid + timedelta(days=1), enddt, cli, rows)


def main():
    cli = EdgarClient()
    try:
        rows: list[dict] = []
        collect_partitioned(PHRASE_Q, START_DATE, END_DATE, cli, rows)
    finally:
        cli.close()
    print(f"phrase-OR raw doc-level rows: {len(rows)}")

    df = pl.DataFrame(rows).with_columns(
        pl.col("primary_doc")
        .map_elements(is_exhibit, return_dtype=pl.Boolean)
        .alias("is_exhibit"),
    )

    seed = int(date.today().strftime("%Y%m%d"))
    for form in ("10-K", "10-Q", "8-K"):
        sub = df.filter(pl.col("form") == form)
        # Distinct (adsh, is_exhibit) pairs so we can count accessions with
        # any body match, any exhibit match, both, or only one.
        per_accession = (
            sub.group_by("adsh")
            .agg(
                pl.col("is_exhibit").any().alias("has_exhibit"),
                (~pl.col("is_exhibit")).any().alias("has_body"),
                pl.col("ciks").first().alias("ciks"),
            )
        )
        n_total = per_accession.height
        n_body = per_accession.filter(pl.col("has_body")).height
        n_exhibit = per_accession.filter(pl.col("has_exhibit")).height
        n_both = per_accession.filter(
            pl.col("has_body") & pl.col("has_exhibit")
        ).height
        n_body_only = n_body - n_both
        n_exhibit_only = n_exhibit - n_both

        def n_ciks(frame):
            return (
                frame.select("ciks")
                .explode("ciks")
                .filter(pl.col("ciks").is_not_null())
                ["ciks"]
                .n_unique()
            )

        c_total = n_ciks(per_accession)
        c_body = n_ciks(per_accession.filter(pl.col("has_body")))
        c_exhibit = n_ciks(per_accession.filter(pl.col("has_exhibit")))
        c_both = n_ciks(
            per_accession.filter(pl.col("has_body") & pl.col("has_exhibit"))
        )

        print(f"\n=== {form} ===")
        print(f"  total distinct accessions: {n_total} ({c_total} CIKs)")
        print(f"  body-matching accessions:  {n_body} ({c_body} CIKs)")
        print(f"  exhibit-matching:          {n_exhibit} ({c_exhibit} CIKs)")
        print(f"  both body and exhibit:     {n_both} ({c_both} CIKs)")
        print(f"  body-only:                 {n_body_only}")
        print(f"  exhibit-only:              {n_exhibit_only}")

        if form == "10-K":
            body_names = (
                sub.filter(~pl.col("is_exhibit"))
                .select("primary_doc")
                .unique()
                .sample(n=10, seed=seed)
                ["primary_doc"]
                .to_list()
            )
            exh_names = (
                sub.filter(pl.col("is_exhibit"))
                .select("primary_doc")
                .unique()
                .sample(n=10, seed=seed)
                ["primary_doc"]
                .to_list()
            )
            print("  10 sampled BODY primary_doc names:")
            for n in body_names:
                print(f"    {n}")
            print("  10 sampled EXHIBIT primary_doc names:")
            for n in exh_names:
                print(f"    {n}")


if __name__ == "__main__":
    main()
