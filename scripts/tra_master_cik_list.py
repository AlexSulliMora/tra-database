"""Build a master list of every SEC-filer CIK that has ever appeared in a
filing mentioning a Tax Receivable Agreement (TRA).

Strategy: two EDGAR full-text search queries spanning 2001-01-01 to today,
partitioned recursively by date. EDGAR full-text search becomes unreliable
(spurious 500s) at deep pagination offsets, so each window is first
probed with size=10 to learn its total; if total > 700 we split before
paginating, keeping every retrieved window inside the safe depth band.

- Phrase-OR: "tax receivable agreement" plus three plural variants.
- Token: TRA.

Local post-filter: keep a CIK only if it appears in the phrase-OR result
OR appears in the TRA-token result with >=3 distinct accessions in
TRA-typical forms.
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))

from sec_edgar.client import EdgarClient  # noqa: E402  (added by sys.path above)
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

TRA_TYPICAL_FORMS = {
    "10-K", "10-Q", "8-K", "S-1", "S-4",
    "DEF 14A", "DEFA14A", "DEFM14A",
}

# Empirically, full-text-search 500s appear around offset ~800. Splitting
# windows so that total <= SAFE_WINDOW_HITS keeps every fetch under that
# bound.
SAFE_WINDOW_HITS = 700


def is_typical_form(form: str | None) -> bool:
    if form is None:
        return False
    if form in TRA_TYPICAL_FORMS:
        return True
    if form.startswith("424B"):
        return True
    return False


# Counters for the report.
STATS = {
    "requests": 0,
    "5xx_retries": 0,
    "4xx_errors": 0,
    "5xx_after_retries": 0,
    "windows_probed": 0,
    "windows_fetched": 0,
    "windows_split": 0,
}


def _is_5xx(msg: str) -> bool:
    return any(c in msg for c in ("500", "502", "503", "504"))


def _is_4xx(msg: str) -> bool:
    return any(c in msg for c in (" 400", " 403", " 404", "'400", "'403", "'404"))


def search_with_retry(
    q: str,
    startdt: str,
    enddt: str,
    client: EdgarClient,
    max_results: int | None = None,
):
    """Wrap search_filings with retries on transient 5xx."""
    last_err = None
    for attempt in range(3):
        try:
            lf, meta = search_filings(
                q=q,
                startdt=startdt,
                enddt=enddt,
                client=client,
                max_results=max_results,
            )
            STATS["requests"] += 1
            return lf.collect(), meta
        except Exception as e:  # noqa: BLE001 (intentional; we report)
            msg = str(e)
            if _is_5xx(msg) and attempt < 2:
                STATS["5xx_retries"] += 1
                last_err = e
                time.sleep(1.0 + attempt)
                continue
            if _is_4xx(msg):
                STATS["4xx_errors"] += 1
                print(
                    f"  4xx on [{startdt},{enddt}] (max_results={max_results}): {msg}",
                    flush=True,
                )
                return None, {"error": msg}
            if _is_5xx(msg):
                STATS["5xx_after_retries"] += 1
                print(
                    f"  5xx-after-retries on [{startdt},{enddt}] "
                    f"(max_results={max_results}): {msg}",
                    flush=True,
                )
                return None, {"error": msg}
            raise
    return None, {"error": f"5xx after retries: {last_err}"}


def search_partitioned(
    q: str,
    startdt: date,
    enddt: date,
    client: EdgarClient,
    rows_accum: list[dict],
    depth: int = 0,
) -> None:
    """Recursively partition the date range so each fetched window has
    total <= SAFE_WINDOW_HITS. Each window is first probed with
    max_results=10 to learn its total without paginating.
    """
    if startdt > enddt:
        return
    s = startdt.isoformat()
    e = enddt.isoformat()

    # Probe.
    STATS["windows_probed"] += 1
    df, meta = search_with_retry(q, s, e, client, max_results=10)
    if df is None:
        # Probe failed. Split if we can, else give up on this window.
        if startdt < enddt:
            mid = startdt + (enddt - startdt) // 2
            STATS["windows_split"] += 1
            print(
                f"  [d={depth}] probe failed on [{s},{e}]; splitting",
                flush=True,
            )
            search_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
            search_partitioned(
                q, mid + timedelta(days=1), enddt, client, rows_accum, depth + 1
            )
        else:
            print(f"  [d={depth}] giving up on single-day window [{s},{e}]", flush=True)
        return

    total = int(meta.get("total", 0))
    relation = meta.get("relation", "eq")
    if total == 0:
        print(f"  [d={depth}] [{s},{e}] total=0; skipping", flush=True)
        return
    if total > SAFE_WINDOW_HITS and startdt < enddt:
        # Split.
        mid = startdt + (enddt - startdt) // 2
        STATS["windows_split"] += 1
        print(
            f"  [d={depth}] [{s},{e}] total={total} relation={relation} -> split",
            flush=True,
        )
        search_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
        search_partitioned(
            q, mid + timedelta(days=1), enddt, client, rows_accum, depth + 1
        )
        return

    # Fetch the full window.
    STATS["windows_fetched"] += 1
    df2, meta2 = search_with_retry(q, s, e, client)
    if df2 is None:
        # Fetch failed even though probe succeeded; try splitting.
        if startdt < enddt:
            mid = startdt + (enddt - startdt) // 2
            STATS["windows_split"] += 1
            print(
                f"  [d={depth}] fetch failed on [{s},{e}] (probe total={total}); splitting",
                flush=True,
            )
            search_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
            search_partitioned(
                q, mid + timedelta(days=1), enddt, client, rows_accum, depth + 1
            )
        else:
            print(
                f"  [d={depth}] single-day fetch failure [{s},{e}] (lost up to {total} hits)",
                flush=True,
            )
        return
    fetched2 = int(meta2.get("fetched", 0))
    total2 = int(meta2.get("total", 0))
    hit_cap2 = bool(meta2.get("hit_cap"))
    print(
        f"  [d={depth}] [{s},{e}] total={total2} fetched={fetched2} "
        f"hit_cap={hit_cap2}",
        flush=True,
    )
    if df2.height > 0:
        rows_accum.extend(df2.to_dicts())
    # If we fell short despite the probe saying it was safe, split.
    if fetched2 < total2 and startdt < enddt:
        # Re-fetch the still-missing portion by date split (cached pages
        # already retrieved will be returned from cache).
        mid = startdt + (enddt - startdt) // 2
        STATS["windows_split"] += 1
        print(
            f"  [d={depth}] partial fetch on [{s},{e}] (fetched {fetched2} of {total2}); splitting",
            flush=True,
        )
        # Clear out the partial rows we just appended for this window
        # and re-collect from sub-windows.
        del rows_accum[-df2.height :]
        search_partitioned(q, startdt, mid, client, rows_accum, depth + 1)
        search_partitioned(
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
    print(f"date range: {START_DATE} to {END_DATE}", flush=True)

    deferred = pl.read_csv(DEFERRED_CSV, infer_schema_length=0)
    deferred_ciks_padded = {
        c.zfill(10) for c in deferred["cik"].cast(pl.Int64).cast(pl.String).to_list()
    }
    print(f"deferred CSV CIKs: {len(deferred_ciks_padded)}", flush=True)

    cli = EdgarClient()
    try:
        print("\n=== Query 1: Phrase-OR ===", flush=True)
        phrase_rows: list[dict] = []
        search_partitioned(PHRASE_Q, START_DATE, END_DATE, cli, phrase_rows)
        print(f"phrase-OR rows collected: {len(phrase_rows)}", flush=True)

        print("\n=== Query 2: TRA token ===", flush=True)
        token_rows: list[dict] = []
        search_partitioned(TOKEN_Q, START_DATE, END_DATE, cli, token_rows)
        print(f"TRA-token rows collected: {len(token_rows)}", flush=True)
    finally:
        cli.close()

    phrase_df = flatten_to_cik_rows(phrase_rows, "phrase")
    token_df = flatten_to_cik_rows(token_rows, "token")

    phrase_df = phrase_df.filter(
        pl.col("cik").is_not_null() & (pl.col("cik").str.len_chars() == 10)
    )
    token_df = token_df.filter(
        pl.col("cik").is_not_null() & (pl.col("cik").str.len_chars() == 10)
    )

    print(
        f"\nphrase rows after explode: {phrase_df.height}; "
        f"token rows after explode: {token_df.height}",
        flush=True,
    )

    token_typical = token_df.with_columns(
        pl.col("form")
        .map_elements(is_typical_form, return_dtype=pl.Boolean)
        .alias("is_typical")
    ).filter(pl.col("is_typical"))
    token_cik_counts = (
        token_typical.group_by("cik")
        .agg(pl.col("adsh").n_unique().alias("n_accessions_typical"))
    )
    token_eligible_ciks = set(
        token_cik_counts.filter(pl.col("n_accessions_typical") >= 3)["cik"].to_list()
    )
    phrase_ciks = set(phrase_df["cik"].unique().to_list())
    token_all_ciks = set(token_df["cik"].unique().to_list())

    print(f"phrase distinct CIKs: {len(phrase_ciks)}", flush=True)
    print(f"token distinct CIKs (all): {len(token_all_ciks)}", flush=True)
    print(
        f"token distinct CIKs (>=3 typical-form accessions): "
        f"{len(token_eligible_ciks)}",
        flush=True,
    )

    master_ciks = phrase_ciks | token_eligible_ciks
    print(f"master list size: {len(master_ciks)}", flush=True)

    combined = pl.concat([phrase_df, token_df], how="vertical")
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
    print(f"\nwrote {agg.height} rows to {OUT_PATH}", flush=True)

    elapsed = time.time() - t0
    print("\n=== STATS ===", flush=True)
    print(f"elapsed_seconds: {elapsed:.1f}", flush=True)
    print(f"sec_requests_issued: {STATS['requests']}", flush=True)
    print(f"5xx_retries: {STATS['5xx_retries']}", flush=True)
    print(f"5xx_after_retries: {STATS['5xx_after_retries']}", flush=True)
    print(f"4xx_errors: {STATS['4xx_errors']}", flush=True)
    print(f"windows_probed: {STATS['windows_probed']}", flush=True)
    print(f"windows_fetched: {STATS['windows_fetched']}", flush=True)
    print(f"windows_split: {STATS['windows_split']}", flush=True)
    print(f"phrase_raw_hits: {len(phrase_rows)}", flush=True)
    print(f"token_raw_hits: {len(token_rows)}", flush=True)
    print(
        f"aggregate_raw_hits: {len(phrase_rows) + len(token_rows)}", flush=True
    )

    print("\n=== Year buckets (by first_file_date) ===", flush=True)
    bucketed = agg.with_columns(
        pl.col("first_file_date").str.slice(0, 4).cast(pl.Int64).alias("year")
    ).with_columns(
        ((pl.col("year") - 2001) // 5 * 5 + 2001).alias("bucket_start")
    )
    bucket_counts = (
        bucketed.group_by("bucket_start").agg(pl.len().alias("n_ciks")).sort("bucket_start")
    )
    for row in bucket_counts.iter_rows(named=True):
        bs = row["bucket_start"]
        if bs is None:
            print(f"  (null year): {row['n_ciks']}", flush=True)
            continue
        print(f"  {bs}-{bs+4}: {row['n_ciks']}", flush=True)

    in_master = sum(1 for c in deferred_ciks_padded if c in master_ciks)
    print(
        f"\ndeferred CSV CIKs found in master list: "
        f"{in_master}/{len(deferred_ciks_padded)}",
        flush=True,
    )
    missing = deferred_ciks_padded - master_ciks
    if missing:
        print(f"missing deferred CIKs: {sorted(missing)}", flush=True)
    new_ciks = master_ciks - deferred_ciks_padded
    print(f"new CIKs (not in deferred CSV): {len(new_ciks)}", flush=True)


if __name__ == "__main__":
    main()
