"""Form-distribution diagnostics across the cached master-list search
results. No SEC requests; everything is served from the on-disk cache.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))

from sec_edgar.client import EdgarClient  # noqa: E402  (sys.path above)
from sec_edgar.search import search_filings  # noqa: E402

PROJECT_ROOT = Path("/home/sulli/research/tra")
OUT_DIR = PROJECT_ROOT / "coauthor/2026-05-12-edgar-scrape/findings"

START_DATE = date(2001, 1, 1)
END_DATE = date(2026, 5, 14)

PHRASE_Q = (
    '"tax receivable agreement" OR "tax receivable agreements" '
    'OR "tax receivables agreement" OR "tax receivables agreements"'
)
TOKEN_Q = "TRA"

ALLOW_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "6-K",
    "DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A",
    "8-K", "8-K/A",
    "S-1", "S-1/A", "S-4", "S-4/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "DRS", "DRS/A",
}

SAFE_WINDOW_HITS = 700
CACHE_MAX_AGE_S = 365 * 24 * 3600  # serve from cache


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


def to_rows_df(raw_rows):
    if not raw_rows:
        return pl.DataFrame(schema={"adsh": pl.String, "form": pl.String, "ciks": pl.List(pl.String)})
    df = pl.DataFrame(raw_rows)
    return df.with_columns(
        pl.col("ciks").cast(pl.List(pl.String)).alias("ciks"),
    )


def form_distribution(df: pl.DataFrame, label: str) -> pl.DataFrame:
    """Per-form: distinct accession count, distinct CIK count, in_allow_list."""
    # Distinct accession count by form (one row per (adsh, form) — but adsh
    # only ever has one form; deduplicate (adsh, form) first).
    accessions = (
        df.select(["adsh", "form"])
        .unique()
        .group_by("form")
        .agg(pl.len().alias("n_accessions"))
    )
    # Distinct CIK count by form (explode ciks, then group).
    ciks = (
        df.select(["form", "ciks"])
        .explode("ciks")
        .filter(pl.col("ciks").is_not_null())
        .group_by("form")
        .agg(pl.col("ciks").n_unique().alias("n_ciks"))
    )
    out = accessions.join(ciks, on="form", how="left").with_columns(
        pl.when(pl.col("form").is_in(list(ALLOW_FORMS)))
        .then(pl.lit("Y"))
        .otherwise(pl.lit("N"))
        .alias("in_allow_list"),
    ).sort("n_accessions", descending=True)
    return out


def main():
    cli = EdgarClient()
    try:
        phrase_rows: list[dict] = []
        collect_partitioned(PHRASE_Q, START_DATE, END_DATE, cli, phrase_rows)
        token_rows: list[dict] = []
        collect_partitioned(TOKEN_Q, START_DATE, END_DATE, cli, token_rows)
    finally:
        cli.close()

    phrase_df = to_rows_df(phrase_rows)
    token_df = to_rows_df(token_rows)

    # Dedup (adsh, form) before counting — full-text search can return the
    # same accession multiple times (different document matches in same
    # filing). We want per-filing counts.
    phrase_unique = phrase_df.unique(subset=["adsh"], keep="first")
    token_unique = token_df.unique(subset=["adsh"], keep="first")

    # Pre-filter distributions.
    pre_phrase = form_distribution(phrase_unique, "phrase")
    pre_token = form_distribution(token_unique, "token")

    # Post-filter distributions: same data, but only allow-list rows kept.
    phrase_post = phrase_unique.filter(pl.col("form").is_in(list(ALLOW_FORMS)))
    token_post = token_unique.filter(pl.col("form").is_in(list(ALLOW_FORMS)))
    post_phrase = form_distribution(phrase_post, "phrase")
    post_token = form_distribution(token_post, "token")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pre_phrase.write_csv(OUT_DIR / "form_dist_phrase_prefilter.csv")
    pre_token.write_csv(OUT_DIR / "form_dist_token_prefilter.csv")
    post_phrase.write_csv(OUT_DIR / "form_dist_phrase_postfilter.csv")
    post_token.write_csv(OUT_DIR / "form_dist_token_postfilter.csv")

    # Aggregate-level summary.
    def agg_stats(df):
        adsh_unique = df.unique(subset=["adsh"]).height
        cik_unique = (
            df.select("ciks").explode("ciks").filter(pl.col("ciks").is_not_null())
            ["ciks"].n_unique()
        )
        return adsh_unique, cik_unique, df.height

    phr_adsh, phr_cik, phr_rows = agg_stats(phrase_unique)
    tok_adsh, tok_cik, tok_rows = agg_stats(token_unique)

    combined = pl.concat(
        [
            phrase_unique.select(["adsh", "form", "ciks"]),
            token_unique.select(["adsh", "form", "ciks"]),
        ],
        how="vertical",
    ).unique(subset=["adsh"], keep="first")
    all_adsh, all_cik, _ = agg_stats(combined)

    # Print full tables to stdout.
    def print_table(title, df):
        print(f"\n=== {title} ===")
        print(f"forms: {df.height}; rows below.")
        with pl.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=200):
            print(df)

    print_table("PRE-FILTER phrase-OR", pre_phrase)
    print_table("PRE-FILTER TRA-token", pre_token)
    print_table("POST-FILTER phrase-OR", post_phrase)
    print_table("POST-FILTER TRA-token", post_token)

    print("\n=== SUMMARY ===")
    print(f"phrase-OR  raw_hits={phr_rows:>6}  distinct_adsh={phr_adsh:>6}  distinct_cik={phr_cik:>6}")
    print(f"TRA-token  raw_hits={tok_rows:>6}  distinct_adsh={tok_adsh:>6}  distinct_cik={tok_cik:>6}")
    print(f"COMBINED   raw_hits={phr_rows+tok_rows:>6}  distinct_adsh={all_adsh:>6}  distinct_cik={all_cik:>6}")
    print(f"CSV outputs written to {OUT_DIR}/form_dist_*.csv")


if __name__ == "__main__":
    main()
