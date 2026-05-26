"""Test SEC EDGAR full-text-search coverage for 10-Ks and 8-Ks, 2001-2007.

Method: random-sample 5 10-Ks and 5 8-Ks per year from the SEC quarterly
form indices, download the primary document plus exhibits, extract a
distinctive phrase, query EDGAR full-text search, check whether the
filing's accession is in the results.

Seed: 20260513 (today).
"""

from __future__ import annotations

import json
import random
import re
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx as _httpx
import polars as pl

from sec_edgar.archives import (
    ARCHIVES_BASE,
    accession_no_dashes,
    fetch_document,
    fetch_filing_index,
    _strip_cik,
)
from sec_edgar.client import EdgarClient
from sec_edgar.search import search_filings

SEED = 20260513
YEARS = list(range(2001, 2008))
FORMS = ["10-K", "8-K"]
SAMPLE_PER_YEAR_FORM = 5

PROJECT_ROOT = Path("/home/sulli/research/tra")
FINDINGS_ROOT = PROJECT_ROOT / "coauthor/2026-05-12-edgar-scrape/findings/sec-index"
FORM_IDX_CACHE = PROJECT_ROOT / ".tra_history_cache/edgar_form_idx"
FULL_INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"


def _form_idx_url(year: int, qtr: int) -> str:
    return f"{FULL_INDEX_BASE}/{year}/QTR{qtr}/form.idx"


def fetch_form_idx(cli: EdgarClient, year: int, qtr: int) -> str:
    url = _form_idx_url(year, qtr)
    cache_path = FORM_IDX_CACHE / f"{year}_QTR{qtr}_form.idx"
    body, _meta = cli.get(url, cache_path=cache_path, cache_max_age_s=365 * 24 * 3600)
    return body.decode("utf-8", errors="replace")


# form.idx is fixed-width:
# Form Type   Company Name   CIK   Date Filed   Filename
# We use a tolerant split.
_IDX_LINE_RE = re.compile(
    r"^(?P<form>\S+(?:\s\S+)?)\s{2,}(?P<company>.+?)\s{2,}(?P<cik>\d+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<filename>\S+)\s*$"
)


def parse_form_idx(text: str, target_form: str) -> list[dict]:
    """Parse form.idx, return rows for the target form (exact match)."""
    rows: list[dict] = []
    # Skip header lines (first ~10 lines until separator of dashes)
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            body_start = i + 1
            break
    for line in lines[body_start:]:
        if not line.strip():
            continue
        # Use column positions: Form Type is leftmost 12 chars.
        form_field = line[:12].strip()
        if form_field != target_form:
            continue
        # Tolerant parse for the rest
        rest = line[12:]
        m = re.match(
            r"^(?P<company>.+?)\s{2,}(?P<cik>\d+)\s+"
            r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<filename>\S+)\s*$",
            rest,
        )
        if not m:
            continue
        filename = m.group("filename")
        # filename like edgar/data/<cik>/<accession>.txt or .../<accession>-index.htm
        m_acc = re.search(r"(\d{10}-\d{2}-\d{6})", filename)
        if not m_acc:
            continue
        rows.append(
            {
                "form": target_form,
                "company": m.group("company").strip(),
                "cik": m.group("cik"),
                "date": m.group("date"),
                "accession": m_acc.group(1),
            }
        )
    return rows


def sample_filings(cli: EdgarClient, rng: random.Random) -> list[dict]:
    samples: list[dict] = []
    for year in YEARS:
        pools: dict[str, list[dict]] = {f: [] for f in FORMS}
        for qtr in (1, 2, 3, 4):
            text = fetch_form_idx(cli, year, qtr)
            for form in FORMS:
                pools[form].extend(parse_form_idx(text, form))
        for form in FORMS:
            pool = pools[form]
            if len(pool) < SAMPLE_PER_YEAR_FORM:
                print(f"WARN: pool for {year} {form} has only {len(pool)} filings")
                picks = pool
            else:
                picks = rng.sample(pool, SAMPLE_PER_YEAR_FORM)
            for p in picks:
                p["year"] = year
                samples.append(p)
            print(f"sampled {year} {form}: pool={len(pool)} picked={len(picks)}")
    return samples


def doc_local_dir(year: int, form: str, cik: str, accession: str) -> Path:
    form_lit = form.replace("-", "")  # 10-K -> 10K, 8-K -> 8K
    cik_padded = cik.zfill(10)
    acc_nd = accession_no_dashes(accession)
    return FINDINGS_ROOT / f"{year}-{form_lit}" / cik_padded / acc_nd


def looks_like_index_file(name: str) -> bool:
    n = name.lower()
    if re.search(r"-index[-.]", n):
        return True
    if n in ("index.json", "index.htm", "index.html", "filing-summary.xml"):
        return True
    return False


def looks_like_exhibit_name(name: str) -> bool:
    n = name.lower()
    return bool(re.search(r"ex-?\d", n))


def select_docs_to_download(
    idx_df: pl.DataFrame, accession: str
) -> tuple[str | None, list[str]]:
    """Return (primary_doc_name, exhibit_names).

    Strategy adapts to filing era:
    - Modern (2004+): primary is the largest non-index .htm/.html; exhibits
      are files matching ex-?\\d (.htm/.html/.txt).
    - Early (pre-2003): primary is the largest numbered .txt (e.g. 0001.txt);
      exhibits are the other numbered .txt files.
    Files without a size field are kept but ranked last.
    """
    if "name" not in idx_df.columns:
        return None, []
    names = idx_df["name"].to_list()
    sizes_raw = (
        idx_df["size"].to_list() if "size" in idx_df.columns else [""] * len(names)
    )
    def sz(s):
        try:
            return int(s)
        except (TypeError, ValueError):
            return 0
    sizes = [sz(s) for s in sizes_raw]

    # candidate documents: text files that aren't the index header
    candidates = []
    for name, size in zip(names, sizes):
        if looks_like_index_file(name):
            continue
        n = name.lower()
        if not n.endswith((".htm", ".html", ".txt")):
            continue
        # Skip the concatenated full-submission .txt: it's huge and
        # duplicative. Pattern: <accession>.txt at top level.
        if n == f"{accession.lower()}.txt":
            continue
        candidates.append((name, size))

    if not candidates:
        # Early-era fallback: serve the concatenated submission .txt
        full_sub = f"{accession}.txt"
        if full_sub in names:
            return full_sub, []
        return None, []

    # Sort by size desc; largest is likely the main document
    candidates.sort(key=lambda x: -x[1])

    # Try modern-style exhibit detection first
    primary = None
    exhibits: list[str] = []
    modern_exhibits = [name for name, _ in candidates if looks_like_exhibit_name(name)]
    modern_non_ex = [name for name, _ in candidates if not looks_like_exhibit_name(name)]

    if modern_non_ex and modern_exhibits:
        primary = modern_non_ex[0]
        exhibits = modern_exhibits
    elif modern_non_ex:
        # No matching exhibits; use first as primary, rest as exhibits
        primary = modern_non_ex[0]
        exhibits = modern_non_ex[1:]
    else:
        # Only "exhibit-named" files; treat largest as primary
        primary = modern_exhibits[0]
        exhibits = modern_exhibits[1:]

    return primary, exhibits


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_AMP_RE = re.compile(r"&[a-z]+;|&#\d+;", re.IGNORECASE)


def strip_html(text: str) -> str:
    t = _HTML_TAG_RE.sub(" ", text)
    t = _AMP_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t)
    return t.strip()


_ALLCAPS_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\b")
_DOLLAR_RE = re.compile(r"\$\s*\d")
_SECTION_RE = re.compile(r"\bSection\s+\d", re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    # crude sentence splitter
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)


def extract_phrase(raw_text: str) -> str | None:
    """Return a 6-7 word verbatim phrase from a middle sentence, or None."""
    stripped = strip_html(raw_text)
    sents = split_sentences(stripped)
    # Filter to sentences of 80-300 chars, no ALL-CAPS tokens, no $amounts, no Section refs
    candidates = []
    for s in sents:
        s = s.strip()
        if not (80 <= len(s) <= 300):
            continue
        if _ALLCAPS_TOKEN_RE.search(s):
            continue
        if _DOLLAR_RE.search(s):
            continue
        if _SECTION_RE.search(s):
            continue
        candidates.append(s)
    if not candidates:
        return None
    # Middle sentence
    middle = candidates[len(candidates) // 2]
    words = middle.split()
    if len(words) < 7:
        return None
    # Try to take 6-7 contiguous words from the middle; skip any phrase with all-caps token
    n = len(words)
    for start in range(max(0, n // 2 - 3), max(1, n - 7)):
        for length in (7, 6):
            phrase_words = words[start : start + length]
            if len(phrase_words) < length:
                continue
            phrase = " ".join(phrase_words)
            if _ALLCAPS_TOKEN_RE.search(phrase):
                continue
            # Strip trailing punctuation cleanly
            phrase = phrase.strip(",.;:")
            if len(phrase.split()) >= 6:
                return phrase
    return None


def search_with_retry(
    q: str, ciks: str, startdt: str, enddt: str, client: EdgarClient
) -> tuple[pl.DataFrame, dict] | tuple[None, dict]:
    """Wrap search_filings with 1-2 retries on HTTP 500."""
    last_err = None
    for attempt in range(3):
        try:
            lf, meta = search_filings(
                q=q,
                ciks=ciks,
                startdt=startdt,
                enddt=enddt,
                client=client,
                max_results=200,
            )
            return lf.collect(), meta
        except Exception as e:  # noqa: BLE001  (intentional broad catch; we report)
            msg = str(e)
            if "500" in msg or "502" in msg or "503" in msg or "504" in msg:
                last_err = e
                time.sleep(1.5)
                continue
            raise
    return None, {"error": f"5xx after retries: {last_err}"}


def shift_date(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def test_one_filing(filing: dict, cli: EdgarClient) -> dict:
    cik = filing["cik"]
    accession = filing["accession"]
    form = filing["form"]
    year = filing["year"]
    file_date = filing["date"]

    result = {
        "year": year,
        "form": form,
        "cik": cik,
        "accession": accession,
        "company": filing["company"],
        "file_date": file_date,
        "primary_status": None,
        "exhibit_status": None,
        "overall_status": "ERROR",
        "primary_phrase": None,
        "exhibit_count": 0,
        "exhibit_indexed_count": 0,
        "error": None,
    }
    try:
        idx_df = fetch_filing_index(cik, accession, client=cli).collect()
    except Exception as e:  # noqa: BLE001
        result["error"] = f"index fetch failed: {e}"
        return result

    primary, exhibits = select_docs_to_download(idx_df, accession)
    if primary is None:
        result["error"] = "no primary document identified"
        return result

    local_dir = doc_local_dir(year, form, cik, accession)
    local_dir.mkdir(parents=True, exist_ok=True)

    # Download primary; on 404 (common in pre-2003 filings), fall back to
    # the concatenated <accession>.txt full submission, which holds the
    # whole filing including exhibits.
    body = None
    tried = []
    for candidate in (primary, f"{accession}.txt"):
        if candidate in tried:
            continue
        tried.append(candidate)
        try:
            body = fetch_document(cik, accession, candidate, client=cli, as_text=True)
            primary = candidate
            break
        except _httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                continue
            result["error"] = f"primary fetch failed ({candidate}): {e}"
            return result
        except Exception as e:  # noqa: BLE001
            result["error"] = f"primary fetch failed ({candidate}): {e}"
            return result
    if body is None:
        result["error"] = f"primary fetch 404 for all candidates: {tried}"
        return result
    (local_dir / primary).write_text(body, encoding="utf-8", errors="replace")

    primary_phrase = extract_phrase(body)
    result["primary_phrase"] = primary_phrase

    startdt = shift_date(file_date, -180)
    enddt = shift_date(file_date, 180)
    cik_padded = cik.zfill(10)

    primary_indexed = False
    if primary_phrase:
        df, meta = search_with_retry(
            f'"{primary_phrase}"', cik_padded, startdt, enddt, cli
        )
        if df is not None and "adsh" in df.columns:
            primary_indexed = accession in df["adsh"].to_list()
        result["primary_status"] = (
            "INDEXED" if primary_indexed else "NOT_FOUND"
        )
    else:
        result["primary_status"] = "NO_PHRASE"

    # Exhibits
    result["exhibit_count"] = len(exhibits)
    any_exhibit_indexed = False
    for ex_name in exhibits[:5]:  # cap exhibits at 5 per filing to stay within budget
        try:
            ex_body = fetch_document(cik, accession, ex_name, client=cli, as_text=True)
        except _httpx.HTTPStatusError:
            continue
        except Exception:  # noqa: BLE001
            continue
        (local_dir / ex_name).write_text(ex_body, encoding="utf-8", errors="replace")
        ex_phrase = extract_phrase(ex_body)
        if not ex_phrase:
            continue
        df, meta = search_with_retry(
            f'"{ex_phrase}"', cik_padded, startdt, enddt, cli
        )
        if df is not None and "adsh" in df.columns:
            if accession in df["adsh"].to_list():
                any_exhibit_indexed = True
                result["exhibit_indexed_count"] += 1
                break  # one success is enough

    result["exhibit_status"] = (
        "INDEXED" if any_exhibit_indexed else (
            "NOT_FOUND" if exhibits else "NO_EXHIBITS"
        )
    )

    if primary_indexed:
        result["overall_status"] = "INDEXED_BODY"
    elif any_exhibit_indexed:
        result["overall_status"] = "INDEXED_EXHIBIT"
    elif result["primary_status"] == "NO_PHRASE" and not exhibits:
        result["overall_status"] = "NO_PHRASE"
    else:
        result["overall_status"] = "NOT_FOUND"
    result["error"] = None
    return result


def main() -> None:
    rng = random.Random(SEED)
    FINDINGS_ROOT.mkdir(parents=True, exist_ok=True)
    cli = EdgarClient()
    try:
        print("=" * 60)
        print(f"Sampling filings (seed={SEED})")
        print("=" * 60)
        samples = sample_filings(cli, rng)
        print(f"Total samples: {len(samples)}")
        # Persist sample list for reproducibility
        (FINDINGS_ROOT / "samples.json").write_text(
            json.dumps(samples, indent=2), encoding="utf-8"
        )

        results: list[dict] = []
        for i, filing in enumerate(samples, 1):
            print(
                f"[{i}/{len(samples)}] {filing['year']} {filing['form']} "
                f"CIK={filing['cik']} {filing['accession']} {filing['company'][:40]}"
            )
            try:
                res = test_one_filing(filing, cli)
            except Exception as e:  # noqa: BLE001
                res = {
                    "year": filing["year"],
                    "form": filing["form"],
                    "cik": filing["cik"],
                    "accession": filing["accession"],
                    "company": filing["company"],
                    "file_date": filing["date"],
                    "overall_status": "ERROR",
                    "error": f"unhandled: {e}\n{traceback.format_exc()}",
                }
            print(f"    -> {res.get('overall_status')}  err={res.get('error')}")
            results.append(res)

        (FINDINGS_ROOT / "results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        print(f"wrote {FINDINGS_ROOT / 'results.json'}")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
