# SEC EDGAR conventions and schema reference

> **Verification status.** Direct WebFetch against `*.sec.gov` returned HTTP 403 to the research tooling, so content here was synthesized from third-party SEC documentation mirrors plus search-result summaries citing the canonical SEC pages. Canonical verification of any specific schema or naming claim happens when the S2 Python client (with its own conforming User-Agent header) is invoked against it.

Naming, numbering, and tagging conventions you need to construct URLs, interpret filing metadata, and link records across the Electronic Data Gathering, Analysis, and Retrieval (EDGAR) data products. For URL templates see [access patterns](access-patterns.md); for which product to choose see [resources](resources.md); for rate and access rules see [limitations](limitations.md).

## Central Index Key (CIK)

Every entity that interacts with the Securities and Exchange Commission (SEC) is assigned a CIK, a numeric identifier. Two conventions appear in practice:

- **Zero-padded 10-digit** (`0000320193`): used in URL paths under `data.sec.gov/submissions/CIK##########.json`, in XBRL accession context references, and in the `cik` field of `company_tickers.json`.
- **Unpadded** (`320193`): accepted in `cgi-bin/browse-edgar` query strings and in many human-facing surfaces. The Archives directory tree (`Archives/edgar/data/320193/...`) also accepts the unpadded form.

When in doubt, pad to 10 digits with leading zeros. The padded form works everywhere; the unpadded form does not. In Python:

```python
cik_padded = f"{int(cik):010d}"
```

## Accession number

The accession number uniquely identifies one submitted filing. Format:

```
<filer_CIK_18_chars>-<YY>-<NNNNNN>
```

Concretely: `0001193125-15-118890`. The leading 10 digits identify the filer, the middle two are the year, the trailing six are a per-filer sequence. Two surface forms:

- **Dashed**: `0001193125-15-118890`. Used in API responses (Submissions, text search), in human-facing pages, and in the `<accession>-index.htm` filename inside a filing folder.
- **Dash-stripped (18 digits)**: `000119312515118890`. Used in the URL path to the filing folder: `Archives/edgar/data/<CIK>/000119312515118890/`.

The 10 prefix digits in the accession are the **filer's** CIK, often the registrant. For some filings (e.g., third-party filed by a financial printer like Donnelley Financial), the prefix differs from the registrant's CIK; the canonical CIK to use for URL construction is always the registrant's, accessible via the Submissions API `cik` field.

Translation in Python:

```python
accession_dash = "0001193125-15-118890"
accession_nodash = accession_dash.replace("-", "")
```

## Form-type taxonomy

EDGAR form names follow a stable taxonomy. The forms most relevant to corporate-event monitoring:

| Form | Meaning |
|------|---------|
| `S-1` / `S-3` / `S-11` | Registration statement for an initial or follow-on securities offering. S-1 is the IPO standard. |
| `S-4` | Registration statement used in business combinations (mergers, exchange offers). |
| `424B*` | Final prospectus (the variants `424B1` through `424B7` differ by filing trigger; `424B3` and `424B4` are the common ones). |
| `10-K` | Annual report (domestic issuer). |
| `10-Q` | Quarterly report (domestic issuer). |
| `8-K` | Current report; event-driven, due within four business days of the triggering event. |
| `20-F` | Annual report for a foreign private issuer. |
| `6-K` | Current report for a foreign private issuer (semi-annual or as-events-occur). |
| `40-F` | Canadian issuer annual report under the Multijurisdictional Disclosure System. |
| `DEF 14A` | Definitive proxy statement (annual meeting). |
| `PRE 14A` | Preliminary proxy statement. |
| `SC 13D` / `SC 13G` | Beneficial ownership reports (>5% stake; 13D for active, 13G for passive). |
| `Form 4` | Insider transaction report. |
| `Form 3` | Initial statement of beneficial ownership by an insider. |

A suffix `/A` denotes an amendment (e.g., `10-K/A`, `8-K/A`). For form-type filters in the Submissions API and Atom feeds, the base form usually matches both base and amendment; specify `8-K/A` explicitly if you want only amendments.

For Tax Receivable Agreement (TRA) monitoring specifically: TRAs are typically executed at IPO (filed as exhibits to S-1/424B), modified or referenced in 10-K/10-Q (via XBRL-tagged deferred tax line items), and terminated/triggered events are disclosed via 8-K (Items 1.01, 1.02, 2.01, see below).

## 8-K Item numbers

The 8-K is the workhorse for event monitoring; each filing carries one or more Item numbers indicating the triggering event(s). Items relevant to a TRA-monitoring pipeline:

| Item | Title | Why it matters for TRAs |
|------|-------|--------------------------|
| 1.01 | Entry into a Material Definitive Agreement | New TRA, TRA amendment, side-letter |
| 1.02 | Termination of a Material Definitive Agreement | TRA cancellation / termination |
| 2.01 | Completion of Acquisition or Disposition of Assets | M&A that may trigger TRA payout (change-of-control acceleration) |
| 2.03 | Creation of a Direct Financial Obligation | Cash obligation linked to TRA payment, or new TRA obligation |
| 2.04 | Triggering Events That Accelerate or Increase a Direct Financial Obligation | TRA acceleration on default, change of control |
| 3.02 | Unregistered Sales of Equity Securities | Up-C structure unit exchanges that flow through a TRA |
| 3.03 | Material Modification to Rights of Security Holders | Up-C collapse, dual-class collapse |
| 5.02 | Departure / Appointment of Directors and Officers | Useful indirectly; founders / TRA beneficiaries leaving |
| 5.03 | Amendments to Articles of Incorporation or Bylaws | Up-C collapse mechanics |
| 5.07 | Submission of Matters to a Vote of Security Holders | Shareholder vote on M&A or restructuring |
| 7.01 | Regulation Fair Disclosure (FD) Disclosure | Material non-public information disclosed to selected parties |
| 8.01 | Other Events | Catch-all; TRA-relevant disclosures sometimes filed here |
| 9.01 | Financial Statements and Exhibits | Where the TRA exhibit is actually attached |

For the project's 8-K monitoring sketch, the high-value filter is `1.01 | 1.02 | 2.01 | 2.04 | 3.03` plus a phrase-search confirmation via text search for "tax receivable agreement".

## Exhibit numbering

Exhibits to SEC filings follow the numbering of Regulation S-K Item 601 (17 CFR 229.601). The number prefix carries categorical meaning:

| Exhibit | Category | TRA relevance |
|---------|----------|----------------|
| 2.x | Plan of acquisition, reorganization, merger, etc. | Triggers TRA acceleration |
| 3.x | Articles of incorporation, bylaws | Up-C structure documents |
| 4.x | Instruments defining rights of securityholders | Indenture, warrant agreement |
| 10.x | Material contracts | **TRAs typically filed here**; also management contracts, credit agreements |
| 21.x | Subsidiaries of the registrant | Identifies Up-C operating partnership |
| 23.x | Consents of experts and counsel | Auditor consents |
| 31.x | Sarbanes-Oxley Section 302 certifications | |
| 32.x | Sarbanes-Oxley Section 906 certifications | |
| 99.x | Additional exhibits | Press releases, sometimes additional contracts |

The full sequence (e.g., `10.1`, `10.2`, `10.18`) is filer-assigned within each category. To find the TRA exhibit in an S-1 or 8-K, search the filing's index (`Archives/edgar/data/<CIK>/<accession_no_dashes>/index.json`) for documents whose `description` mentions "Tax Receivable Agreement" or whose `name` matches `*ex10*`. There is no enforced filename convention, so document description and free-text search are required.

## eXtensible Business Reporting Language (XBRL) tagging

XBRL is the structured-data format the SEC requires for the financial statements within 10-K, 10-Q, 8-K (when financial data is included), 20-F, 40-F, and 6-K filings. The format that ships with modern filings is **inline XBRL (iXBRL)**: the same HTML document contains both human-readable text and machine-readable XBRL tags embedded as element attributes.

### Concept, taxonomy, version

A fact in XBRL has:

- A **concept** (a.k.a. tag): e.g., `AccountsPayableCurrent`, `Revenues`, `IncomeLossFromContinuingOperations`.
- A **taxonomy**: the dictionary defining the concept. Common SEC-recognized taxonomies are `us-gaap` (Generally Accepted Accounting Principles), `ifrs-full` (International Financial Reporting Standards), `dei` (Document and Entity Information), `srt` (SEC Reporting Taxonomy). Custom company-specific tags use the filer's accession as the taxonomy identifier.
- A **version**: standard tags carry a vintage like `us-gaap/2024`, denoting the calendar-year release of the GAAP Reporting Taxonomy that defined the tag. EDGAR accepts either the current or previous-year taxonomy; the SEC encourages the current year.

### Context

Every fact attaches to a context that fixes:

- **Reporting entity**: the registrant's CIK.
- **Period**: either a duration (start date, end date), giving income-statement and cash-flow facts, or an instant (single date), giving balance-sheet facts.
- **Unit of measure (UoM)**: `USD`, `shares`, `USD/shares`, etc.
- **Dimensions** (segments): axes that break down a base fact into components (`StatementBusinessSegmentsAxis`, `RangeAxis`, etc.). Facts without dimensions are the "default" (consolidated entity) measurement.

In the project's `2025_11_notes/` Financial Statement Data Sets, these context attributes appear as columns: `ddate` (period end), `qtrs` (0 for instant, 1-4 for durations), `uom` (unit), `dimh` (md5 hash of axis=member pairs; `0x00000000` means no dimensions), `iprx` (priority among duplicates).

### Period grammar in the Frames API

The XBRL Frames endpoint (see [access patterns](access-patterns.md)) addresses a specific period-tag-unit slice using the calendar-year grammar `CY####`, `CY####Q#`, `CY####Q#I`. The `I` suffix is the literal "instantaneous" marker for balance-sheet tags. The Frames API does not address fiscal-year periods; it normalizes to calendar quarters.

### XBRL relevance to TRA work

The TRA-related deferred tax balance shows up tagged under `us-gaap` in the financial statements of post-IPO Up-C filers, commonly as:

- `DeferredTaxLiabilitiesNoncurrent` or `DeferredIncomeTaxLiabilitiesNet` (balance sheet)
- `LiabilitiesUnderTaxReceivableAgreements` (custom or extension tag in some filers)
- Several disclosure-only tags inside the income tax footnote

The project's `2025_11_notes/` data resolves these via `num.tsv` joined to `tag.tsv`. The Company Concept API gives the same information per-firm via the JSON path.

## Cache-key conventions

For client-side caching across EDGAR endpoints, the natural cache keys are:

- **Submissions**: `(cik_padded,)` -> the JSON blob.
- **Company Facts / Company Concept**: `(cik_padded, taxonomy, tag)` -> the JSON blob.
- **Frames**: `(taxonomy, tag, unit, period)` -> the JSON blob.
- **Archives documents**: `(cik, accession_no_dashes, filename)` -> the raw bytes.
- **Text search results**: `(query, forms, startdt, enddt, from)` -> the JSON page.

The project's existing layout under `.tra_history_cache/edgar_submissions/` follows the first key; extend with `edgar_companyfacts/`, `edgar_companyconcept/`, `edgar_frames/`, `edgar_archives/`, `edgar_efts/` subdirectories using the keys above.

## Sources

- EDGAR Application Programming Interfaces (APIs): `https://www.sec.gov/search-filings/edgar-application-programming-interfaces` (SEC; canonical page returned HTTP 403 to WebFetch, summarized from search-result content)
- Accessing EDGAR Data: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data` (SEC)
- Form 8-K (rules and item descriptions): `https://www.sec.gov/files/form8-k.pdf` (SEC); Exchange Act Form 8-K Compliance Disclosure Interpretations: `https://www.sec.gov/rules-regulations/staff-guidance/compliance-disclosure-interpretations/exchange-act-form-8-k`
- Regulation S-K Item 601 (exhibit numbering): `https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.600/section-229.601` (eCFR)
- 2024 XBRL Taxonomies Update: `https://www.sec.gov/newsroom/whats-new/2403-2024-xbrl-taxonomies-update` (SEC)
- US GAAP Architecture Guide: `https://xbrl.us/xbrl-reference/us-gaap-architecture-guide/` (XBRL US)
- "Form 8-K Reference Chart", Fenwick & West: `https://assets.fenwick.com/legacy/FenwickDocuments/Form_8-K_Reference_Chart.pdf`
- Project-internal Financial Statement Data Sets schema documentation: `<project root>/CLAUDE.md` (project repo)
