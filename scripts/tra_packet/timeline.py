"""Filing-list construction and packet rendering.

Given a CIK, builds a filtered filing list from the Submissions JSON
covering: every 10-K / 10-Q / 10-K/A / 10-Q/A, every 8-K / 8-K/A, the
earliest S-1 / S-1/A, and the latest DEF 14A. The skill consumes this
list, fetches each primary document via ``sec_edgar``, and renders the
packet markdown.

The packet path is the per-firm directory:
``coauthor/2026-05-12-edgar-scrape/findings/packets/<slug>/<slug>.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl


PACKETS_ROOT = Path("coauthor/2026-05-12-edgar-scrape/findings/packets")


def slugify_company(name: str) -> str:
    """Return a filesystem-safe slug from a company name."""
    s = name.lower().strip()
    s = re.sub(r"[,.&'/()]+", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


@dataclass
class FilingRow:
    accession: str
    form: str
    filing_date: str
    report_date: str | None
    primary_doc: str
    items: str | None
    size: int | None
    bucket: str  # "S-1" | "10-K" | "10-Q" | "8-K" | "DEF 14A"


@dataclass
class PacketContext:
    cik: str
    cik_padded: str
    company_name: str
    csv_signals: dict
    filings: list[FilingRow] = field(default_factory=list)


_PERIODIC_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
_EVENT_FORMS = {"8-K", "8-K/A"}
_REGISTRATION_FORMS = {"S-1", "S-1/A"}
_PROXY_FORMS = {"DEF 14A"}


def build_filing_list(
    submissions_lf: pl.LazyFrame,
) -> list[FilingRow]:
    """Return the per-firm filing list per the SKILL methodology.

    Inputs: the LazyFrame returned by ``fetch_submissions``. Columns
    expected: ``accessionNumber``, ``filingDate``, ``reportDate``,
    ``form``, ``primaryDocument``, ``items``, ``size``.
    """
    df = submissions_lf.collect()
    if df.height == 0:
        return []

    wanted = _PERIODIC_FORMS | _EVENT_FORMS | _REGISTRATION_FORMS | _PROXY_FORMS
    df = df.filter(pl.col("form").is_in(list(wanted)))

    rows: list[FilingRow] = []

    # 10-K, 10-Q, 8-K, DEF 14A: take all. Full firm lifetime coverage.
    for r in df.filter(
        pl.col("form").is_in(
            list(_PERIODIC_FORMS | _EVENT_FORMS | _PROXY_FORMS)
        )
    ).iter_rows(named=True):
        rows.append(_to_filing_row(r))

    # S-1: earliest only. The earliest S-1 carries the original TRA
    # exhibit; later amendments rarely add TRA-relevant material.
    s1 = df.filter(pl.col("form").is_in(list(_REGISTRATION_FORMS)))
    if s1.height > 0:
        earliest = s1.sort("filingDate").head(1).row(0, named=True)
        rows.append(_to_filing_row(earliest))

    # Sort the final list ascending by filing date.
    rows.sort(key=lambda x: (x.filing_date or "0000-00-00", x.accession))
    return rows


def _to_filing_row(r: dict) -> FilingRow:
    form = r.get("form")
    if form in _REGISTRATION_FORMS:
        bucket = "S-1"
    elif form in _PERIODIC_FORMS:
        bucket = "10-K" if "10-K" in (form or "") else "10-Q"
    elif form in _EVENT_FORMS:
        bucket = "8-K"
    elif form in _PROXY_FORMS:
        bucket = "DEF 14A"
    else:
        bucket = form or ""
    items = r.get("items")
    if isinstance(items, list):
        items = ",".join(str(x) for x in items if x is not None)
    size = r.get("size")
    if isinstance(size, str) and size.isdigit():
        size = int(size)
    return FilingRow(
        accession=r["accessionNumber"],
        form=form or "",
        filing_date=r.get("filingDate") or "",
        report_date=r.get("reportDate"),
        primary_doc=r.get("primaryDocument") or "",
        items=items if isinstance(items, str) and items else None,
        size=size if isinstance(size, int) else None,
        bucket=bucket,
    )


def archives_url(cik_unpadded: str, accession: str, primary_doc: str) -> str:
    acc_nd = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_unpadded}/"
        f"{acc_nd}/{primary_doc}"
    )


def write_packet(
    ctx: PacketContext,
    timeline_rows: list[dict],
    headline_summary: str,
    saved_exhibits: list | None = None,
    concept_meta: dict | None = None,
    out_path: Path | None = None,
) -> Path:
    """Write the per-firm packet markdown to disk.

    ``timeline_rows``: one dict per filing, columns described in SKILL.md.
    ``headline_summary``: the leading text block at the top of the
    packet; the reviewer agent writes this based on the evidence.

    The mechanical packet ships with placeholder content in the
    "Headline summary", "Per-filing notes", and "Open questions"
    sections. The downstream reviewer agent fills them in by reading
    each TRA-mentioning filing and recording findings.
    """
    slug = slugify_company(ctx.company_name)
    pkt_dir = (out_path or PACKETS_ROOT) / slug
    pkt_dir.mkdir(parents=True, exist_ok=True)
    pkt_md = pkt_dir / f"{slug}.md"

    parts: list[str] = []
    parts.append(f"# {ctx.company_name} (CIK {ctx.cik_padded})\n")
    parts.append("## Headline summary\n")
    parts.append(headline_summary.strip() + "\n")

    parts.append("\n## Existing pipeline signals\n")
    csv = ctx.csv_signals
    parts.append(f"- last_present_period: {csv.get('last_present_period')}")
    parts.append(f"- cancel_signal_period (regex): {csv.get('cancel_signal_period')}")
    parts.append(f"- pipeline t+1 accession: {csv.get('t_plus_1_adsh')}")
    if csv.get("cancel_excerpt"):
        parts.append(
            f"- regex excerpt (verbatim from CSV): {csv['cancel_excerpt']}"
        )
    if csv.get("cancel_filing_url"):
        parts.append(f"- cancel_filing_url: {csv['cancel_filing_url']}")
    if csv.get("last_present_filing_url"):
        parts.append(f"- last_present_filing_url: {csv['last_present_filing_url']}")
    manual = csv.get("Manual Check") or csv.get("manual_check")
    if manual:
        parts.append(f"\n### Prior manual note (verbatim)\n\n> {manual}")
        if csv.get("Source:") or csv.get("source"):
            parts.append(f"\nSource: {csv.get('Source:') or csv.get('source')}")
        if csv.get("Source context:") or csv.get("source_context"):
            parts.append(
                f"\nSource context: {csv.get('Source context:') or csv.get('source_context')}"
            )

    # TRA event timeline: a structured table the reviewer agent fills
    # in after working through the per-filing evidence. Event types
    # include Registration, Execution, Amendment, Transfer, Termination,
    # Bankruptcy, Up-C collapse, and any other event affecting the TRA.
    parts.append("\n## TRA event timeline\n")
    parts.append(
        "_Reviewer agent fills in one row per material TRA event. "
        "Event types: Registration (pre-IPO), Execution (IPO), "
        "Amendment, Transfer (M&A), Termination, Bankruptcy, Up-C "
        "collapse, and other. The 'brief summary' column expects "
        "concrete content (what an amendment amended; whether a "
        "restructure related to anything besides the Up-C)._\n"
    )
    parts.append("| date | event | filing link | brief summary |")
    parts.append("|---|---|---|---|")
    parts.append("| _to fill in_ | _to fill in_ | _to fill in_ | _to fill in_ |")

    # TRA exhibits: the manifest of TRA contract documents collected
    # by tra_packet.exhibits.collect_tra_exhibits. Each row is a
    # unique exhibit by content hash; re-filings of the same contract
    # in subsequent filings are deduped.
    parts.append("\n## TRA exhibits\n")
    if not saved_exhibits:
        parts.append("_No TRA-contract exhibits were identified._\n")
    else:
        parts.append(
            f"_{len(saved_exhibits)} unique exhibit(s) identified. "
            "Each is a TRA-contract document; re-filings of the same "
            "exhibit are deduped by content hash._\n"
        )
        parts.append(
            "| filing date | accession | sgml type | tra mentions | size (bytes) | saved file |"
        )
        parts.append("|---|---|---|---|---|---|")
        for ex in saved_exhibits:
            rel = ex.saved_path.relative_to(pkt_dir) if (
                ex.saved_path.is_relative_to(pkt_dir)
            ) else ex.saved_path
            parts.append(
                f"| {ex.filing_date} | {ex.accession} | "
                f"{ex.sgml_type} | {ex.tra_phrase_count} | "
                f"{ex.byte_size:,} | [{rel}]({rel}) |"
            )

    # XBRL TRA-liability series (Company Concept API). When any row
    # in the series carries ``requires_verification = True`` (the
    # standard us-gaap TRA-specific tag returned 404 and a non-TRA
    # fallback was served), the section header is prefixed with a
    # warning so the reviewer agent verifies the values against the
    # actual 10-K balance sheet before citing them.
    series_rows = (concept_meta or {}).get("series_rows") or []
    any_requires_verification = any(
        r.get("requires_verification") for r in series_rows
    ) or bool((concept_meta or {}).get("requires_verification"))
    xbrl_header = "## XBRL TRA-liability series (from Company Concept API)"
    if any_requires_verification:
        xbrl_header += (
            " (FALLBACK TAG: standard us-gaap fallback used; verify "
            "against the actual filing)"
        )
    parts.append(f"\n{xbrl_header}\n")
    if not concept_meta:
        parts.append("_Not fetched._\n")
    elif concept_meta.get("found"):
        parts.append(
            f"- Resolved concept: `{concept_meta['taxonomy']}` / "
            f"`{concept_meta['concept']}`"
        )
        if concept_meta.get("tag_requested") and (
            concept_meta.get("tag_used")
            and concept_meta["tag_used"] != concept_meta["tag_requested"]
        ):
            parts.append(
                f"- **Fallback in effect:** requested "
                f"`{concept_meta['tag_requested']}`; served "
                f"`{concept_meta['tag_used']}`. The served tag is NOT "
                "TRA-specific; the values may represent a different "
                "liability category and require verification against "
                "the firm's 10-K balance sheet before citation."
            )
        if concept_meta.get("label"):
            parts.append(f"- Label: {concept_meta['label']}")
        if concept_meta.get("tried"):
            tried_str = ", ".join(
                f"{t['taxonomy']}/{t['concept']}={'hit' if t['found'] else '404'}"
                for t in concept_meta["tried"]
            )
            parts.append(f"- Fallback walk: {tried_str}")
        if series_rows:
            parts.append(
                "\n| period end | value | unit | form | filed | requires_verification |"
            )
            parts.append("|---|---|---|---|---|---|")
            for r in series_rows:
                val = r.get("val")
                val_str = f"{val:,.0f}" if val is not None else ""
                rv = "true" if r.get("requires_verification") else "false"
                parts.append(
                    f"| {r.get('end')} | {val_str} | {r.get('unit')} | "
                    f"{r.get('form')} | {r.get('filed')} | {rv} |"
                )
    else:
        tried_str = ", ".join(
            f"{t['taxonomy']}/{t['concept']}"
            for t in (concept_meta.get("tried") or [])
        )
        parts.append(
            f"_No standard us-gaap TRA-liability concept resolved for "
            f"this CIK. Tried: {tried_str or 'none'}. The firm likely "
            f"used a filer-specific custom XBRL tag for its TRA "
            f"liability, which the Company Concept API does not "
            f"expose; the reviewer agent should consult the firm's "
            f"Company Facts API or read the TRA liability directly "
            f"from the periodic filings' tax footnotes._\n"
        )

    parts.append("\n## Filing timeline\n")
    parts.append(
        "| filed | form | accession | tra_mention | items | doc |"
    )
    parts.append("|---|---|---|---|---|---|")
    for r in timeline_rows:
        tra = "yes" if r.get("tra_mention") else ""
        items = r.get("items") or ""
        doc_url = r.get("doc_url") or ""
        doc_link = (
            f"[{r.get('primary_doc') or 'doc'}]({doc_url})" if doc_url else ""
        )
        parts.append(
            f"| {r.get('filing_date')} | {r.get('form')} | "
            f"{r.get('accession')} | {tra} | {items} | {doc_link} |"
        )

    # Per-filing notes: one placeholder entry per TRA-mentioning
    # filing. The reviewer agent navigates each filing via its table
    # of contents (older filings without a TOC fall back to text
    # search), reads the TRA-relevant sections, and fills in the
    # findings here.
    parts.append("\n## Per-filing notes\n")
    parts.append(
        "_Reviewer agent fills in one entry per TRA-mentioning filing. "
        "Per the skill methodology: navigate the filing via its table "
        "of contents to the TRA-relevant sections, read those sections, "
        "and record the findings below. Older filings without a usable "
        "TOC fall back to in-document text search for the phrase "
        "'tax receivable agreement'._\n"
    )
    tra_filings = [r for r in timeline_rows if r.get("tra_mention")]
    if not tra_filings:
        parts.append("_No TRA-mentioning filings were located in the timeline._\n")
    for r in tra_filings:
        parts.append(
            f"\n### {r.get('filing_date')} {r.get('form')} "
            f"({r.get('accession')})\n"
        )
        if r.get("doc_url"):
            parts.append(f"**Source:** <{r['doc_url']}>")
        if r.get("excerpts_path"):
            parts.append(
                f"**Cached TRA excerpts (non-GAAP-filtered):** "
                f"`{r['excerpts_path']}`"
            )
        if r.get("toc_path"):
            parts.append(f"**Cached TOC index:** `{r['toc_path']}`")
        if r.get("excerpts_count") is not None:
            parts.append(
                f"**Excerpt count:** {r.get('excerpts_kept', 0)} kept "
                f"of {r['excerpts_count']} total "
                f"(non-GAAP table matches excluded)"
            )
        parts.append("")
        parts.append("- **Section names where TRA appears:** _to fill in_")
        parts.append("- **Summary of TRA-relevant content:** _to fill in_")
        parts.append(
            "- **Extraction hints for future agents** "
            "(anchor names, TOC entries, search terms, navigation steps): "
            "_to fill in_"
        )

    parts.append("\n## Open questions for the reviewer\n")
    # The skill author fills these in based on the evidence; this is
    # a placeholder for downstream insertion via a second write.
    parts.append("_Author the open questions below based on the evidence above._\n")

    pkt_md.write_text("\n".join(parts))
    return pkt_md
