"""SEC EDGAR access primitives.

Rate-limited, cache-aware fetchers for the EDGAR JSON APIs and the
Archives filing tree. See README.md in this directory for invocation
patterns and trial-run records.
"""

__version__ = "0.1.0"

__all__ = [
    "EdgarClient",
    "USER_AGENT",
    "fetch_submissions",
    "fetch_filing_index",
    "fetch_document",
    "search_filings",
    "list_filings_by_form",
    "fetch_filing",
    "__version__",
]


def __getattr__(name):
    # Lazy re-exports so ``python -m sec_edgar.<mod>`` does not emit the
    # "found in sys.modules after import of package" RuntimeWarning.
    if name in {"EdgarClient", "USER_AGENT"}:
        from sec_edgar.client import EdgarClient, USER_AGENT
        return {"EdgarClient": EdgarClient, "USER_AGENT": USER_AGENT}[name]
    if name == "fetch_submissions":
        from sec_edgar.submissions import fetch_submissions
        return fetch_submissions
    if name in {"fetch_filing_index", "fetch_document"}:
        from sec_edgar.archives import fetch_filing_index, fetch_document
        return {"fetch_filing_index": fetch_filing_index,
                "fetch_document": fetch_document}[name]
    if name == "search_filings":
        from sec_edgar.search import search_filings
        return search_filings
    if name in {"list_filings_by_form", "fetch_filing"}:
        from sec_edgar.forms import list_filings_by_form, fetch_filing
        return {"list_filings_by_form": list_filings_by_form,
                "fetch_filing": fetch_filing}[name]
    raise AttributeError(name)
