# TRA database schema

Three Parquet files compiled by `scripts/build_tra_database.py` from the
per-firm `*_summary.qmd` files under `TRA-contracts/`. The build script reads
each summary's YAML frontmatter and its `## TRA Timeline` bullets, normalizes
list-valued fields by joining with `|`, derives a stable `tra_id` from the
filename, and writes the three files into this directory. A fourth derived
view, `stock_by_date.parquet`, is computed from the TRA-level table for the
dashboard.

Last build inputs: 360 summary files across 321 firm directories (some firms
carry multiple parallel TRAs). Run from the project root with
`pixi run -- python scripts/build_tra_database.py`.

## File 1: `tras.parquet` (one row per TRA)

| Column | Type | Description |
|---|---|---|
| `firm_slug` | string | Directory name under `TRA-contracts/`, of the form `<firm-name-lowercase-hyphenated>_<10-digit-CIK>`. The trailing CIK is the firm's primary CIK as filed with SEC EDGAR. |
| `cik` | string | The primary CIK extracted from the trailing `_<10-digit>` suffix of `firm_slug`. Always present; preserved as a string to keep leading zeros. |
| `tra_id` | string | Stable identifier within a firm. For single-TRA firms the build script synthesizes `TRA-<creation-date>`; for multi-TRA firms the id is taken from the `_TRA-<date>[-<diff>]_summary.qmd` filename pattern. Used in `parallel_tras` to cross-reference related agreements at the same firm. |
| `summary_path` | string | Path to the source `summary.qmd`, relative to the project root. |
| `title` | string | Human-readable title from `title:` in the summary frontmatter. |
| `company_names` | string | Pipe-joined list (`|`) of legal entity names involved in the TRA, from `company-names:`. May include the PubCo, the operating LLC, and successor / acquirer entities. |
| `ciks` | string | Pipe-joined list of all CIKs associated with the TRA, from `CIKs:`. The first entry is typically the primary CIK in `cik`. |
| `status` | enum | One of `Ongoing`, `Terminated`, `Unknown`. Reflects the TRA's most recent known state in the source filings; `Unknown` covers cases where the TRA disappears from disclosures without an explicit termination event. Distinct from the as-of-date status the dashboard computes. |
| `creation_date` | ISO date | Execution date of the original TRA (`YYYY-MM-DD`), from `creation-date:`. Always present in the current corpus. |
| `termination_date` | ISO date or blank | Termination date when known. Set only when `status = Terminated` and a specific date is identifiable in the filings; otherwise blank. |
| `last_event_date` | ISO date or blank | Date of the most recent entry in the timeline, derived at build time from `events.parquet`. Used by the dashboard to bound the "Ongoing" window for `status = Unknown` TRAs (a TRA with unknown ultimate fate is treated as Ongoing up to and including this date). |
| `tax_asset_types` | string | Pipe-joined list of tax-asset categories the TRA shares benefits from, from `tax-asset-type:`. Common values: `Basis Step-Up`, `NOL`, `Section 743(b)`, `Section 704(c)`. Multi-valued: a TRA may share more than one type. |
| `sharing_ratio` | string | The percentage of cash tax savings owed to the TRA counterparty, as it appears in the source filing (e.g. `85%`, `65%`, or a textual description when the ratio is not a single number). Stored as a string to preserve the original phrasing. |
| `parallel_tras` | string | Pipe-joined list of `tra_id` values for other TRAs at the same firm executed contemporaneously or as part of the same structure (e.g. a Basis Step-Up TRA and a separate NOL TRA at the same IPO). Empty for single-TRA firms. |
| `role` | enum | The firm's role relative to the TRA. One of `PubCo` (the public company that pays the TRA, the default case), `Beneficiary` (firm receives TRA payments), `Acquirer` (firm acquired a TRA via M&A), `Financing-arm` (TRA assigned to a financing vehicle). |
| `trigger_event_type` | enum | The corporate event that created the TRA. Top values: `IPO` (211), `SPAC business combination` (101), `Spin-off`, `Merger`, `Up-C transition`, `JV formation`, `Asset purchase`, `Plan of reorganization`, `Section 162 issuance`, `Other`. |
| `counterparty_type` | enum | The category of party receiving TRA payments. Values: `pre-IPO holders`, `M&A sellers`, `founder vehicle`, `named individual`, `plan-of-reorganization trustee`, `Other`. |
| `notes` | string | Free-text notes from `notes:` in the summary frontmatter. Used for qualifications, related side-agreements, or evidence gaps. |

## File 2: `events.parquet` (one row per timeline bullet)

Drawn from the `## TRA Timeline` section of each summary file. Bullets within
that section are grouped under `####` subheadings (event groups); each
`- YYYY-MM-DD: description` bullet produces one row.

| Column | Type | Description |
|---|---|---|
| `firm_slug` | string | Same as in `tras.parquet`. |
| `cik` | string | Same as in `tras.parquet`. |
| `tra_id` | string | Foreign key to `tras.parquet`. |
| `summary_path` | string | Source `summary.qmd` path relative to the project root. |
| `date` | ISO date | Event date as written in the bullet. The build script accepts only `YYYY-MM-DD`; bullets with a trailing `?` (uncertain date) or a non-ISO format are not parsed. |
| `event_group` | string | The `####` subheading the bullet appears under in the source file (e.g. `Up-C reverse takeover and TRA execution`, `Third Amendment and Canopy USA assignment`). Used by the dashboard's per-TRA timeline view to bucket events into horizontal lanes. |
| `description` | string | Bullet text after the date and colon. |

## File 3: `stock_by_date.parquet` (one row per date × dimension × group value)

A long-format derived view of how many TRAs are active at each month-start
date, broken down by six grouping dimensions. Built by
`build_stock_by_date()` from the `tras.parquet` rows in the same script run.

| Column | Type | Description |
|---|---|---|
| `date` | ISO date | First day of each month from the earliest `creation_date` in the corpus through the current month. |
| `dimension` | enum | One of `trigger_event_type`, `counterparty_type`, `role`, `status`, `tax_asset_types`, `vintage_year`. Selects which column from `tras.parquet` is being grouped. |
| `group_value` | string | A category within `dimension`. For `tax_asset_types`, multi-valued TRAs are exploded on `|` and counted in each band. For `vintage_year`, the four-digit year of `creation_date`. For all other dimensions, the raw value from `tras.parquet` (blank values are mapped to `(unknown)`). |
| `count` | int | Number of TRAs active at `date` falling in this `(dimension, group_value)` bucket. |
| `rank` | int | Stable stacking order within a dimension. For `vintage_year`, the rank is chronological (`2004 = 2004`, `2026 = 2026`) so the dashboard's time-evolution chart reads as cohorts laid down over time. For all other dimensions, the rank is by total count descending, so the largest band sits at the bottom of the stack and the smallest categories on top. |

### Active-as-of-date rule

A TRA is "active" at date $D$ when

$$
\text{creation\_date} \le D
\quad\text{and}\quad
(\text{termination\_date is blank} \;\;\text{or}\;\; \text{termination\_date} > D).
$$

A TRA terminated on date $T$ is counted as active through $T - 1$ and not on $T$
or later. This rule produces the `count` column. The dashboard's per-row
status display layers a second rule on top (see next section).

## Dashboard as-of-date status semantics

The dashboard's status table uses a four-way classification, not the raw
`status` column, because `status` is the eventual fate while the user is
asking "what was the state of this TRA on date $D$?"

Let $C$ = `creation_date`, $T$ = `termination_date`, $L$ = `last_event_date`,
and $s$ = the raw `status` column. The dashboard rule (in
`dashboard.template.html`, function `statusAsOf`) is:

1. If $C$ is missing or $C > D$: **Not yet created** (excluded from the table at date $D$).
2. Else if $T$ is present: **Terminated** when $T \le D$, **Ongoing** when $T > D$.
3. Else if $s = \text{Terminated}$ (termination occurred but no specific date in the filings): **Unknown** at all dates $\ge C$.
4. Else if $s = \text{Unknown}$: **Ongoing** when $D \le L$ (we have evidence the TRA was alive on the last event date), **Unknown** when $D > L$.
5. Otherwise ($s = \text{Ongoing}$): **Ongoing**.

This is why the dashboard can distinguish "Ongoing at Jan 2015" (DreamWorks
and HFF, both `status = Unknown` but with timeline activity past that date)
from "Unknown at Jan 2026" (same TRAs, but past their last known event).

## Conventions

- **Pipe-delimited fields.** `company_names`, `ciks`, `tax_asset_types`, and `parallel_tras` are pipe-joined (`|`) strings. Empty when the underlying YAML list is empty or missing.
- **Blank versus null.** All blank cells are written as empty strings. The Parquet files do not use a sentinel like `NA` or `NULL`.
- **CIKs as strings.** Both `cik` and `ciks` are strings to preserve leading zeros. Parquet stores dtype natively, so `pl.read_parquet("tras.parquet")` returns these as `pl.String` without any schema-override argument.
- **Dates as ISO strings.** All dates are ISO `YYYY-MM-DD` strings, not date types. This includes the `date` column in `stock_by_date.parquet`, which is cast to string at build time for consistency with `creation_date`, `termination_date`, and the `events.parquet` `date` column. Cast with `pl.col("creation_date").str.to_date(strict=False)` when a date type is needed.
- **`tra_id` is firm-local.** The pair `(firm_slug, tra_id)` is the cross-file primary key. `tra_id` alone is not unique across the corpus.

## Known data issues

- One row has `status = Terminated` but blank `termination_date`: `paperweight-development-corp_0001031296`, `TRA-2012-05-16`. The termination event is documented in the underlying contract log but a specific termination date was not isolatable from the filings.
- 60 TRAs have `status = Unknown`. These are agreements that disappear from disclosures (deregistration, going private, acquisition closing without explicit TRA disposition) without an explicit termination event in the available filings.
- The corpus is not closed under M&A: a TRA assigned from PubCo $A$ to acquirer $B$ may appear in $A$'s directory under its original terms and again in $B$'s directory under the assignment. `role` partially disambiguates this; full lineage requires reading the underlying contract log.

## Regenerating

```
pixi run -- python scripts/build_tra_database.py
```

writes `tras.parquet`, `events.parquet`, and `stock_by_date.parquet` into
`outputs/tra-database/`. The dashboard is rebuilt separately with
`pixi run -- python scripts/build_dashboard.py`, which reads the three parquet
files and substitutes them into `dashboard.template.html` to produce
`dashboard.html`.
