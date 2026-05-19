"""Build tras.parquet, events.parquet, and stock_by_date.parquet from the
per-firm summary.qmd files under TRA-contracts/.

  tras.parquet           one row per TRA, columns derived from YAML frontmatter
  events.parquet         one row per timeline bullet across all TRAs
  stock_by_date.parquet  one row per (date, dimension, group_value) with the
                         count of TRAs active at that date in that group

Filename conventions:
  <firm-slug>_summary.qmd                       single-TRA firm
  <firm-slug>_TRA-<date>[-<diff>]_summary.qmd   one of multiple parallel TRAs

Run from the project root with `pixi run -- python scripts/build_tra_database.py`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import polars as pl
import yaml

CORPUS_ROOT_DEFAULT = Path("TRA-contracts")
OUTPUT_DIR_DEFAULT = Path("outputs/tra-database")

SUMMARY_GLOB = "*_summary.qmd"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
EVENT_GROUP_RE = re.compile(r"^####\s+(.+?)\s*$")
EVENT_BULLET_RE = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2}):\s+(.+?)\s*$")
TRA_TIMELINE_HEADING_RE = re.compile(r"^##\s+TRA Timeline\s*$")
NEXT_TOP_HEADING_RE = re.compile(r"^##\s+\S")
TRA_ID_FROM_FILENAME_RE = re.compile(r"_(TRA-[^_]+?)_summary\.qmd$")

TRAS_COLUMNS = [
    "firm_slug",
    "cik",
    "tra_id",
    "summary_path",
    "title",
    "company_names",
    "ciks",
    "status",
    "creation_date",
    "termination_date",
    "last_event_date",
    "tax_asset_types",
    "sharing_ratio",
    "parallel_tras",
    "role",
    "trigger_event_type",
    "counterparty_type",
    "notes",
]

EVENTS_COLUMNS = [
    "firm_slug",
    "cik",
    "tra_id",
    "summary_path",
    "date",
    "event_group",
    "description",
]

STOCK_COLUMNS = [
    "date",
    "dimension",
    "group_value",
    "count",
    "rank",
]

STOCK_DIMENSIONS = [
    "trigger_event_type",
    "counterparty_type",
    "role",
    "status",
    "tax_asset_types",  # multi-valued, exploded on '|'
    "vintage_year",
]


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    body = text[m.end():]
    return fm, body


def derive_tra_id(filename: str, firm_slug: str, creation_date: str | None) -> str:
    """Return the TRA-id token used in parallel-tras references.

    For multi-TRA files the id is embedded in the filename. For single-TRA
    files we synthesize `TRA-<creation-date>` when a creation date is
    present; otherwise return the firm slug as a fallback id."""
    m = TRA_ID_FROM_FILENAME_RE.search(filename)
    if m:
        return m.group(1)
    if creation_date:
        return f"TRA-{creation_date}"
    return f"TRA-{firm_slug}"


def parse_timeline(body: str) -> list[tuple[str, str, str]]:
    """Return list of (event_group, date, description) tuples drawn from
    the `## TRA Timeline` section's bullets."""
    in_timeline = False
    group: str | None = None
    out: list[tuple[str, str, str]] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not in_timeline:
            if TRA_TIMELINE_HEADING_RE.match(line):
                in_timeline = True
            continue
        if NEXT_TOP_HEADING_RE.match(line):
            break
        m_grp = EVENT_GROUP_RE.match(line)
        if m_grp:
            group = m_grp.group(1)
            continue
        m_bul = EVENT_BULLET_RE.match(line)
        if m_bul:
            out.append((group or "", m_bul.group(1), m_bul.group(2)))
    return out


def list_to_pipe(v) -> str:
    """Normalize a YAML list / scalar / None to a pipe-joined string."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "|".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip()


def scalar_or_blank(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def cik_from_firm_slug(firm_slug: str) -> str:
    """Trailing `_<10-digit-cik>` if present, else blank."""
    m = re.search(r"_(\d{10})$", firm_slug)
    return m.group(1) if m else ""


def build_stock_by_date(tras_df: pl.DataFrame, freq: str = "1mo") -> pl.DataFrame:
    """Return a long-format DataFrame of active-TRA counts by date and
    grouping dimension.

    A TRA is "active" at date D when creation_date <= D AND
    (termination_date is null OR termination_date > D). Status is the
    latest known status and does not vary with D; coloring by status
    shows the eventual fate of TRAs active at each historical date.

    `tax_asset_types` is multi-valued; a TRA with both Basis Step-Up and
    NOL contributes one count to each band, so band totals can exceed the
    overall active count.
    """
    parsed = tras_df.with_columns(
        pl.col("creation_date").str.to_date(strict=False).alias("_cd"),
        pl.col("termination_date").str.to_date(strict=False).alias("_td"),
    ).filter(pl.col("_cd").is_not_null())

    if parsed.is_empty():
        return pl.DataFrame(schema={c: pl.String for c in STOCK_COLUMNS}).with_columns(
            pl.col("count").cast(pl.Int64)
        )

    min_d = parsed.select(pl.col("_cd").min()).item()
    today = dt.date.today()
    # Anchor the grid to month-starts spanning [min_creation_month, today_month].
    grid_start = dt.date(min_d.year, min_d.month, 1)
    grid_end = dt.date(today.year, today.month, 1)
    grid = pl.date_range(grid_start, grid_end, interval=freq, eager=True).alias("date")
    grid_df = pl.DataFrame({"date": grid})

    # Cartesian join of TRAs and date grid, then filter to active rows.
    active = (
        parsed.join(grid_df, how="cross")
        .filter(
            (pl.col("_cd") <= pl.col("date"))
            & (pl.col("_td").is_null() | (pl.col("_td") > pl.col("date")))
        )
        .with_columns(pl.col("_cd").dt.year().cast(pl.String).alias("vintage_year"))
    )

    out_frames: list[pl.DataFrame] = []
    for dim in STOCK_DIMENSIONS:
        if dim == "tax_asset_types":
            d = (
                active.with_columns(
                    pl.col("tax_asset_types").str.split("|").alias("_split")
                )
                .explode("_split")
                .with_columns(pl.col("_split").str.strip_chars().alias("group_value"))
                .filter(pl.col("group_value") != "")
            )
        elif dim == "vintage_year":
            d = active.with_columns(pl.col("vintage_year").alias("group_value"))
        else:
            d = active.with_columns(
                pl.when(pl.col(dim) == "").then(pl.lit("(unknown)")).otherwise(pl.col(dim)).alias("group_value")
            )
        grouped = (
            d.group_by(["date", "group_value"])
            .agg(pl.len().alias("count"))
            .with_columns(pl.lit(dim).alias("dimension"))
            .select(["date", "dimension", "group_value", "count"])
        )
        out_frames.append(grouped)

    combined = pl.concat(out_frames)
    # Stable stacking order: per dimension, rank group_values so the order
    # does not flip between adjacent x-ticks. Two regimes:
    #  - vintage_year: rank chronologically (oldest at bottom of stack), so
    #    the time-evolution chart reads as cohorts laid down over time.
    #  - all other dimensions: rank by total count across all dates
    #    (largest band at bottom), which keeps the dominant category
    #    grounded and the visually noisy small categories on top.
    totals = (
        combined.group_by(["dimension", "group_value"])
        .agg(pl.col("count").sum().alias("_total"))
        .with_columns(
            pl.when(pl.col("dimension") == "vintage_year")
            .then(pl.col("group_value").cast(pl.Int64, strict=False))
            .otherwise(
                pl.col("_total")
                .rank(method="ordinal", descending=True)
                .over("dimension")
                .cast(pl.Int64)
            )
            .alias("rank")
        )
        .select(["dimension", "group_value", "rank"])
    )
    return (
        combined.join(totals, on=["dimension", "group_value"], how="left")
        .with_columns(pl.col("date").dt.strftime("%Y-%m-%d"))
        .select(STOCK_COLUMNS)
        .sort(["dimension", "rank", "date"])
    )


def build(
    corpus_root: Path, output_dir: Path
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    tras_rows: list[dict] = []
    events_rows: list[dict] = []
    parse_errors: list[str] = []

    summary_paths = sorted(corpus_root.glob(f"*/{SUMMARY_GLOB}"))
    for path in summary_paths:
        firm_dir = path.parent
        firm_slug = firm_dir.name
        rel_path = path.relative_to(corpus_root.parent).as_posix() if corpus_root.parent != Path("") else path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = split_frontmatter(text)
        except Exception as exc:
            parse_errors.append(f"{path}: {exc}")
            continue

        creation_date = scalar_or_blank(fm.get("creation-date"))
        tra_id = derive_tra_id(path.name, firm_slug, creation_date or None)
        cik_pri = cik_from_firm_slug(firm_slug)

        tras_rows.append({
            "firm_slug": firm_slug,
            "cik": cik_pri,
            "tra_id": tra_id,
            "summary_path": rel_path,
            "title": scalar_or_blank(fm.get("title")),
            "company_names": list_to_pipe(fm.get("company-names")),
            "ciks": list_to_pipe(fm.get("CIKs")),
            "status": scalar_or_blank(fm.get("status")),
            "creation_date": creation_date,
            "termination_date": scalar_or_blank(fm.get("termination-date")),
            "tax_asset_types": list_to_pipe(fm.get("tax-asset-type")),
            "sharing_ratio": scalar_or_blank(fm.get("sharing-ratio")),
            "parallel_tras": list_to_pipe(fm.get("parallel-tras")),
            "role": scalar_or_blank(fm.get("role")),
            "trigger_event_type": scalar_or_blank(fm.get("trigger-event-type")),
            "counterparty_type": scalar_or_blank(fm.get("counterparty-type")),
            "notes": scalar_or_blank(fm.get("notes")),
        })

        for event_group, date_str, description in parse_timeline(body):
            events_rows.append({
                "firm_slug": firm_slug,
                "cik": cik_pri,
                "tra_id": tra_id,
                "summary_path": rel_path,
                "date": date_str,
                "event_group": event_group,
                "description": description,
            })

    if parse_errors:
        print("Parse errors:", file=sys.stderr)
        for e in parse_errors:
            print(f"  {e}", file=sys.stderr)

    tras_schema = {c: pl.String for c in TRAS_COLUMNS}
    events_df = pl.DataFrame(events_rows, schema={c: pl.String for c in EVENTS_COLUMNS})

    # Pull last_event_date per (firm_slug, tra_id) from events.
    last_event = (
        events_df.group_by(["firm_slug", "tra_id"])
        .agg(pl.col("date").max().alias("last_event_date"))
    )
    for row in tras_rows:
        row.setdefault("last_event_date", "")
    tras_df = pl.DataFrame(tras_rows, schema=tras_schema).drop("last_event_date").join(
        last_event, on=["firm_slug", "tra_id"], how="left"
    ).with_columns(pl.col("last_event_date").fill_null("")).select(TRAS_COLUMNS)
    stock_df = build_stock_by_date(tras_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    tras_df.write_parquet(output_dir / "tras.parquet")
    events_df.write_parquet(output_dir / "events.parquet")
    stock_df.write_parquet(output_dir / "stock_by_date.parquet")

    return tras_df, events_df, stock_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(CORPUS_ROOT_DEFAULT))
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR_DEFAULT))
    args = ap.parse_args()

    corpus_root = Path(args.corpus).resolve()
    output_dir = Path(args.output_dir).resolve()

    tras_df, events_df, stock_df = build(corpus_root, output_dir)

    print(f"tras.parquet          rows={len(tras_df):5d}  cols={tras_df.width}  -> {output_dir / 'tras.parquet'}")
    print(f"events.parquet        rows={len(events_df):5d}  cols={events_df.width}  -> {output_dir / 'events.parquet'}")
    print(f"stock_by_date.parquet rows={len(stock_df):5d}  cols={stock_df.width}  -> {output_dir / 'stock_by_date.parquet'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
