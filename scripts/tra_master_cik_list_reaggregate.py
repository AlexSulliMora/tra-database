"""Re-aggregate the TRA master CIK list with a form allow-list applied
to BOTH the phrase-OR query and the TRA-token query.

Source data: cached EDGAR full-text-search responses written by the
previous master-list run. No new SEC requests are issued (the wrapper
returns cached bytes when cache_max_age_s is large enough).
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))

from sec_edgar.client import EdgarClient  # noqa: E402  (sys.path above)
from sec_edgar.search import search_filings  # noqa: E402

PROJECT_ROOT = Path("/home/sulli/research/tra")
OUT_PATH = (
    PROJECT_ROOT
    / "coauthor/2026-05-12-edgar-scrape/findings/tra_master_cik_list.csv"
)
DEFERRED_CSV = PROJECT_ROOT / "tra_deferred_review.csv"

START_DATE = date(2001, 1, 1)
END_DATE = date(2026, 5, 14)

PHRASE_Q = (
    '"tax receivable agreement" OR "tax receivable agreements" '
    'OR "tax receivables agreement" OR "tax receivables agreements"'
)
TOKEN_Q = "TRA"

# Allow-list matching the download skill's set.
ALLOW_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "6-K",
    "DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A",
    "8-K", "8-K/A",
    "S-1", "S-1/A", "S-4", "S-4/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "DRS", "DRS/A",
}

SAFE_WINDOW_HITS = 700
# Long cache horizon: we don't want any network calls for this re-aggregation.
CACHE_MAX_AGE_S = 365 * 24 * 3600

STATS = {
    "requests": 0,
    "cache_misses": 0,
}


def search_window(q: str, startdt: str, enddt: str, client: EdgarClient, max_results=None):
    lf, meta = search_filings(
        q=q,
        startdt=startdt,
        enddt=enddt,
        client=client,
        cache_max_age_s=CACHE_MAX_AGE_S,
        max_results=max_results,
    )
    STATS["requests"] += 1
    return lf.collect(), meta


def collect_partitioned(
    q: str,
    startdt: date,
    enddt: date,
    client: EdgarClient,
    rows_accum: list[dict],
    depth: int = 0,
) -> None:
    if startdt > enddt:
        return
    s = startdt.isoformat()
    e = enddt.isoformat()
    df, meta = search_window(q, s, e, client, max_results=10)
    total = int(meta.get("total", 0))
    relation = meta.get("relation", "eq")
    if total == 0:
        return
    if (total > SAFE_WINDOW_HITS or relation == "gte") and startdt < enddt:
        mid = startdt + (enddt - startdt) // 2
        collect_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
        collect_partitioned(
            q, mid + timedelta(days=1), enddt, client, rows_accum, depth + 1
        )
        return
    df2, meta2 = search_window(q, s, e, client)
    if df2.height > 0:
        rows_accum.extend(df2.to_dicts())
    fetched2 = int(meta2.get("fetched", 0))
    total2 = int(meta2.get("total", 0))
    if fetched2 < total2 and startdt < enddt:
        del rows_accum[-df2.height :]
        mid = startdt + (enddt - startdt) // 2
        collect_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
        collect_partitioned(
            q, mid + timedelta(days=1), enddt, client, rows_accum, depth + 1
        )


def flatten_to_cik_rows(rows: list[dict], query_label: str) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            schema={
                "cik": pl.String,
                "adsh": pl.String,
                "form": pl.String,
                "file_date": pl.String,
                "display_names": pl.String,
                "query": pl.String,
            }
        )
    df = pl.DataFrame(rows)
    df = df.with_columns(
        pl.col("display_names").cast(pl.List(pl.String)).alias("display_names"),
        pl.col("ciks").cast(pl.List(pl.String)).alias("ciks"),
    )
    df = df.with_columns(
        pl.col("display_names").list.join("; ").alias("display_names_joined")
    )
    df = df.explode("ciks").rename({"ciks": "cik"})
    df = df.with_columns(
        pl.col("cik").str.zfill(10).alias("cik"),
        pl.lit(query_label).alias("query"),
    )
    df = df.select(
        ["cik", "adsh", "form", "file_date", "display_names_joined", "query"]
    ).rename({"display_names_joined": "display_names"})
    return df


def main() -> None:
    t0 = time.time()
    print(f"start: {datetime.now().isoformat()}", flush=True)

    deferred = pl.read_csv(DEFERRED_CSV, infer_schema_length=0)
    deferred_ciks_padded = {
        c.zfill(10) for c in deferred["cik"].cast(pl.Int64).cast(pl.String).to_list()
    }

    cli = EdgarClient()
    try:
        phrase_rows: list[dict] = []
        collect_partitioned(PHRASE_Q, START_DATE, END_DATE, cli, phrase_rows)
        print(f"phrase-OR raw rows: {len(phrase_rows)}", flush=True)
        token_rows: list[dict] = []
        collect_partitioned(TOKEN_Q, START_DATE, END_DATE, cli, token_rows)
        print(f"TRA-token raw rows: {len(token_rows)}", flush=True)
    finally:
        cli.close()
    print(f"elapsed after fetch: {time.time()-t0:.1f}s", flush=True)

    phrase_df = flatten_to_cik_rows(phrase_rows, "phrase").filter(
        pl.col("cik").is_not_null() & (pl.col("cik").str.len_chars() == 10)
    )
    token_df = flatten_to_cik_rows(token_rows, "token").filter(
        pl.col("cik").is_not_null() & (pl.col("cik").str.len_chars() == 10)
    )

    # ---- Diagnostics: pre-filter CIK universes (matching prior run) ----
    prior_phrase_ciks = set(phrase_df["cik"].unique().to_list())
    prior_token_typical_old = (
        token_df.with_columns(
            pl.col("form").is_in(
                [
                    "10-K", "10-Q", "8-K", "S-1", "S-4",
                    "DEF 14A", "DEFA14A", "DEFM14A",
                ]
            ).alias("is_typical_old")
        )
        .filter(
            pl.col("is_typical_old")
            | pl.col("form").str.starts_with("424B")
        )
        .group_by("cik")
        .agg(pl.col("adsh").n_unique().alias("n"))
        .filter(pl.col("n") >= 3)["cik"]
        .to_list()
    )
    prior_master = prior_phrase_ciks | set(prior_token_typical_old)
    print(
        f"PRIOR (no form filter on phrase; old typical-form set on token): "
        f"phrase_ciks={len(prior_phrase_ciks)} token_eligible={len(prior_token_typical_old)} "
        f"union={len(prior_master)}",
        flush=True,
    )

    # ---- Apply allow-list to BOTH queries ----
    phrase_filt = phrase_df.filter(pl.col("form").is_in(list(ALLOW_FORMS)))
    token_filt = token_df.filter(pl.col("form").is_in(list(ALLOW_FORMS)))

    phrase_ciks = set(phrase_filt["cik"].unique().to_list())
    token_cik_counts = (
        token_filt.group_by("cik")
        .agg(pl.col("adsh").n_unique().alias("n_accessions_allow"))
    )
    token_eligible_ciks = set(
        token_cik_counts.filter(pl.col("n_accessions_allow") >= 3)["cik"].to_list()
    )
    master_ciks = phrase_ciks | token_eligible_ciks

    # Diagnostics: what got dropped from phrase?
    dropped_phrase = prior_phrase_ciks - phrase_ciks
    # Form distribution among dropped phrase-CIKs (use full phrase_df).
    if dropped_phrase:
        dropped_form_counts = (
            phrase_df.filter(pl.col("cik").is_in(list(dropped_phrase)))
            .group_by("form")
            .agg(pl.col("cik").n_unique().alias("n_ciks"))
            .sort("n_ciks", descending=True)
            .head(15)
        )
        print("Top forms among dropped phrase-only CIKs:", flush=True)
        for r in dropped_form_counts.iter_rows(named=True):
            print(f"  {r['form']}: {r['n_ciks']}", flush=True)

    # Phrase-only vs token-only (after filter).
    phrase_only_new = phrase_ciks - token_eligible_ciks
    token_only_new = token_eligible_ciks - phrase_ciks
    phrase_only_old = prior_phrase_ciks - set(prior_token_typical_old)
    token_only_old = set(prior_token_typical_old) - prior_phrase_ciks
    print(
        f"phrase-only CIKs: before={len(phrase_only_old)} after={len(phrase_only_new)}",
        flush=True,
    )
    print(
        f"phrase distinct CIKs total: before={len(prior_phrase_ciks)} "
        f"after={len(phrase_ciks)}",
        flush=True,
    )
    print(
        f"token-only CIKs: before={len(token_only_old)} after={len(token_only_new)}",
        flush=True,
    )
    print(
        f"token-eligible distinct CIKs total: before={len(prior_token_typical_old)} "
        f"after={len(token_eligible_ciks)}",
        flush=True,
    )
    print(
        f"master union: before={len(prior_master)} after={len(master_ciks)} "
        f"dropped={len(prior_master) - len(master_ciks & prior_master)}",
        flush=True,
    )

    # Build aggregate from filtered rows only.
    combined = pl.concat([phrase_filt, token_filt], how="vertical")
    combined = combined.filter(pl.col("cik").is_in(list(master_ciks)))

    agg = (
        combined.group_by("cik")
        .agg(
            pl.col("file_date").min().alias("first_file_date"),
            pl.col("file_date").max().alias("last_file_date"),
            pl.col("adsh").n_unique().alias("total_hits"),
            pl.col("form").unique().sort().alias("forms_list"),
            pl.col("display_names").last().alias("display_name"),
            pl.col("query").unique().alias("queries"),
        )
        .with_columns(
            pl.col("forms_list").list.join(";").alias("forms_touched"),
            pl.col("queries").list.contains("phrase").alias("in_phrase_query"),
            pl.col("queries").list.contains("token").alias("in_token_query"),
            pl.col("cik").is_in(list(deferred_ciks_padded)).alias("in_deferred_csv"),
        )
        .select(
            [
                "cik",
                "display_name",
                "first_file_date",
                "last_file_date",
                "total_hits",
                "forms_touched",
                "in_phrase_query",
                "in_token_query",
                "in_deferred_csv",
            ]
        )
        .sort("cik")
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    agg.write_csv(OUT_PATH)
    print(f"wrote {agg.height} rows to {OUT_PATH}", flush=True)

    in_master = sum(1 for c in deferred_ciks_padded if c in master_ciks)
    print(
        f"deferred CSV CIKs in new master list: {in_master}/{len(deferred_ciks_padded)}",
        flush=True,
    )
    if in_master < len(deferred_ciks_padded):
        missing = deferred_ciks_padded - master_ciks
        print(f"MISSING deferred CIKs: {sorted(missing)}", flush=True)

    print(f"\nrequests issued (incl. cache hits): {STATS['requests']}", flush=True)
    print(f"total elapsed: {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
