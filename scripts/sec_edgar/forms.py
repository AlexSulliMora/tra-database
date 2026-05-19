"""High-level fetchers combining submissions + archives.

Two functions:

- :func:`list_filings_by_form` filters a registrant's Submissions
  history to one form type and an optional date range, returning a
  LazyFrame of matching filings.
- :func:`fetch_filing` resolves the primary document for one accession
  via the Submissions API (avoiding an index.json fetch when possible)
  and returns the document text plus the directory listing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from sec_edgar.client import EdgarClient
from sec_edgar.submissions import fetch_submissions
from sec_edgar.archives import fetch_document, fetch_filing_index


def list_filings_by_form(
    cik: str | int,
    form_type: str,
    startdt: str | date | None = None,
    enddt: str | date | None = None,
    client: EdgarClient | None = None,
) -> pl.LazyFrame:
    """Return a LazyFrame of filings for ``cik`` matching ``form_type``.

    ``form_type`` is matched exactly against the ``form`` column. The
    optional date range is inclusive and applied against ``filingDate``.
    """
    lf, _static = fetch_submissions(cik, client=client)
    out = lf.filter(pl.col("form") == form_type)
    if startdt is not None:
        out = out.filter(pl.col("filingDate") >= str(startdt))
    if enddt is not None:
        out = out.filter(pl.col("filingDate") <= str(enddt))
    return out


def fetch_filing(
    cik: str | int,
    accession: str,
    client: EdgarClient | None = None,
) -> tuple[str | bytes, pl.LazyFrame]:
    """Resolve and fetch the primary document for one accession.

    Returns ``(primary_doc, index_lazyframe)``. The primary doc is
    resolved by looking up ``filings.recent`` (or any continuation
    block) on the Submissions JSON for the CIK; if the accession is not
    present, we fall back to the filing's ``index.json``.
    """
    own = client is None
    cli = client if client is not None else EdgarClient()
    try:
        lf_filings, _static = fetch_submissions(cik, client=cli)
        row = (
            lf_filings.filter(pl.col("accessionNumber") == accession)
            .select(["accessionNumber", "primaryDocument", "form"])
            .collect()
        )
        if row.height >= 1 and row["primaryDocument"][0]:
            primary_name = row["primaryDocument"][0]
        else:
            idx = fetch_filing_index(cik, accession, client=cli).collect()
            # Heuristic: prefer the first .htm that isn't the index page.
            cand = idx.filter(
                pl.col("name").str.ends_with(".htm")
                & ~pl.col("name").str.contains("index", literal=False)
            )
            if cand.height == 0:
                raise RuntimeError(
                    f"could not infer primary document for {cik}/{accession}"
                )
            primary_name = cand["name"][0]

        idx_lf = fetch_filing_index(cik, accession, client=cli)
        body = fetch_document(cik, accession, primary_name, client=cli)
        return body, idx_lf
    finally:
        if own:
            cli.close()


def _self_test() -> None:
    """Trial run: Apple's 2023 10-K accession round-trips."""
    cik = "0000320193"
    accession = "0000320193-23-000106"
    body, idx_lf = fetch_filing(cik, accession)
    idx_df = idx_lf.collect()
    print(f"filing index rows: {idx_df.height}")
    print(f"primary doc len: {len(body):,}")
    if isinstance(body, str):
        head = body[:120].replace("\n", " ")
        print(f"primary doc head: {head!r}")
        if "10-K" not in body and "Apple" not in body:
            raise RuntimeError(
                "primary doc text missing both '10-K' and 'Apple' tokens"
            )
    print("\nlist_filings_by_form(cik=Apple, form='10-K') head:")
    lf = list_filings_by_form(cik, "10-K")
    df = lf.collect()
    print(df.select(["accessionNumber", "filingDate", "form"]).head(5))
    if df.height == 0:
        raise RuntimeError("expected >0 Apple 10-K filings")


if __name__ == "__main__":
    _self_test()
