#!/usr/bin/env python3
"""tra-classify — three-way deterministic classifier for SEC EX-10.* documents.

See `.claude/skills/tra-classify/SKILL.md` for the full skill contract and
`.claude/skills/tra-classify/references/signal-catalog.md` for the per-version
signal definitions and classification rule.

This file implements `--mode classify` (U5). The `--mode review-uncertain` (U6)
and `--mode finalize` (U7) modes are stubbed and raise NotImplementedError.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import polars as pl

# Random seed per project convention (date-derived, not 42).
SEED = int(date.today().strftime("%Y%m%d"))

# --- bounded read windows (WSL safety) -----------------------------------
TITLE_WINDOW_BYTES = 80_000  # leading slice scanned for the centered-title detector
SCAN_WINDOW_BYTES = 400_000  # leading slice scanned for phrase + defined-term signals

# --- output schema -------------------------------------------------------
OUTPUT_COLUMNS = [
    "cik",
    "accession",
    "filename",
    "classification",
    "classifier_version",
    "signals_matched",
    "needs_a1_review",
    "escalation_reason",
    "reviewer_verdict",
    "reviewer_rationale",
]

# --- v1 signals ----------------------------------------------------------

# S2: four phrase variants (singular + plural × receivable + receivables).
PHRASE_VARIANTS = [
    re.compile(r"tax\s+receivable\s+agreement", re.IGNORECASE),
    re.compile(r"tax\s+receivable\s+agreements", re.IGNORECASE),
    re.compile(r"tax\s+receivables\s+agreement", re.IGNORECASE),
    re.compile(r"tax\s+receivables\s+agreements", re.IGNORECASE),
]

# S1: centered-title detector. Both inline-style and CSS-class centering.
# Inline: <p align="center">...</p>, <div style="text-align: center">...</div>,
#         <center>...</center>, <h1 style="...text-align:center..."> etc.
# CSS class: <p class="centered">...</p> where <style> defines .centered
#            with text-align:center.
TITLE_PHRASE_RE = re.compile(r"tax\s+receivable\s+agreement", re.IGNORECASE)

# Inline-centering wrappers — heuristic: any tag with align="center" or
# style containing text-align:center, OR <center> wrapper.
INLINE_CENTER_RE = re.compile(
    r"""(?:
        <center[^>]*>(?:(?!</center>).)*?TAX\s+RECEIVABLE\s+AGREEMENT(?:(?!</center>).)*?</center>
        |
        <(?:p|div|h\d|span)[^>]*?(?:align\s*=\s*["']?center|style\s*=\s*["'][^"']*text-align\s*:\s*center)[^>]*?>
            (?:(?!</(?:p|div|h\d|span)>).)*?TAX\s+RECEIVABLE\s+AGREEMENT(?:(?!</(?:p|div|h\d|span)>).)*?
        </(?:p|div|h\d|span)>
    )""",
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# CSS-class centering: detect <style>...text-align:center...</style> sections,
# extract class names that center, then check whether the title phrase appears
# in any tag carrying one of those classes.
CSS_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
CSS_CENTERING_CLASS_RE = re.compile(
    r"\.([a-z][\w-]*)\s*\{[^}]*text-align\s*:\s*center[^}]*\}",
    re.IGNORECASE,
)

# S3: defined-term signals — each named individually so signals_matched
# can carry the specific term that fired.
DEFINED_TERM_SIGNALS = {
    "defined_term_realized_tax_benefit": re.compile(r"realized\s+tax\s+benefit", re.IGNORECASE),
    "defined_term_hypothetical_tax_liability": re.compile(r"hypothetical\s+tax\s+liability", re.IGNORECASE),
    "defined_term_exchange_basis": re.compile(r"exchange\s+basis\s+(?:schedule|adjustment)", re.IGNORECASE),
    "defined_term_tax_benefit_schedule": re.compile(r"tax\s+benefit\s+schedule", re.IGNORECASE),
    "defined_term_early_termination_payment": re.compile(r"early\s+termination\s+payment", re.IGNORECASE),
    "defined_term_net_tax_benefit_payment": re.compile(r"net\s+tax\s+benefit\s+payment", re.IGNORECASE),
    "defined_term_basis_adjustment": re.compile(r"basis\s+adjustment", re.IGNORECASE),
    "defined_term_tax_asset": re.compile(r"tax\s+asset(?:s)?\b", re.IGNORECASE),
    "defined_term_section_754": re.compile(r"section\s+754\s+election", re.IGNORECASE),
}


@dataclass
class ScanResult:
    """The signals matched by one document's bounded reads."""

    centered_title: bool = False
    phrase: bool = False
    defined_terms: list[str] = field(default_factory=list)


def detect_centered_title(title_text: str) -> bool:
    """True iff the title window contains a centered 'TAX RECEIVABLE AGREEMENT'.

    Handles both inline-style centering (align="center", style="text-align:center",
    <center> tags) and CSS-class centering (a class defined as text-align:center
    in an in-document <style> block, applied to a tag containing the title phrase).

    Returns False if the phrase is not centered (or not present at all).
    """
    # Quick early-out: if the title phrase isn't anywhere in the window, no centering.
    if not TITLE_PHRASE_RE.search(title_text):
        return False

    # Path 1: inline centering wrappers.
    if INLINE_CENTER_RE.search(title_text):
        return True

    # Path 2: CSS-class centering. Find the set of class names declared
    # text-align:center in any <style> block, then check whether any tag
    # carrying one of those classes contains the title phrase.
    centering_classes: set[str] = set()
    for style_block in CSS_STYLE_BLOCK_RE.findall(title_text):
        centering_classes.update(
            m.group(1).lower() for m in CSS_CENTERING_CLASS_RE.finditer(style_block)
        )

    if not centering_classes:
        return False

    # Build a per-class regex once and check for title-phrase-containing tags.
    for cls in centering_classes:
        class_tag_re = re.compile(
            rf'<(?:p|div|h\d|span)[^>]*?class\s*=\s*["\'][^"\']*\b{re.escape(cls)}\b[^"\']*["\'][^>]*?>'
            r"(?:(?!</(?:p|div|h\d|span)>).)*?TAX\s+RECEIVABLE\s+AGREEMENT"
            r"(?:(?!</(?:p|div|h\d|span)>).)*?</(?:p|div|h\d|span)>",
            re.IGNORECASE | re.DOTALL,
        )
        if class_tag_re.search(title_text):
            return True

    return False


def scan_document(path: Path) -> ScanResult:
    """Read the bounded title + scan windows from `path` and score signals.

    PDF files are not handled here — they short-circuit to `uncertain` upstream.
    """
    result = ScanResult()

    # Read the title window first; reuse it as the prefix of the scan window
    # since the windows overlap entirely (title ⊂ scan).
    try:
        with path.open("rb") as f:
            scan_bytes = f.read(SCAN_WINDOW_BYTES)
    except OSError as e:
        raise RuntimeError(f"failed to read {path}: {e}") from e

    # Decode tolerantly (SEC HTML carries inconsistent encodings).
    scan_text = scan_bytes.decode("utf-8", errors="replace")
    title_text = scan_text[:TITLE_WINDOW_BYTES]

    # S1: centered title.
    result.centered_title = detect_centered_title(title_text)

    # S2: any of the four phrase variants in the scan window.
    result.phrase = any(p.search(scan_text) for p in PHRASE_VARIANTS)

    # S3: defined-term signals.
    for signal_name, regex in DEFINED_TERM_SIGNALS.items():
        if regex.search(scan_text):
            result.defined_terms.append(signal_name)

    return result


def classify_signals(
    scan: ScanResult,
    is_pdf: bool,
    is_forced_uncertain: bool,
) -> tuple[str, str]:
    """Apply the v1 classification rule. Returns (classification, signals_matched).

    Rule order (first match wins):
    1. forced_uncertain → uncertain
    2. PDF → uncertain (no text extraction)
    3. centered_title → yes
    4. phrase + at least one defined_term → yes
    5. phrase alone → uncertain
    6. nothing matched → no
    """
    if is_forced_uncertain:
        return "uncertain", "forced_uncertain"

    if is_pdf:
        return "uncertain", "pdf_no_text"

    # Build the signals_matched list in catalog order for stable output.
    matched = []
    if scan.centered_title:
        matched.append("centered_title")
    if scan.phrase:
        matched.append("phrase")
    matched.extend(scan.defined_terms)
    signals_str = "|".join(matched)

    if scan.centered_title:
        return "yes", signals_str
    if scan.phrase and scan.defined_terms:
        return "yes", signals_str
    if scan.phrase:
        return "uncertain", signals_str
    return "no", ""


def load_forced_uncertain(path: Path) -> set[tuple[str, str, str]]:
    """Load (cik, accession, filename) tuples from forced_uncertain.csv."""
    if not path.exists():
        raise FileNotFoundError(
            f"forced_uncertain CSV not found at {path}; create an empty "
            f"header-only file with: echo 'cik,accession,filename,reason' > {path}"
        )

    df = pl.read_csv(path)
    required = {"cik", "accession", "filename", "reason"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"forced_uncertain CSV at {path} missing required columns: {missing}"
        )

    return {
        (row["cik"], row["accession"], row["filename"])
        for row in df.iter_rows(named=True)
    }


def load_manifest(path: Path) -> pl.DataFrame:
    """Load the manifest from pull_exhibits.py. Required columns: cik, accession,
    filename, filing_date, form, phrase_variants_matched.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"manifest not found at {path}; run scripts/pull_exhibits.py first"
        )
    df = pl.read_csv(path, schema_overrides={"cik": pl.String})
    # The manifest's CIK should be 10-digit zero-padded; if it isn't, pad here.
    df = df.with_columns(pl.col("cik").str.zfill(10).alias("cik"))
    return df


def load_resume_state(output_csv: Path) -> set[tuple[str, str, str]]:
    """Return the set of (cik, accession, filename) tuples already in output_csv,
    so we can skip them on resume.
    """
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        return set()
    df = pl.read_csv(output_csv, schema_overrides={"cik": pl.String})
    return {
        (row["cik"], row["accession"], row["filename"])
        for row in df.iter_rows(named=True)
    }


def write_header_if_new(output_csv: Path) -> None:
    """Write the header row if output_csv does not exist yet."""
    if output_csv.exists() and output_csv.stat().st_size > 0:
        return
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(OUTPUT_COLUMNS)


def append_row(output_csv: Path, row: dict[str, object]) -> None:
    """Append one row to output_csv. Caller guarantees the header exists."""
    with output_csv.open("a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in OUTPUT_COLUMNS])


def discover_documents(input_dir: Path) -> list[Path]:
    """Enumerate documents under input_dir.

    pull_exhibits.py writes files as `<input_dir>/<CIK>/<accession>_<filename>`,
    flattened one directory per CIK. We support both .htm/.html/.txt/.pdf.
    """
    exts = ("*.htm", "*.html", "*.txt", "*.pdf")
    files = sorted(p for ext in exts for p in input_dir.rglob(ext))
    return files


def resolve_manifest_row(
    file_path: Path,
    input_dir: Path,
    manifest_lookup: dict[tuple[str, str, str], None],
) -> tuple[str, str, str]:
    """Map an on-disk file path to its (cik, accession, filename) per the manifest.

    pull_exhibits.py names files `<input_dir>/<CIK>/<accession>_<filename>`. We
    parse CIK from the parent dir and split accession / filename on the first
    underscore that follows the accession-numbered prefix.
    """
    try:
        rel = file_path.relative_to(input_dir)
    except ValueError as e:
        raise RuntimeError(
            f"file {file_path} is not under input_dir {input_dir}"
        ) from e

    parts = rel.parts
    if len(parts) < 2:
        raise RuntimeError(
            f"file {file_path} not in expected <CIK>/<accession>_<filename> layout"
        )

    cik = parts[0].zfill(10)
    leaf = parts[-1]

    # The accession number is the leading "NNNNNNNNNN-NN-NNNNNN" prefix.
    # Split it off; everything after the first '_' is the filename.
    accession_match = re.match(r"(\d{10}-\d{2}-\d{6})_(.+)", leaf)
    if not accession_match:
        raise RuntimeError(
            f"file {file_path} leaf name does not match "
            f"<accession>_<filename> pattern: {leaf}"
        )
    accession = accession_match.group(1)
    filename = accession_match.group(2)

    key = (cik, accession, filename)
    if key not in manifest_lookup:
        raise RuntimeError(
            f"manifest row not found for {key} (file: {file_path}); manifest "
            f"may be stale — re-run scripts/pull_exhibits.py"
        )

    return key


def run_classify_mode(args: argparse.Namespace) -> int:
    """Implementation of --mode classify."""
    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)
    forced_uncertain_path = Path(args.forced_uncertain)
    manifest_path = Path(args.manifest)
    classifier_version = args.classifier_version

    if not input_dir.is_dir():
        sys.exit(f"input_dir not a directory: {input_dir}")

    forced_uncertain = load_forced_uncertain(forced_uncertain_path)
    manifest = load_manifest(manifest_path)
    manifest_lookup = {
        (row["cik"], row["accession"], row["filename"]): None
        for row in manifest.iter_rows(named=True)
    }

    files = discover_documents(input_dir)
    if not files:
        sys.exit(f"no .htm/.html/.txt/.pdf documents under {input_dir}")

    already_done = load_resume_state(output_csv)
    if already_done:
        print(
            f"resume: {len(already_done)} rows already in {output_csv}; "
            f"skipping those documents"
        )

    write_header_if_new(output_csv)

    # Counters for end-of-run summary.
    n_yes = n_no = n_uncertain = n_skipped = 0
    n_error = 0

    for path in files:
        try:
            key = resolve_manifest_row(path, input_dir, manifest_lookup)
        except RuntimeError as e:
            # Failing loudly per the project rule.
            print(f"ERROR resolving {path}: {e}", file=sys.stderr)
            n_error += 1
            continue

        cik, accession, filename = key

        if key in already_done:
            n_skipped += 1
            continue

        is_forced = key in forced_uncertain
        is_pdf = path.suffix.lower() == ".pdf"

        if is_pdf or is_forced:
            classification, signals_matched = classify_signals(
                ScanResult(), is_pdf=is_pdf, is_forced_uncertain=is_forced
            )
        else:
            scan = scan_document(path)
            classification, signals_matched = classify_signals(
                scan, is_pdf=False, is_forced_uncertain=False
            )

        row = {
            "cik": cik,
            "accession": accession,
            "filename": filename,
            "classification": classification,
            "classifier_version": classifier_version,
            "signals_matched": signals_matched,
            "needs_a1_review": "",
            "escalation_reason": "",
            "reviewer_verdict": "",
            "reviewer_rationale": "",
        }
        append_row(output_csv, row)

        if classification == "yes":
            n_yes += 1
        elif classification == "no":
            n_no += 1
        else:
            n_uncertain += 1

    total_processed = n_yes + n_no + n_uncertain
    print()
    print(f"input directory   : {input_dir}")
    print(f"output CSV        : {output_csv}")
    print(f"classifier_version: {classifier_version}")
    print(f"forced_uncertain  : {len(forced_uncertain)} entries")
    print(f"documents found   : {len(files)}")
    print(f"resumed (skipped) : {n_skipped}")
    print(f"errors            : {n_error}")
    print(f"newly processed   : {total_processed}")
    print(f"  yes             : {n_yes} ({n_yes / max(total_processed, 1):.1%})")
    print(f"  uncertain       : {n_uncertain} ({n_uncertain / max(total_processed, 1):.1%})")
    print(f"  no              : {n_no} ({n_no / max(total_processed, 1):.1%})")

    return 1 if n_error else 0


def run_review_uncertain_mode(args: argparse.Namespace) -> int:
    """Stub — implemented in U6 (A4 reviewer subagent + cache driver)."""
    raise NotImplementedError(
        "--mode review-uncertain is implemented in U6 (next implementation unit). "
        "Use --mode classify in the current build."
    )


def run_finalize_mode(args: argparse.Namespace) -> int:
    """Stub — implemented in U7 (iteration mechanics + acceptance tracking)."""
    raise NotImplementedError(
        "--mode finalize is implemented in U7 (next-next implementation unit). "
        "Use --mode classify in the current build."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="tra-classify: three-way deterministic classifier for SEC EX-10.* documents"
    )
    parser.add_argument(
        "--mode",
        choices=["classify", "review-uncertain", "finalize"],
        default="classify",
        help="Subcommand to run (default: classify)",
    )
    parser.add_argument(
        "--input-dir",
        default="data/edgar-query/exhibits/",
        help="Directory of EX-10 documents (default: data/edgar-query/exhibits/)",
    )
    parser.add_argument(
        "--output-csv",
        required=True,
        help="Where to write classifications (e.g., data/edgar-query/classifications-v1.csv)",
    )
    parser.add_argument(
        "--classifier-version",
        type=int,
        help="Iteration number. Required for --mode classify and --mode review-uncertain. "
        "For --mode finalize, auto-resolved from classifier_acceptance.md when omitted.",
    )
    parser.add_argument(
        "--forced-uncertain",
        default="data/edgar-query/forced_uncertain.csv",
        help="CSV of (cik, accession, filename, reason) override entries (default: data/edgar-query/forced_uncertain.csv)",
    )
    parser.add_argument(
        "--manifest",
        default="data/edgar-query/exhibits/manifest.csv",
        help="Manifest written by pull_exhibits.py (default: data/edgar-query/exhibits/manifest.csv)",
    )
    parser.add_argument(
        "--cache-csv",
        default="data/edgar-query/a4_verdicts_cache.csv",
        help="A4 verdict cache (used by --mode review-uncertain; default: data/edgar-query/a4_verdicts_cache.csv)",
    )

    args = parser.parse_args()

    # Mode-specific required-arg validation.
    if args.mode in ("classify", "review-uncertain") and args.classifier_version is None:
        parser.error(f"--mode {args.mode} requires --classifier-version")

    if args.mode == "classify":
        return run_classify_mode(args)
    if args.mode == "review-uncertain":
        return run_review_uncertain_mode(args)
    if args.mode == "finalize":
        return run_finalize_mode(args)

    parser.error(f"unknown mode: {args.mode}")
    return 2  # unreachable but satisfies type checkers


if __name__ == "__main__":
    raise SystemExit(main())
