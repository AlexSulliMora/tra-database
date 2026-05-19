#!/usr/bin/env python3
"""
TRA summary CSV builder — parses contract_log.md files and reconstructs tra_summary.csv.

Fixes known bugs:
1. Populate notes column with distilled contract summaries.
2. Extract status_flag from backtick-wrapped tokens in contract_log.md.
3. Correctly identify date_terminated from explicit transition statements.
4. Parse counterparties from contract_log.md.
5. Correct role mis-classifications.
6. Populate tax_asset_type from keyword search.
7. Extract payment_pct from percentage patterns.
"""

import csv
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# Base directories
PROJECT_ROOT = Path("/home/sulli/research/tra")
FINDINGS_DIR = PROJECT_ROOT / "coauthor/2026-05-12-edgar-scrape/findings"
TEST_RUN_DIR = FINDINGS_DIR / "test-run"
OUTPUT_CSV = FINDINGS_DIR / "tra_summary.csv"

# Regex patterns for extraction
STATUS_FLAG_PATTERN = r"`(in_force|terminated_\w+|transferred_offledger|economically_extinguished_in_force|never_executed)`"
DATE_TERMINATED_PATTERN = r"(terminated_\w+|effective|transition)\s+(?:on\s+)?(\d{4}-\d{2}-\d{2})"
PAYMENT_PCT_PATTERN = r"(\d{1,2})%|(\d{1,2})\s+percent"
TAX_ASSET_KEYWORDS = {
    "section_754": r"(?i)section\s+754|basis\s+step-up|step-up",
    "pre_ipo_nol": r"(?i)pre-ipo\s+nol|net\s+operating\s+loss\s+carryforward",
    "338h10": r"(?i)338\(h\)\(10\)|338h10",
    "option_deductions": r"(?i)option\s+deduction|compensatory\s+stock\s+option",
    "blocker_attributes": r"(?i)blocker\s+(?:nol|attributes|transferred)",
    "amt_credit": r"(?i)amt\s+credit",
}

def read_contract_log(firm_dir: Path) -> Optional[str]:
    """Read the contract_log.md file from a firm directory."""
    log_path = firm_dir / "contract_log.md"
    if log_path.exists():
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            print(f"Warning: could not read {log_path}: {e}", file=sys.stderr)
            return None
    return None

def extract_status_flag(content: str) -> Optional[str]:
    """Extract status flag from backtick-wrapped tokens."""
    matches = re.findall(STATUS_FLAG_PATTERN, content)
    if matches:
        return matches[0]  # Return the first match (primary status)
    return None

def extract_date_terminated(content: str, status_flag: Optional[str]) -> Optional[str]:
    """
    Extract date_terminated from explicit transition statements.
    Look for patterns like "terminated_by_standalone_agreement effective 2019-12-20" or "(status transition on 2019-12-20)".
    """
    # Pattern 1: "terminated_<flag> effective YYYY-MM-DD"
    pattern1 = r"terminated_\w+\s+(?:effective|on)\s+(\d{4}-\d{2}-\d{2})"
    matches = re.findall(pattern1, content)
    if matches:
        return matches[0]

    # Pattern 2: "(status transition on YYYY-MM-DD" or "status transition on YYYY-MM-DD" (with optional parens)
    pattern2 = r"\(?status\s+(?:flag\s+)?transition\s+(?:on|:?\s+)(\d{4}-\d{2}-\d{2})"
    matches = re.findall(pattern2, content, re.IGNORECASE)
    if matches:
        return matches[0]

    # Pattern 3: "effective YYYY-MM-DD" or "effective immediately and" immediately after status flag
    pattern3 = r"`terminated_\w+`.*?effective\s+(\d{4}-\d{2}-\d{2})"
    matches = re.findall(pattern3, content, re.IGNORECASE | re.DOTALL)
    if matches:
        return matches[0]

    # Pattern 4: "TRA was terminated on YYYY-MM-DD"
    pattern4 = r"(?:tra\s+)?(?:was\s+)?terminated\s+(?:on|effective)\s+(\d{4}-\d{2}-\d{2})"
    matches = re.findall(pattern4, content, re.IGNORECASE)
    if matches:
        return matches[0]

    return None

def extract_counterparties(content: str) -> str:
    """Extract counterparties from contract_log.md."""
    counterparties = []

    # Pattern 1: "Beneficiaries:" or "Counterparties:" or "TRA Parties:"
    for label in ["Beneficiaries?", "Counterparties?", "TRA Parties?", "Initial Limited Partners?"]:
        pattern = rf"{label}\s*\n((?:[^\n]+\n)+?)\n"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            lines = match.group(1).strip().split('\n')
            for line in lines:
                line = line.strip('- * ').strip()
                if line and not line.lower().startswith(('as designated', 'agent')):
                    counterparties.append(line)

    # Pattern 2: "Parties:" section (like in AdaptHealth)
    pattern = r"Parties:\s*\n((?:.*?\n)+?)\n(?=[A-Z]|\*\*)"
    match = re.search(pattern, content)
    if match:
        lines = match.group(1).strip().split('\n')
        for line in lines:
            line = re.sub(r'^-\s+', '', line.strip())
            if line and not any(x in line.lower() for x in ['agent', 'as designated']):
                counterparties.append(line)

    return "; ".join(set(counterparties)) if counterparties else ""

def extract_payment_pct(content: str) -> Optional[str]:
    """
    Extract payment percentage from contract text.
    For amended contracts, prefer the final/amended percentage over the original.
    """
    # Pattern 1: "replaces X% with Y%" or "replaces ... with ..." — take the replacement
    amendment_match = re.search(
        r"replaces\s+['\"]?(?:\w+\s+)?percent\s*\((\d{1,2})%?\)['\"]?\s+with\s+['\"]?(?:\w+\s+)?percent\s*\((\d{1,2})%?\)",
        content,
        re.IGNORECASE
    )
    if amendment_match:
        return f"{amendment_match.group(2)}%"

    # Pattern 2: Alternative format "replaces 'eighty-five percent (85%)' with 'fifty percent (50%)'"
    amendment_match2 = re.search(
        r"(?:replaces|replaced)\s+['\"]?[^'\"]*?(\d{1,2})%[)'\"]*?\s+(?:with|to)\s+['\"]?[^'\"]*?(\d{1,2})%",
        content,
        re.IGNORECASE | re.DOTALL
    )
    if amendment_match2:
        return f"{amendment_match2.group(2)}%"

    # Pattern 3: Direct percentage patterns
    # Look for "85% payment" or "85% of"
    pattern1_matches = re.findall(r"(\d{1,2})%\s+(?:of|to|payment|payout|sharing|share)", content, re.IGNORECASE)

    # If we have percentages, prefer the most common one (usually the payment %age)
    if pattern1_matches:
        from collections import Counter
        pct_counter = Counter(pattern1_matches)
        most_common_pct = pct_counter.most_common(1)[0][0]
        return f"{most_common_pct}%"

    return None

def extract_tax_asset_types(content: str) -> str:
    """Extract tax asset types from contract content."""
    types = []
    for asset_type, pattern in TAX_ASSET_KEYWORDS.items():
        if re.search(pattern, content):
            # Map to canonical name
            canonical = {
                "section_754": "section_754_step_up",
                "pre_ipo_nol": "pre_ipo_nol",
                "338h10": "338h10_basis_step_up",
                "option_deductions": "option_deductions",
                "blocker_attributes": "blocker_attributes",
                "amt_credit": "amt_credit",
            }
            types.append(canonical.get(asset_type, asset_type))

    return ", ".join(sorted(set(types))) if types else ""

def extract_notes(content: str, cik: str, company_name: str) -> str:
    """
    Extract a terse 1-3 sentence summary from contract_log.md.
    For beneficiaries, emphasize that they hold rights; for pubcos, describe the TRA.
    """
    notes = []

    # Extract role to tailor the note
    is_beneficiary = bool(re.search(r"(?i)\brole.*?beneficiary", content))

    # Extract role description (first couple sentences after "Role determination")
    role_match = re.search(r"(?:Role determination|Firm role)\](.*?)(?=\n\n|##|\Z)", content, re.DOTALL)
    if role_match:
        role_text = role_match.group(1)
        # Clean up multiline content
        role_text = re.sub(r'\s+', ' ', role_text).strip()
        # Take first ~80 characters
        if len(role_text) > 80:
            role_text = role_text[:77] + "..."
        notes.append(role_text)

    # Extract TRA date and origin context
    tra_id_match = re.search(r"(TRA-(\d{4})-\d{2}-\d{2})", content)
    if tra_id_match:
        year = tra_id_match.group(2)
        # Extract origin context right after the TRA heading
        context_match = re.search(
            rf"{re.escape(tra_id_match.group(1))}.*?(?:SPAC|business combination|IPO|merger|acquisition)",
            content,
            re.IGNORECASE | re.DOTALL
        )
        if context_match:
            ctx = re.search(r"((?:SPAC|business combination|IPO|merger|acquisition)[^.]*?(?:20\d{2}))", context_match.group(0), re.IGNORECASE)
            if ctx:
                notes.append(f"{year} TRA: {ctx.group(1)[:60]}")

    # Extract payment terms (percentage and asset type)
    pct = extract_payment_pct(content)
    assets = extract_tax_asset_types(content)
    if pct or assets:
        payment_note = f"{pct or 'variable'} to beneficiaries"
        if assets:
            payment_note += f" on {assets.split(',')[0]}"
        notes.append(payment_note)

    # Extract status with key transitions
    status = extract_status_flag(content)
    if status:
        date_term = extract_date_terminated(content, status)
        if "in_force" in status:
            notes.append("In force.")
        elif "terminated" in status:
            status_short = status.replace('terminated_', '').replace('_', ' ')
            if date_term:
                notes.append(f"Terminated {status_short} on {date_term}.")
            else:
                notes.append(f"Terminated ({status_short}).")

    # Collapse to 1-3 sentences (up to ~200 chars for better readability)
    summary = " ".join(notes)
    # Limit to first ~180 characters
    if len(summary) > 180:
        summary = summary[:177].rsplit(' ', 1)[0] + "."

    # Always end with a period if non-empty
    if summary and not summary.endswith('.'):
        summary += '.'

    return summary.strip()

def parse_firm_row(firm_dir: Path) -> Optional[Dict]:
    """
    Parse a single firm directory and return a row dict.
    Firm dir naming: `<slug>_<cik>` (no leading zero in display, but CIK field is padded).
    """
    firm_name = firm_dir.name
    if not firm_dir.is_dir():
        return None

    # Extract CIK from directory name (last underscore-separated segment)
    parts = firm_name.rsplit('_', 1)
    if len(parts) != 2:
        return None

    slug, cik_raw = parts
    cik = cik_raw.lstrip('0') or '0'  # Remove leading zeros but keep at least one
    cik_padded = cik.zfill(10)  # Pad to 10 digits for CSV

    # Read contract log
    content = read_contract_log(firm_dir)
    if not content:
        # No contract log; return a minimal row
        return {
            'cik': cik_padded,
            'company_name': '',
            'slug': slug,
            'role': 'mention_only',
            'tra_id': '',
            'counterparties': '',
            'date_executed': '',
            'date_terminated': '',
            'status_flag': '',
            'tax_asset_type': '',
            'payment_pct': '',
            'notes': '',
        }

    # Extract company name from heading
    company_match = re.search(r"#\s+([^(]+?)(?:\s*\(|$)", content)
    company_name = company_match.group(1).strip() if company_match else ''

    # Extract TRA ID first (needed for date extraction)
    tra_id_match = re.search(r'(TRA-\d{4}-\d{2}-\d{2})', content)
    tra_id = tra_id_match.group(1) if tra_id_match else ''

    # Extract date_executed from TRA ID first (this is always the original execution date)
    if tra_id:
        # TRA ID format: TRA-YYYY-MM-DD
        parts = tra_id.split('-')
        if len(parts) == 4:
            date_executed = f"{parts[1]}-{parts[2]}-{parts[3]}"
        else:
            date_executed = ''
    else:
        # No TRA ID, try to find execution date from content
        date_executed_match = re.search(r"(?:executed|dated)\s+(?:as\s+of\s+)?(\d{4}-\d{2}-\d{2})", content)
        date_executed = date_executed_match.group(1) if date_executed_match else ''

    # Determine role (check for role determination early)
    role = 'mention_only'

    # Look for explicit role statements in contract_log.md
    role_section = re.search(
        r"(?:Role determination|Firm role)\s*\n+(.*?)(?:\n\n|\n##|\Z)",
        content,
        re.IGNORECASE | re.DOTALL
    )

    if role_section:
        role_text = role_section.group(1).lower()
        # Check for explicit role first line (before the verb "is")
        first_line = role_text.split('\n')[0].strip()

        # Pattern 0: Explicit "none of the five roles" — keep as mention_only
        if 'none of the five roles' in role_text or 'classified role: none' in first_line:
            role = 'mention_only'
        # Pattern 1: "**role: beneficiary**" or "role: beneficiary" at the very start
        elif re.match(r"\*?\*?role\s*:\s*beneficiary", first_line):
            role = 'beneficiary'
        # Pattern 2: "**role: pubco**" or "PubCo /" at the start
        elif re.match(r"\*?\*?role\s*:\s*pubco|^pubco\s*[\/-]", first_line):
            role = 'pubco'
        # Pattern 3: Look at what the firm "is" (e.g., "is the public company" = pubco, "is a beneficiary" = beneficiary)
        elif ' is the ' in first_line:
            if 'public company' in first_line or 'obligor' in first_line[:50]:
                role = 'pubco'
            elif 'beneficiary' in first_line:
                role = 'beneficiary'
        elif ' is a ' in first_line:
            if 'beneficiary' in first_line:
                role = 'beneficiary'
            elif 'public' in first_line or 'obligor' in first_line:
                role = 'pubco'
        # Fallback: search anywhere in section
        elif 'beneficiary' in role_text and role_text.count('beneficiary') > role_text.count('obligor'):
            role = 'beneficiary'
        elif 'pubco' in role_text or 'obligor' in role_text:
            role = 'pubco'

    # Extract date_terminated
    date_terminated = extract_date_terminated(content, extract_status_flag(content))

    # Extract other fields
    status_flag = extract_status_flag(content)
    counterparties = extract_counterparties(content)
    tax_asset_type = extract_tax_asset_types(content)
    payment_pct = extract_payment_pct(content)
    notes = extract_notes(content, cik_padded, company_name)

    # Handle status flags
    if not tra_id and not date_executed:
        if role == 'beneficiary':
            # Beneficiaries may have docs elsewhere (under obligor's CIK)
            # Keep status_flag if found, else leave empty
            pass
        else:
            role = 'never_executed'
            status_flag = status_flag or 'never_executed'
    elif not tra_id and status_flag and role != 'beneficiary':
        role = 'no_tra'

    return {
        'cik': cik_padded,
        'company_name': company_name,
        'slug': slug,
        'role': role,
        'tra_id': tra_id,
        'counterparties': counterparties,
        'date_executed': date_executed,
        'date_terminated': date_terminated,
        'status_flag': status_flag,
        'tax_asset_type': tax_asset_type,
        'payment_pct': payment_pct,
        'notes': notes,
    }

def load_existing_csv() -> Dict[str, Dict]:
    """Load the existing CSV to preserve CIK and company_name fields where available."""
    existing = {}
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                slug = row.get('slug', '')
                if slug:
                    existing[slug] = row
    return existing

def build_csv():
    """Walk test-run directory, parse each firm, and write CSV."""
    rows = []

    # Load existing data to fill in CIK/company_name where we don't have a contract_log
    existing = load_existing_csv()

    # Walk all firm directories
    for firm_dir in sorted(TEST_RUN_DIR.iterdir()):
        if firm_dir.is_dir() and firm_dir.name != 'TEST_RUN_REPORT.md':
            row = parse_firm_row(firm_dir)
            if row:
                # Merge in existing CIK/company_name if we didn't extract them
                slug = row['slug']
                if not row['company_name'] and slug in existing:
                    row['company_name'] = existing[slug].get('company_name', '')
                    if not row['cik'] or row['cik'] == '0000000000':
                        row['cik'] = existing[slug].get('cik', row['cik'])

                rows.append(row)

    # Write CSV
    fieldnames = [
        'cik', 'company_name', 'slug', 'role', 'tra_id', 'counterparties',
        'date_executed', 'date_terminated', 'status_flag', 'tax_asset_type', 'payment_pct', 'notes'
    ]

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")
    return rows

def print_verification(rows: List[Dict]):
    """Print verification statistics."""
    print("\n=== Verification Report ===\n")

    # Count by role
    role_counts = {}
    for row in rows:
        role = row['role']
        role_counts[role] = role_counts.get(role, 0) + 1

    print("Row counts by role:")
    for role in sorted(role_counts.keys()):
        print(f"  {role}: {role_counts[role]}")

    # Count by status_flag
    status_counts = {}
    for row in rows:
        status = row['status_flag'] or '(empty)'
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nRow counts by status_flag:")
    for status in sorted(status_counts.keys()):
        print(f"  {status}: {status_counts[status]}")

    # Count non-empty notes
    notes_filled = sum(1 for row in rows if row['notes'].strip())
    print(f"\nFirms with non-empty notes: {notes_filled}/{len(rows)}")

    # Sample rows for specified firms
    sample_firms = [
        'adapthealth-corp', 'agiliti-health-inc', 'agiliti-inc-de', 'agrofresh-solutions-inc',
        'aevex-corp', 'advisory-board-co', 'adeptus-health-inc', 'aleanna-Inc'
    ]

    print("\nSample rows (8 firms):")
    for firm in sample_firms:
        matching = [r for r in rows if r['slug'] == firm]
        if matching:
            row = matching[0]
            print(f"\n  {firm}:")
            for field in ['cik', 'role', 'tra_id', 'status_flag', 'payment_pct', 'notes']:
                val = row.get(field, '(missing)')
                val = val or '(empty)'
                if len(val) > 60:
                    val = val[:57] + "..."
                print(f"    {field}: {val}")

if __name__ == '__main__':
    rows = build_csv()
    print_verification(rows)
