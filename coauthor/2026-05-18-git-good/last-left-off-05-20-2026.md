# Last left off — 2026-05-20

Handoff note for the `2026-05-18-git-good` project. Scope is limited to the EDGAR
acquisition / classification rework done this session; the broader project state
was not re-verified (see the last section).

Each claim below is tagged `[verified]` (checked this session with a command),
`[reported]` (stated by a subagent, not independently checked), or `[design]`
(a decision or reasoning point, not a measurement).

## Current state

### EDGAR acquisition pipeline — reworked to per-document

The acquisition was changed from one-row-per-filing to one-row-per-matched-EX-10-document.

- `scripts/sec_edgar/search.py`: `_hit_to_row` now also extracts `file_type`; added to `HIT_COLUMNS`. `[verified: grep]`
- `scripts/find_candidates.py`: groups by `(adsh, primary_doc)` instead of `adsh`; filters the output parquet to `file_type` matching `EX-10.*`; added a `--cache-max-age-s` flag. `[verified: grep]`
- `data/edgar-query/full-text.parquet`: 3,025 rows, one per matched EX-10 document; columns include `adsh, primary_doc, ciks, form, file_type, file_date, phrase_variants_matched`. `[verified: polars read]`
- `scripts/pull_exhibits.py`: rewritten to download `primary_doc` directly per row; the `fetch_filing_index` round-trip and EX-10 filename regex were removed. `[verified: grep]`
- `data/edgar-query/exhibits/`: 3,025 documents on disk — 3,019 `.htm`, 3 `.pdf`, 3 `.txt` — plus a fresh `manifest.csv` (3,025 rows). The old 15,035-file broad pull was deleted. `[verified: find]`

### Classify skill — built in `tmp/`, NOT accepted

- `tmp/TRA-classify/`: `SKILL.md` plus `scripts/classify_tras.py`. A pre-filter that drops definite non-TRAs from an exhibit directory and returns a manual-review list.
- Re-run on the 3,025-document set: `tra_droplist.csv` is 595 rows `[verified: csv read]`; `tra_keeplist.csv` is 2,430 rows `[reported by builder coder, not verified]`.
- Treat the 2,430 / 595 split as unvalidated output. Do not feed it downstream as confirmed TRA candidates.

## Open problems with the classify skill

Verified:

- `TRA_PHRASE_RE = tax\s+receivable\s+agreement` matches only the singular forms. `find_candidates.py` queries four search variants, two spelled "tax receivables agreement" (receivables plural). The skill's phrase check cannot match documents found on those two variants. `[verified: grep of both files]`

From an independent coder review (agent `a26bf130fb653b9ab`), not independently re-verified:

- `SKILL.md` headline numbers are stale: it advertises a 15,035-file corpus and 88% reduction; the actual corpus is 3,025 and the committed CSVs show 2,430 kept / 595 dropped, a 20% reduction. `[reported]`
- On the new corpus the pre-filter keeps ~80% of files, because the "phrase present anywhere" keep rule is near-universal in a pull already filtered on that exact phrase, so the filter does little. `[reported]`
- The "zero false drops on a 5-TRA reference set" and "14 of 18 dropped" validation claims are not reproducible from anything in the directory; no reference paths or test harness are committed. `[reported]`
- `SKILL.md` and the script docstring describe a `.htm`-only glob; the code actually globs `.htm/.html/.txt/.pdf`. `[reported]`
- The centered-title parser depends on inline `align`/`style` attributes, so it yields an empty title for `.txt` filings and for HTML centered via CSS classes. `[reported]`
- A stale `scripts/__pycache__/*.pyc` is committed. `[reported]`

Conceptual point (raised by the user):

- Containing the phrase "tax receivable agreement" does not make a document a TRA. LLC agreements, credit agreements, and registration-rights agreements reference TRAs routinely. The skill's "phrase present → keep" rule conflates a mention with the instrument. `[design]`
- The discriminating signal for an actual TRA contract is the centered document title reading "TAX RECEIVABLE AGREEMENT", not phrase presence. `[design]`

## Open decision (undecided)

How should the classify step separate actual TRA contracts from EX-10 documents that merely mention a TRA? Two directions, neither chosen:

1. Fix and recalibrate the classify skill: cover all four phrase variants, scan the whole file rather than a 400 KB window, make the centered title the primary signal.
2. Drop the pre-filter entirely and route all 3,025 documents to the manual confirmation pass or to `tra-process-filings`, which reads full documents.

## Next steps

1. Make the open decision above.
2. If the skill is kept: fix the phrase regex (all four variants) and work through the coder-review findings.
3. Run the manual TRA confirmation pass to produce a list of confirmed-TRA CIKs (exploding the `ciks` list of every confirmed document).
4. Downstream, not started for this rerun: `tra-download-filings` narrowed to 8-K / 10-K / final prospectus plus exhibits for the confirmed-TRA CIKs, then `tra-htm-to-md`, then `tra-process-filings`, then `scripts/build_tra_database.py`, then `scripts/build_dashboard.py`.

## Broader git-good project — state NOT verified this session

The frozen plan is `coauthor/2026-05-18-git-good/ca-02-plan.md`. This session's EDGAR-acquisition rework diverged from it: the parquet is now per-document, `find_candidates.py` and `pull_exhibits.py` were rewritten, and the classification step is a script under `tmp/TRA-classify/` rather than what the plan specifies. `ca-02-plan.md` no longer reflects the built pipeline and should be reconciled.

Project deliverables whose current state was not checked this session: the GitHub push, the skill relocation into `.claude/skills/`, the `tra-refresh` skill, and whether `README.md` matches the reworked pipeline (it currently describes the old per-filing pull and the retired `tra-packet` skill). A future session should verify each against the working tree rather than trusting this note.
