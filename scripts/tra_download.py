"""TRA filing downloader (implements .claude/skills/tra-download-filings)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
import polars as pl

from sec_edgar.archives import fetch_document
from sec_edgar.client import EdgarClient
from sec_edgar.forms import list_filings_by_form
from sec_edgar.search import search_filings
from sec_edgar.submissions import fetch_submissions

SUBMISSIONS_CACHE_ROOT = Path(".tra_history_cache/edgar_submissions")


PHRASE_Q = (
    '"tax receivable agreement" OR "tax receivable agreements" '
    'OR "tax receivables agreement" OR "tax receivables agreements"'
)
TOKEN_Q = "TRA"
EVENTS_Q = (
    '"Chapter 11" OR "Chapter 7" OR "voluntary petition" '
    'OR "plan of reorganization" OR "plan of liquidation" '
    'OR "rejection of executory contracts" '
    'OR "agreement and plan of merger" OR "merger consideration" '
    'OR "tender offer" OR "asset purchase agreement" '
    'OR "going-private"'
)
# The SEC full-text-search `forms` parameter silently returns ~0 hits
# when the comma-separated list contains slash-bearing codes
# (10-K/A, 10-Q/A, 8-K/A, S-1/A, S-4/A, DRS/A). Do NOT pass `forms` to
# search_filings(); post-filter on the `form` column locally instead.
ALLOWED_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "6-K",
    "DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A",
    "8-K", "8-K/A",
    "S-1", "S-1/A", "S-4", "S-4/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "DRS", "DRS/A",
}
COMPLETENESS_FORMS = (
    "S-1", "S-1/A", "S-4", "S-4/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
)


def search_with_retry(*args, max_attempts: int = 3, backoff_s: float = 1.5, **kwargs):
    last_5xx = 0
    for attempt in range(max_attempts):
        try:
            return search_filings(*args, **kwargs), last_5xx
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_attempts - 1:
                last_5xx += 1
                time.sleep(backoff_s)
                continue
            raise


def _manifest_lines_for_cik(cik: str, s: dict) -> list[str]:
    lines = [
        f"## CIK {cik}",
        f"- phrase-OR hits: {s['phrase_hits']}",
        f"- TRA-token hits: {s['token_hits']}",
        f"- events-query hits: {s['events_hits']}",
        f"- events-query net-new (adsh, primary_doc) pairs: {s['events_only_count']}",
        f"- union (adsh, primary_doc) pairs: {s['union_count']}",
        f"- downloaded from search union: {s['downloaded_from_search']}",
        f"- total downloaded (incl. completeness): {s['total_downloaded']}",
        "- events-query form breakdown:",
    ]
    for f, n in s["events_form_breakdown"].items():
        lines.append(f"  - {f}: {n}")
    lines.append("- completeness pass added per form:")
    for f, n in s["completeness_added"].items():
        lines.append(f"  - {f}: {n}")
    if s["events_only_rows"]:
        lines.append("- events-only filings (net-new):")
        for r in s["events_only_rows"]:
            lines.append(
                f"  - {r['filed']} {r['form']} {r['adsh']} {r['primary_doc']}"
            )
    lines.append("")
    return lines


def _slugify(name: str) -> str:
    """Lowercase, replace runs of non-alphanumeric chars with single
    hyphens, strip leading/trailing hyphens. Matches the convention of
    the prior rename pass on the 26 originally-renamed firms.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _name_for_cik(
    cik: str,
    client: EdgarClient | None = None,
    cache_root: Path = SUBMISSIONS_CACHE_ROOT,
) -> str | None:
    """Resolve the registrant's `name` field. Reads the cached
    submissions JSON if present (no network), else fetches via
    fetch_submissions (one HTTP request, cached on disk). Returns None
    only if both routes fail to surface a usable name (caller falls
    back to a plain-CIK directory).
    """
    cached = cache_root / f"CIK{cik}.json"
    if cached.exists():
        try:
            payload = json.loads(cached.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if payload:
            name = payload.get("name")
            if name:
                return name
    # Cache absent or unparseable: go to the network. Pass
    # include_continuations=False so we don't pay for filings pagination
    # just to learn the name.
    _, static = fetch_submissions(
        cik, client=client, include_continuations=False
    )
    return static.get("name")


def _resolve_cik_dir(
    out_root: Path,
    cik: str,
    client: EdgarClient | None = None,
) -> Path:
    """Return the on-disk directory for this firm. Preference order:
    (1) reuse an existing `<slug>_<cik>/` directory if one exists under
    out_root; (2) otherwise create `<slug>_<cik>/` using the slugified
    name from the submissions JSON; (3) if the name cannot be resolved,
    fall back to a plain-CIK directory.
    """
    for candidate in out_root.glob(f"*_{cik}"):
        if candidate.is_dir():
            return candidate
    name = _name_for_cik(cik, client=client)
    if name:
        slug = _slugify(name)
        if slug:
            return out_root / f"{slug}_{cik}"
    return out_root / cik


def _completed_ciks_from_manifest(manifest_path: Path) -> set[str]:
    """Parse `## CIK <padded>` headers from an existing manifest file
    and return the set of CIK strings already written. Returns an empty
    set if the manifest does not exist.
    """
    if not manifest_path.exists():
        return set()
    completed: set[str] = set()
    pat = re.compile(r"^## CIK (\d{10,})\s*$")
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                completed.add(m.group(1))
    return completed


def download_filings(ciks: list[str], output_dir: str | Path) -> dict:
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict] = {}
    retries_total = 0
    errors_4xx: list[str] = []
    failures: list[dict] = []

    # Initialize the manifest with a header so per-CIK appends are
    # well-formed even if the process dies after the first firm. If the
    # manifest already exists (resume case), do not clobber it.
    manifest = out_root / "download_log.md"
    if not manifest.exists():
        manifest.write_text("# TRA download manifest\n\n", encoding="utf-8")

    # Resume: skip CIKs whose section has already been written to the
    # manifest by a prior run.
    completed_already = _completed_ciks_from_manifest(manifest)
    skipped_resume = 0

    # Share one EdgarClient across the loop so the rate-limit token
    # bucket is process-wide, the connection pool is reused, and
    # _name_for_cik / search_filings / fetch_document all share state.
    client = EdgarClient()
    try:
        for raw_cik in ciks:
            # SEC full-text-search `ciks` parameter requires 10-digit zero-padded
            # form; passing the unpadded CIK silently returns zero hits. Normalize
            # any caller input (padded or not) to the canonical 10-digit form and
            # use it for every downstream call, output path, and manifest entry.
            cik = raw_cik.lstrip("0").zfill(10)
            if cik in completed_already:
                skipped_resume += 1
                continue
            cik_stats: dict = {"cik": cik}
            # Per-firm guard: any uncaught exception under this CIK is
            # recorded and the loop continues to the next CIK rather
            # than killing the whole run. The narrow exceptions for
            # httpx 4xx during document fetches are still handled inline
            # (those are routine and should not look like firm failures).
            current_stage = "init"
            try:
                current_stage = "resolve_cik_dir"
                cik_dir = _resolve_cik_dir(out_root, cik, client=client)
                current_stage = "phrase_search"
                (lf_a, meta_a), r1 = search_with_retry(
                    PHRASE_Q, ciks=cik, client=client
                )
                current_stage = "token_search"
                (lf_b, meta_b), r2 = search_with_retry(
                    TOKEN_Q, ciks=cik, client=client
                )
                current_stage = "events_search"
                (lf_c, meta_c), r3 = search_with_retry(
                    EVENTS_Q, ciks=cik, client=client
                )
                retries_total += r1 + r2 + r3
                current_stage = "search_collect"
                df_a_raw = lf_a.collect()
                df_b_raw = lf_b.collect()
                df_c_raw = lf_c.collect()
                cik_stats["phrase_hits_raw"] = df_a_raw.height
                cik_stats["token_hits_raw"] = df_b_raw.height
                cik_stats["events_hits_raw"] = df_c_raw.height
                df_a = df_a_raw.filter(pl.col("form").is_in(ALLOWED_FORMS))
                df_b = df_b_raw.filter(pl.col("form").is_in(ALLOWED_FORMS))
                df_c = df_c_raw.filter(pl.col("form").is_in(ALLOWED_FORMS))
                cik_stats["phrase_hits"] = df_a.height
                cik_stats["token_hits"] = df_b.height
                cik_stats["events_hits"] = df_c.height
                cik_stats["phrase_form_breakdown"] = dict(
                    df_a.group_by("form").len().sort("form").iter_rows()
                )
                cik_stats["token_form_breakdown"] = dict(
                    df_b.group_by("form").len().sort("form").iter_rows()
                )
                cik_stats["events_form_breakdown"] = dict(
                    df_c.group_by("form").len().sort("form").iter_rows()
                )

                # Track which (adsh, pdoc) pairs the TRA-keyword searches
                # already covered, so we can identify net-new contributions
                # from the events query for the manifest.
                tra_pairs: set[tuple[str, str]] = set()
                for df in (df_a, df_b):
                    if df.height == 0:
                        continue
                    for row in df.iter_rows(named=True):
                        adsh = row["adsh"]
                        pdoc = row["primary_doc"]
                        if not adsh or not pdoc:
                            continue
                        tra_pairs.add((adsh, pdoc))

                union_pairs: set[tuple[str, str]] = set()
                union_rows: dict[tuple[str, str], dict] = {}
                events_only_pairs: set[tuple[str, str]] = set()
                events_only_rows: list[dict] = []
                for df in (df_a, df_b, df_c):
                    if df.height == 0:
                        continue
                    for row in df.iter_rows(named=True):
                        adsh = row["adsh"]
                        pdoc = row["primary_doc"]
                        if not adsh or not pdoc:
                            continue
                        key = (adsh, pdoc)
                        if key not in union_pairs:
                            union_pairs.add(key)
                            union_rows[key] = row
                # Net-new contributions from the events query.
                if df_c.height > 0:
                    for row in df_c.iter_rows(named=True):
                        adsh = row["adsh"]
                        pdoc = row["primary_doc"]
                        if not adsh or not pdoc:
                            continue
                        key = (adsh, pdoc)
                        if key not in tra_pairs and key not in events_only_pairs:
                            events_only_pairs.add(key)
                            events_only_rows.append(row)
                cik_stats["union_count"] = len(union_pairs)
                cik_stats["events_only_count"] = len(events_only_pairs)
                cik_stats["events_only_rows"] = [
                    {"adsh": r["adsh"], "form": r.get("form"),
                     "filed": r.get("filed"), "primary_doc": r["primary_doc"]}
                    for r in events_only_rows
                ]

                current_stage = "search_download"
                downloaded: set[tuple[str, str]] = set()
                for adsh, pdoc in sorted(union_pairs):
                    target = cik_dir / adsh / pdoc
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        downloaded.add((adsh, pdoc))
                        continue
                    try:
                        body = fetch_document(cik, adsh, pdoc)
                    except httpx.HTTPStatusError as e:
                        errors_4xx.append(
                            f"{cik}/{adsh}/{pdoc}: HTTP {e.response.status_code}"
                        )
                        continue
                    if isinstance(body, str):
                        target.write_text(body, encoding="utf-8")
                    else:
                        target.write_bytes(body)
                    downloaded.add((adsh, pdoc))
                cik_stats["downloaded_from_search"] = len(downloaded)

                # Step 3: completeness pass
                current_stage = "completeness"
                completeness_added: dict[str, int] = {}
                for form_type in COMPLETENESS_FORMS:
                    lf = list_filings_by_form(cik, form_type)
                    df = lf.select(
                        ["accessionNumber", "primaryDocument", "form"]
                    ).collect()
                    added = 0
                    for row in df.iter_rows(named=True):
                        adsh = row["accessionNumber"]
                        pdoc = row["primaryDocument"]
                        if not adsh or not pdoc:
                            continue
                        key = (adsh, pdoc)
                        if key in downloaded:
                            continue
                        target = cik_dir / adsh / pdoc
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists():
                            downloaded.add(key)
                            added += 1
                            continue
                        try:
                            body = fetch_document(cik, adsh, pdoc)
                        except httpx.HTTPStatusError as e:
                            errors_4xx.append(
                                f"{cik}/{adsh}/{pdoc}: HTTP {e.response.status_code}"
                            )
                            continue
                        if isinstance(body, str):
                            target.write_text(body, encoding="utf-8")
                        else:
                            target.write_bytes(body)
                        downloaded.add(key)
                        added += 1
                    completeness_added[form_type] = added
                cik_stats["completeness_added"] = completeness_added
                cik_stats["total_downloaded"] = len(downloaded)
                stats[cik] = cik_stats

                # Append this firm's section to the manifest immediately
                # so the manifest reflects completed firms even if the
                # process dies.
                with manifest.open("a", encoding="utf-8") as fh:
                    fh.write(
                        "\n".join(_manifest_lines_for_cik(cik, cik_stats))
                        + "\n"
                    )
            except Exception as e:  # noqa: BLE001 (firm-level guard)
                failures.append(
                    {
                        "cik": cik,
                        "stage": current_stage,
                        "exception_class": type(e).__name__,
                        "message": str(e),
                    }
                )
                # Deliberately do NOT write a `## CIK` header for failed
                # firms, so the resume check retries them next run.
                continue
    finally:
        client.close()

    # Final sections: failures, then anomalies.
    if failures:
        fail_lines = ["## Failures"]
        for f in failures:
            fail_lines.append(
                f"- CIK {f['cik']} stage={f['stage']} "
                f"{f['exception_class']}: {f['message']}"
            )
        with manifest.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(fail_lines) + "\n")

    anomaly_lines = ["## Anomalies", f"- 5xx retries fired: {retries_total}"]
    if errors_4xx:
        anomaly_lines.append("- 4xx errors:")
        for e in errors_4xx:
            anomaly_lines.append(f"  - {e}")
    else:
        anomaly_lines.append("- 4xx errors: none")
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(anomaly_lines) + "\n")

    return {
        "stats": stats,
        "retries_5xx": retries_total,
        "errors_4xx": errors_4xx,
        "failures": failures,
        "skipped_resume": skipped_resume,
    }


if __name__ == "__main__":
    import sys

    ciks = sys.argv[1].split(",")
    out = sys.argv[2]
    result = download_filings(ciks=ciks, output_dir=out)
    print(json.dumps(result, indent=2, default=str))
