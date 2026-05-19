"""Build a single-file, file://-portable HTML dashboard for the TRA database.

Reads outputs/tra-database/{tras.parquet, events.parquet, stock_by_date.parquet}
plus outputs/tra-database/dashboard.template.html, embeds the three datasets
as JSON, and writes outputs/tra-database/dashboard.html.

Run after scripts/build_tra_database.py refreshes the parquets:
  pixi run -- python scripts/build_dashboard.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

DEFAULT_DIR = Path("outputs/tra-database")


def read_inputs(d: Path):
    tras = pl.read_parquet(d / "tras.parquet")
    events = pl.read_parquet(d / "events.parquet")
    stock = pl.read_parquet(d / "stock_by_date.parquet")
    return tras, events, stock


def safe_json(records: list[dict]) -> str:
    # `</script>` inside JSON would break the host script block; escape it.
    return json.dumps(records, separators=(",", ":")).replace("</", "<\\/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    args = ap.parse_args()

    d = Path(args.dir).resolve()
    template_path = d / "dashboard.template.html"
    out_path = d / "dashboard.html"

    if not template_path.exists():
        print(f"missing template: {template_path}", file=sys.stderr)
        return 1

    tras, events, stock = read_inputs(d)
    template = template_path.read_text(encoding="utf-8")
    html = (
        template
        .replace("__TRAS_JSON__",   safe_json(tras.to_dicts()))
        .replace("__EVENTS_JSON__", safe_json(events.to_dicts()))
        .replace("__STOCK_JSON__",  safe_json(stock.to_dicts()))
    )
    out_path.write_text(html, encoding="utf-8")

    print(f"dashboard.html  {len(html):>9,d} chars  tras={len(tras)} events={len(events)} stock={len(stock)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
