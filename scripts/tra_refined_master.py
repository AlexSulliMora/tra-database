"""Refined TRA master CIK list using only phrase-OR hits, with
body/exhibit classification on primary_doc.

No SEC requests; cached search responses only.
"""

from __future__ import annotations

import re
import sys
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
SAFE_WINDOW_HITS = 700
CACHE_MAX_AGE_S = 365 * 24 * 3600

# Tighter exhibit regex: ex must be at start OR preceded by [-_./].
EXHIBIT_RE = re.compile(
    r"(?:^|[-_./])(ex[-_\.]?\d|exhibit\d|dex\d|ex99)", re.IGNORECASE
)

BODY_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A",
    "8-K", "8-K/A",
    "20-F", "40-F", "6-K",
    "DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A",
}
EXHIBIT_FORMS = {
    "8-K", "8-K/A",
    "S-1", "S-1/A",
    "S-4", "S-4/A",
    "DRS", "DRS/A",
    "10-K", "10-Q",
}


def is_exhibit(primary_doc: str | None) -> bool:
    if primary_doc is None:
        return False
    name = primary_doc.rsplit("/", 1)[-1]
    return bool(EXHIBIT_RE.search(name))


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
    print(f"start: {datetime.now().isoformat()}", flush=True)

    deferred = pl.read_csv(DEFERRED_CSV, infer_schema_length=0)
    deferred_ciks_padded = {
        c.zfill(10) for c in deferred["cik"].cast(pl.Int64).cast(pl.String).to_list()
    }

    cli = EdgarClient()
    try:
        rows: list[dict] = []
        collect_partitioned(PHRASE_Q, START_DATE, END_DATE, cli, rows)
    finally:
        cli.close()
    print(f"phrase-OR raw doc-level rows: {len(rows)}", flush=True)

    df = pl.DataFrame(rows).with_columns(
        pl.col("display_names").cast(pl.List(pl.String)),
        pl.col("ciks").cast(pl.List(pl.String)),
        pl.col("primary_doc")
        .map_elements(is_exhibit, return_dtype=pl.Boolean)
        .alias("is_exhibit"),
    ).with_columns(
        pl.col("display_names").list.join("; ").alias("display_names_joined"),
    )

    # ---- Quick 10-K body/exhibit recount with tighter regex ----
    tk = df.filter(pl.col("form") == "10-K")
    tk_per = (
        tk.group_by("adsh")
        .agg(
            pl.col("is_exhibit").any().alias("has_exhibit"),
            (~pl.col("is_exhibit")).any().alias("has_body"),
        )
    )
    n10k_body = tk_per.filter(pl.col("has_body")).height
    n10k_exh = tk_per.filter(pl.col("has_exhibit")).height
    n10k_both = tk_per.filter(pl.col("has_body") & pl.col("has_exhibit")).height
    print(
        f"10-K body/exhibit (tighter regex): body={n10k_body} "
        f"exhibit={n10k_exh} both={n10k_both} total_adsh={tk_per.height}",
        flush=True,
    )

    # ---- Build the qualifying (cik, adsh, form, signal) set ----
    # body rows: form in BODY_FORMS AND is_exhibit False
    body_qual = df.filter(
        pl.col("form").is_in(list(BODY_FORMS)) & ~pl.col("is_exhibit")
    ).with_columns(pl.lit("body").alias("doc_class"))
    exh_qual = df.filter(
        pl.col("form").is_in(list(EXHIBIT_FORMS)) & pl.col("is_exhibit")
    ).with_columns(pl.lit("exhibit").alias("doc_class"))
    qual = pl.concat([body_qual, exh_qual], how="vertical")

    # Explode ciks.
    qual_exp = qual.explode("ciks").rename({"ciks": "cik"}).with_columns(
        pl.col("cik").str.zfill(10).alias("cik"),
    ).filter(
        pl.col("cik").is_not_null() & (pl.col("cik").str.len_chars() == 10)
    )

    print(
        f"qualifying body rows: {body_qual.height}, exhibit rows: {exh_qual.height}",
        flush=True,
    )

    # Per-form per-class distinct CIK counts.
    per_form_class = (
        qual_exp.group_by(["form", "doc_class"])
        .agg(pl.col("cik").n_unique().alias("n_ciks"))
        .pivot(index="form", on="doc_class", values="n_ciks")
        .fill_null(0)
        .sort("form")
    )
    print("\nPer-form distinct-CIK counts:", flush=True)
    with pl.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=120):
        print(per_form_class)

    # CIK-level classification: body-only / exhibit-only / both.
    cik_class = (
        qual_exp.group_by("cik")
        .agg(
            (pl.col("doc_class") == "body").any().alias("has_body"),
            (pl.col("doc_class") == "exhibit").any().alias("has_exhibit"),
        )
        .with_columns(
            pl.when(pl.col("has_body") & pl.col("has_exhibit"))
            .then(pl.lit("both"))
            .when(pl.col("has_body"))
            .then(pl.lit("body-only"))
            .otherwise(pl.lit("exhibit-only"))
            .alias("signal_class"),
        )
    )

    class_counts = cik_class.group_by("signal_class").agg(pl.len().alias("n"))
    print("\nCIK signal_class breakdown:", flush=True)
    for row in class_counts.iter_rows(named=True):
        print(f"  {row['signal_class']}: {row['n']}", flush=True)
    print(f"  total: {cik_class.height}", flush=True)

    # Build the aggregate CSV using ALL doc-level rows (body and exhibit
    # combined) restricted to the qualifying universe, so per-CIK
    # first/last file_date and forms_touched reflect the whole picture.
    agg = (
        qual_exp.group_by("cik")
        .agg(
            pl.col("file_date").min().alias("first_file_date"),
            pl.col("file_date").max().alias("last_file_date"),
            pl.col("adsh").n_unique().alias("total_hits"),
            pl.col("form").unique().sort().alias("forms_list"),
            pl.col("display_names_joined").last().alias("display_name"),
        )
        .with_columns(
            pl.col("forms_list").list.join(";").alias("forms_touched"),
            pl.col("cik").is_in(list(deferred_ciks_padded)).alias("in_deferred_csv"),
        )
        .join(cik_class.select(["cik", "signal_class"]), on="cik", how="left")
        # Retain the old in_phrase_query / in_token_query columns for
        # schema continuity: phrase is now the only source, token is
        # unused.
        .with_columns(
            pl.lit(True).alias("in_phrase_query"),
            pl.lit(False).alias("in_token_query"),
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
                "signal_class",
            ]
        )
        .sort("cik")
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    agg.write_csv(OUT_PATH)
    print(f"\nwrote {agg.height} rows to {OUT_PATH}", flush=True)

    in_master = sum(1 for c in deferred_ciks_padded if c in set(agg["cik"].to_list()))
    print(
        f"deferred CSV CIKs in refined master list: "
        f"{in_master}/{len(deferred_ciks_padded)}",
        flush=True,
    )
    if in_master < len(deferred_ciks_padded):
        missing = deferred_ciks_padded - set(agg["cik"].to_list())
        print(f"MISSING deferred CIKs: {sorted(missing)}", flush=True)


if __name__ == "__main__":
    main()
