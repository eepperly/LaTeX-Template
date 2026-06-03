#!/usr/bin/env python
"""
make_cvpubs.py — Convert a BibTeX file to \cvpub{} entries for a LaTeX CV.

Usage:
    python make_cvpubs.py refs.bib
    python make_cvpubs.py refs.bib --bold Webber   # bold a different name
    python make_cvpubs.py refs.bib > cvpubs.tex    # redirect to file

Output is sorted reverse-chronologically (newest first) and written to stdout.
"""

import bibtexparser
from bibtexparser.bparser import BibTexParser
import re
import argparse
import sys

DEFAULT_BOLD_NAME = 'Epperly'

# ==========================================
# 1. Author Formatting
# ==========================================

def parse_author(raw):
    """Parse a single BibTeX author name into (first_parts, last)."""
    raw = re.sub(r'\s+', ' ', raw.strip())
    if ',' in raw:
        idx = raw.index(',')
        last = raw[:idx].strip()
        first_str = raw[idx + 1:].strip()
        first_parts = first_str.split() if first_str else []
    else:
        parts = raw.split()
        if not parts:
            return [], ''
        if len(parts) == 1:
            return [], parts[0]
        last = parts[-1]
        first_parts = parts[:-1]
    return first_parts, last

def initial(part):
    """Return the uppercase first letter of a name part, stripping LaTeX braces."""
    clean = re.sub(r'[{}]', '', part).strip()
    return clean[0].upper() if clean else ''

def format_one_author(first_parts, last):
    """Format a single author as E.\\ N.\\ Last."""
    initials = [c for c in (initial(p) for p in first_parts) if c]
    return ''.join(f'{c}.\\ ' for c in initials) + last

def format_authors(author_field, bold_name=DEFAULT_BOLD_NAME):
    """Format a full BibTeX author field for a LaTeX CV."""
    raw_list = re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE)
    formatted = []
    for raw in raw_list:
        first_parts, last = parse_author(raw)
        name = format_one_author(first_parts, last)
        if last.lower() == bold_name.lower():
            name = f'\\textbf{{{name}}}'
        formatted.append(name)

    n = len(formatted)
    if n == 0:
        return ''
    elif n == 1:
        return formatted[0]
    elif n == 2:
        return f'{formatted[0]} \\& {formatted[1]}'
    else:
        # Oxford comma: A, B, \& C
        return ', '.join(formatted[:-1]) + ', \\& ' + formatted[-1]

# ==========================================
# 2. Venue Formatting
# ==========================================

def detect_arxiv(entry):
    return any(
        'arxiv' in entry.get(f, '').lower()
        for f in ('journal', 'url', 'eprint', 'archiveprefix')
    )

def clean_title(title):
    """Strip BibTeX case-protection braces from a title string."""
    prev = None
    t = title
    while t != prev:
        prev = t
        t = re.sub(r'\{([^{}]*)\}', r'\1', t)
    return t.strip().rstrip('.')

def format_doi_link(doi):
    doi = re.sub(r'https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE).strip()
    return f'doi:\\href{{https://doi.org/{doi}}}{{{doi}}}'

def format_venue(entry):
    """Return (venue_str, doi_str). doi_str is '' when there is no DOI."""
    if detect_arxiv(entry):
        # Journal field is already formatted by bibtex_cleaner, e.g.:
        #   arXiv preprint \href{http://arxiv.org/abs/2304.12465v2}{arXiv:2304.12465v2}
        return entry.get('journal', 'arXiv preprint'), ''

    journal = entry.get('journal', entry.get('booktitle', ''))
    volume  = entry.get('volume', '')
    pages   = entry.get('pages', '')

    venue = journal
    if volume:
        venue += f' {volume}'
    if pages:
        venue += f', {pages}'

    doi = entry.get('doi', '').strip()
    doi_str = f'  {format_doi_link(doi)}' if doi else ''

    return venue, doi_str

# ==========================================
# 3. Entry Formatting
# ==========================================

def format_entry(entry, bold_name=DEFAULT_BOLD_NAME):
    """Format a single BibTeX entry as a \\cvpub{} line."""
    authors = format_authors(entry.get('author', ''), bold_name)
    year    = entry.get('year', '')
    title   = clean_title(entry.get('title', ''))
    venue, doi_str = format_venue(entry)

    return f'\\cvpub{{{authors} ({year}). {title}. {venue}.{doi_str}}}'

# ==========================================
# 4. Main
# ==========================================

def sort_key(entry):
    try:
        return -int(entry.get('year', 0))
    except ValueError:
        return 0

def process_bibtex(input_file, bold_name):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            bib = bibtexparser.load(f, BibTexParser(common_strings=True))
    except FileNotFoundError:
        print(f"Error: '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    entries = sorted(bib.entries, key=sort_key)  # stable: same-year order preserved

    lines = []
    for entry in entries:
        try:
            lines.append(format_entry(entry, bold_name))
        except Exception as exc:
            key = entry.get('ID', 'unknown')
            print(f"Warning: skipping '{key}': {exc}", file=sys.stderr)

    print('\n\n'.join(lines))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description='Convert a BibTeX file to \\cvpub{} entries for a LaTeX CV'
    )
    ap.add_argument('input', help='Input .bib file')
    ap.add_argument(
        '--bold', default=DEFAULT_BOLD_NAME, metavar='LAST_NAME',
        help=f'Last name to typeset in bold (default: {DEFAULT_BOLD_NAME})'
    )
    args = ap.parse_args()
    process_bibtex(args.input, args.bold)
