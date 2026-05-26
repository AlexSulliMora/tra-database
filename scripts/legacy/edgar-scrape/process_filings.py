#!/usr/bin/env python3
"""
Process Vince Holding Corp filings to identify TRA contracts, classify them,
and produce contract_log.md and filing_notes.md.

Execution: python process_filings.py /path/to/firm_dir
"""

import sys
import os
import re
from pathlib import Path
from html.parser import HTMLParser
from collections import defaultdict
from datetime import datetime

# Simple HTML stripper
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_text(self):
        return ''.join(self.text)

def strip_html(html_content):
    """Strip HTML to plain text."""
    stripper = HTMLStripper()
    try:
        stripper.feed(html_content)
        return stripper.get_text()
    except Exception as e:
        return html_content

def extract_accession_and_date(file_path):
    """Extract accession number and infer date from path."""
    parts = file_path.parts
    for part in parts:
        if re.match(r'^\d{10}-\d{2}-\d{6}$', part):
            accession = part
            # Parse accession: 0001193125-13-457161 -> 2013-11-13 (approx)
            # First 10 digits are CIK, next 2 are year, rest is sequence
            year = int(accession[10:12])
            if year > 70:
                year += 1900
            else:
                year += 2000
            return accession, year
    return None, None

def is_tra_contract(text):
    """
    Determine if document is a Tax Receivable Agreement contract.

    A true TRA contract has these markers:
    - Preamble: "This Tax Receivable Agreement" anywhere in the document
    - AND substantive TRA article/section structure
    - AND is substantial in length

    Reject if the document is primarily a Form (S-1, 10-K, etc.) that is NOT an exhibit.
    """
    text_upper = text.upper()

    # PRIMARY FILTER: Is this a main SEC form/report document (not an exhibit)?
    # Forms that contain TRA disclosures but are not the contract itself
    form_indicators = [
        r'FORM\s+10-K\b',
        r'FORM\s+10-Q\b',
        r'FORM\s+8-K\b',
        r'FORM\s+DEF\s*14A\b',
    ]

    # Check if this is a main form (not an exhibit)
    for indicator in form_indicators:
        if re.search(indicator, text_upper):
            # This is a main form. It's not a TRA contract (just discusses it)
            return False

    # S-1 and prospectuses are only OK if they explicitly have an exhibit marker
    if re.search(r'FORM\s+S-1\b|REGISTRATION STATEMENT|PROSPECTUS', text_upper):
        if not re.search(r'EXHIBIT|EX-\d|EX\d', text_upper[:1000]):
            return False

    # PRIMARY POSITIVE: Document preamble
    # Must have the actual TRA preamble: "This Tax Receivable Agreement"
    if not re.search(r'THIS\s+TAX\s+RECEIVABLE\s+AGREEMENT', text_upper):
        return False

    # SECONDARY POSITIVE: Document structure
    # Must have actual TRA article structure (ARTICLE I, ARTICLE II, etc.)
    if not re.search(r'ARTICLE\s+[IVX]+', text_upper):
        return False

    # Length check: a real TRA is substantial
    if len(text) < 1000:
        return False

    return True

def classify_tra_document(text):
    """
    Classify a TRA document as: original, amended, restatement, termination, or other.
    Returns (classification, note)
    """
    text_upper = text.upper()

    # Check for termination first
    if re.search(r'TERMINATION.*TAX RECEIVABLE AGREEMENT|NOTICE OF TERMINATION', text_upper):
        return 'termination', 'Standalone termination document or amendment terminating the agreement'

    # Check for "Amended and Restated"
    if re.search(r'AMENDED\s+AND\s+RESTATED\s+TAX\s+RECEIVABLE\s+AGREEMENT', text_upper):
        return 'amended_and_restated', 'Wholesale restatement of the agreement'

    # Check for numbered amendments
    match = re.search(r'(?:FIRST|SECOND|THIRD|FOURTH|FIFTH)\s+AMENDMENT\s+TO\s+(?:.*?\s+)?TAX RECEIVABLE AGREEMENT', text_upper)
    if match:
        return 'amendment_numbered', 'Numbered amendment to prior agreement'

    # Check for "Amendment No. X"
    match = re.search(r'AMENDMENT\s+NO\.\s+(\d+)\s+TO', text_upper)
    if match:
        num = match.group(1)
        return f'amendment_{num}', f'Amendment No. {num} to a prior agreement'

    # Check for unnumbered amendments
    if re.search(r'AMENDMENT\s+TO\s+(?:.*?\s+)?TAX RECEIVABLE AGREEMENT', text_upper):
        return 'amendment_unnumbered', 'Amendment to a prior agreement'

    # Otherwise, classify as original
    return 'original', 'Original Tax Receivable Agreement'

def extract_preamble_date(text):
    """
    Try to extract the preamble date: "This Tax Receivable Agreement, dated as of [date]"
    """
    pattern = r'THIS TAX RECEIVABLE AGREEMENT[,\s]+DATED\s+AS OF\s+([A-Z][A-Za-z]+\s+\d{1,2},\s+\d{4}|[A-Z][A-Za-z]+\s+\d{1,2}\s+\d{4}|\d{1,2}\s+[A-Z][A-Za-z]+\s+\d{4})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def is_executed(text):
    """Check if document appears to be executed (has signatures)."""
    # Look for signature blocks or "IN WITNESS WHEREOF"
    return bool(re.search(r'IN WITNESS WHEREOF|SIGNATURE PAGE|SIGNED|EXECUTED', text, re.IGNORECASE))

def process_firm_directory(firm_dir):
    """
    Process all documents in the firm directory.
    """
    firm_path = Path(firm_dir)
    if not firm_path.exists():
        print(f"Error: {firm_dir} does not exist")
        sys.exit(1)

    # Collect all files
    all_files = []
    for root, dirs, files in os.walk(firm_path):
        for file in files:
            if file.endswith('.htm') or file.endswith('.txt'):
                filepath = Path(root) / file
                all_files.append(filepath)

    print(f"Found {len(all_files)} documents across {len(set(p.parent.name for p in all_files))} accessions")

    # Process documents
    tra_documents = []
    filing_map = defaultdict(list)  # accession -> list of (filepath, classification, is_tra)

    for filepath in sorted(all_files):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            text = strip_html(content)
            is_tra = is_tra_contract(text)

            accession, year = extract_accession_and_date(filepath)

            if accession:
                filing_map[accession].append({
                    'filepath': filepath,
                    'is_tra': is_tra,
                    'text': text,
                    'year': year,
                })

                if is_tra:
                    classification, note = classify_tra_document(text)
                    preamble_date = extract_preamble_date(text)
                    executed = is_executed(text)

                    tra_documents.append({
                        'accession': accession,
                        'filepath': filepath,
                        'filename': filepath.name,
                        'classification': classification,
                        'note': note,
                        'preamble_date': preamble_date,
                        'executed': executed,
                        'year': year,
                        'text': text,
                    })
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            continue

    return all_files, tra_documents, filing_map

def generate_contract_log(tra_documents):
    """Generate contract_log.md content."""
    lines = [
        "# Contract Log",
        "",
        "## Identified TRA Contracts",
        "",
    ]

    # Group by classification
    by_class = defaultdict(list)
    for doc in tra_documents:
        by_class[doc['classification']].append(doc)

    # Original documents first
    for classification in sorted(by_class.keys()):
        docs = by_class[classification]
        lines.append(f"### {classification.replace('_', ' ').title()} ({len(docs)} document(s))")
        lines.append("")

        for doc in sorted(docs, key=lambda x: (x['accession'], x['filename'])):
            lines.append(f"**Accession**: {doc['accession']}")
            lines.append(f"**Document**: {doc['filename']}")
            lines.append(f"**Status**: {'Executed' if doc['executed'] else 'Unexecuted'}")
            lines.append(f"**Preamble Date**: {doc['preamble_date'] or 'Not found (blank)'}")
            lines.append(f"**Note**: {doc['note']}")
            lines.append("")

    return "\n".join(lines)

def generate_filing_notes(all_files, filing_map, tra_documents):
    """Generate filing_notes.md content."""
    lines = [
        "# Filing Notes",
        "",
        "## Per-Filing Annotations",
        "",
    ]

    # Build a set of TRA-bearing accessions
    tra_accessions = set(doc['accession'] for doc in tra_documents)

    # Sort by accession
    for accession in sorted(filing_map.keys()):
        docs_in_filing = filing_map[accession]
        has_tra = accession in tra_accessions
        tra_docs = [d for d in docs_in_filing if d['is_tra']]

        # Infer form type and date from accession
        accession_date = docs_in_filing[0]['year'] if docs_in_filing else '?'

        lines.append(f"### {accession}")
        lines.append(f"**Date (inferred)**: {accession_date}")
        lines.append(f"**TRA documents in accession**: {len(tra_docs)}")

        if has_tra:
            for doc in tra_docs:
                lines.append(f"  - {doc['filepath'].name}: {[d['classification'] for d in tra_documents if d['filepath'] == doc['filepath']][0]}")
            lines.append("**Annotation**: Contains TRA contract(s). See contract_log.md for details.")
        else:
            lines.append("**Annotation**: No TRA contract documents identified. Standard periodic or prospectus disclosures.")

        lines.append("")

    return "\n".join(lines)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python process_filings.py <firm_dir>")
        sys.exit(1)

    firm_dir = sys.argv[1]

    print(f"Processing {firm_dir}...")
    all_files, tra_documents, filing_map = process_firm_directory(firm_dir)

    print(f"Identified {len(tra_documents)} TRA contract documents")

    # Generate outputs
    contract_log = generate_contract_log(tra_documents)
    filing_notes = generate_filing_notes(all_files, filing_map, tra_documents)

    # Write outputs
    output_dir = Path(firm_dir)

    contract_log_path = output_dir / 'contract_log.md'
    with open(contract_log_path, 'w') as f:
        f.write(contract_log)
    print(f"Wrote {contract_log_path}")

    filing_notes_path = output_dir / 'filing_notes.md'
    with open(filing_notes_path, 'w') as f:
        f.write(filing_notes)
    print(f"Wrote {filing_notes_path}")

    # Create contracts directory
    contracts_dir = output_dir / 'contracts'
    contracts_dir.mkdir(exist_ok=True)

    # Save contract files
    for tra_doc in tra_documents:
        # For now, just organize by accession and classification
        contract_subdir = contracts_dir / f"TRA-{tra_doc['accession']}"
        contract_subdir.mkdir(exist_ok=True)

        dest_path = contract_subdir / tra_doc['filename']
        with open(tra_doc['filepath'], 'r', encoding='utf-8', errors='ignore') as src:
            content = src.read()
        with open(dest_path, 'w') as dst:
            dst.write(content)

    print(f"Organized {len(tra_documents)} TRA contracts under contracts/ directory")
    print("\nSummary:")
    print(f"  Total documents: {len(all_files)}")
    print(f"  TRA documents: {len(tra_documents)}")
    print(f"  Accessions: {len(filing_map)}")
