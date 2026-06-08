#!/usr/bin/env python
"""
make_cvpubs.py — Convert a BibTeX file to \\cvpub{} entries for a LaTeX CV,
                 and optionally a Markdown numbered list for a website.

Usage:
    python make_cvpubs.py refs.bib
    python make_cvpubs.py refs.bib --bold Webber        # bold a different name
    python make_cvpubs.py refs.bib > cvpubs.tex         # redirect to file
    python make_cvpubs.py refs.bib --markdown pubs.md   # also write Markdown

Output is sorted reverse-chronologically (newest first) and written to stdout.
"""

import bibtexparser
from bibtexparser.bparser import BibTexParser
import re
import argparse
import sys

DEFAULT_BOLD_NAME = 'Epperly'

# ==========================================
# 0. Section Parsing
# ==========================================

_SECTION_RE  = re.compile(r'^%%%\s+(.+)$')
_ENTRY_KEY_RE = re.compile(r'^@(?!string\b|comment\b|preamble\b)\w+\s*\{([^,\s\}]+)', re.IGNORECASE)

def parse_sections(filepath):
    """
    Scan a .bib file for %%% section comments and return an ordered list of
    (section_name_or_None, [entry_key, ...]) tuples preserving file order.
    """
    sections = []
    current_name = None
    current_keys = []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            m = _SECTION_RE.match(line)
            if m:
                sections.append((current_name, current_keys))
                current_name = m.group(1).strip()
                current_keys = []
            else:
                m = _ENTRY_KEY_RE.match(line)
                if m:
                    current_keys.append(m.group(1))

    sections.append((current_name, current_keys))
    return [(n, ks) for n, ks in sections if n is not None or ks]

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

def format_one_author(first_parts, last, sep='\\ '):
    """Format a single author as 'E.\\ N.\\ Last' (LaTeX) or 'E. N. Last' (Markdown)."""
    initials = [c for c in (initial(p) for p in first_parts) if c]
    return ''.join(f'{c}.{sep}' for c in initials) + last

def _join_authors(formatted, ampersand):
    n = len(formatted)
    if n == 0:
        return ''
    elif n == 1:
        return formatted[0]
    elif n == 2:
        return f'{formatted[0]} {ampersand} {formatted[1]}'
    else:
        return ', '.join(formatted[:-1]) + f', {ampersand} ' + formatted[-1]

def format_authors(author_field, bold_name=DEFAULT_BOLD_NAME):
    """Format a full BibTeX author field for a LaTeX CV."""
    raw_list = re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE)
    formatted = []
    for raw in raw_list:
        first_parts, last = parse_author(raw)
        name = format_one_author(first_parts, last, sep='\\ ')
        if last.lower() == bold_name.lower():
            name = f'\\textbf{{{name}}}'
        formatted.append(name)
    return _join_authors(formatted, '\\&')

_ACCENT_MAP = {
    "'": '́', '`': '̀', '^': '̂', '"': '̈',
    '~': '̃', '=': '̄', '.': '̇', 'c': '̧',
    'v': '̌', 'u': '̆', 'H': '̋',
}

def _replace_accent(m):
    cmd, char = m.group(1), m.group(2)
    combining = _ACCENT_MAP.get(cmd)
    if combining:
        import unicodedata
        return unicodedata.normalize('NFC', char + combining)
    return char

def _latex_to_md(text):
    """Convert LaTeX markup in a string to Markdown equivalents."""
    # \href{url}{text} -> [text](url)  (must happen before brace stripping)
    text = re.sub(r'\\href\{([^}]+)\}\{([^}]+)\}', r'[\2](\1)', text)
    # Strip { } braces first so {\'n} becomes \'n before accent substitution
    prev = None
    while text != prev:
        prev = text
        text = re.sub(r'\{([^{}]*)\}', r'\1', text)
    # Common LaTeX accents: \'e -> é, \`a -> à, \^o -> ô, \"u -> ü, etc.
    text = re.sub(r"\\([`'^\"~=.cvuH])([A-Za-z])", _replace_accent, text)
    # Special LaTeX characters: \l -> ł, \o -> ø, \ae -> æ, etc.
    _SPECIAL = {
        'l': 'ł', 'L': 'Ł', 'o': 'ø', 'O': 'Ø',
        'aa': 'å', 'AA': 'Å', 'ae': 'æ', 'AE': 'Æ',
        'oe': 'œ', 'OE': 'Œ', 'ss': 'ß', 'i': 'ı',
    }
    text = re.sub(r'\\([A-Za-z]+)', lambda m: _SPECIAL.get(m.group(1), m.group(0)), text)
    # \\ spacing -> single space
    text = text.replace('\\ ', ' ')
    # LaTeX en-dash -- -> Unicode en dash
    text = text.replace('--', '–')
    return text.strip()

def format_authors_md(author_field, bold_name=DEFAULT_BOLD_NAME):
    """Format a full BibTeX author field for Markdown."""
    raw_list = re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE)
    formatted = []
    for raw in raw_list:
        first_parts, last = parse_author(raw)
        name = _latex_to_md(format_one_author(first_parts, last, sep=' '))
        if last.lower() == bold_name.lower():
            name = f'**{name}**'
        formatted.append(name)
    return _join_authors(formatted, '&')

# ==========================================
# 2. Venue Formatting
# ==========================================

def detect_arxiv(entry):
    return any(
        'arxiv' in entry.get(f, '').lower()
        for f in ('journal', 'url')
    )

def clean_title(title):
    """Strip BibTeX case-protection braces from a title string."""
    prev = None
    t = title
    while t != prev:
        prev = t
        t = re.sub(r'\{([^{}]*)\}', r'\1', t)
    return t.strip().rstrip('.')

def _entry_link_url(entry):
    """Return the canonical URL for an entry (DOI preferred, then URL field)."""
    doi = re.sub(r'https?://(dx\.)?doi\.org/', '', entry.get('doi', ''),
                 flags=re.IGNORECASE).strip()
    if doi:
        return f'https://doi.org/{doi}'
    return entry.get('url', '').strip()

def _arxiv_url(journal_field):
    """Extract the URL from a \\href{url}{...} in the journal field."""
    m = re.search(r'\\href\{([^}]+)\}', journal_field)
    return m.group(1) if m else ''

def format_venue(entry):
    """Return (venue_str, link_url) where link_url is used to hyperlink the title."""
    etype = entry.get('ENTRYTYPE', '').lower()

    if detect_arxiv(entry):
        # Journal field already formatted by bibtex_cleaner, e.g.:
        #   arXiv preprint \href{http://arxiv.org/abs/2304.12465v2}{arXiv:2304.12465v2}
        # The arXiv number is already a hyperlink; we also want the title linked.
        journal = entry.get('journal', 'arXiv preprint')
        return journal, _arxiv_url(journal)

    if etype == 'phdthesis':
        type_str = entry.get('type', 'PhD dissertation')
        school   = entry.get('school', '')
        venue    = f'{type_str}, {school}' if school else type_str
        return venue, _entry_link_url(entry)

    if etype == 'mastersthesis':
        type_str = entry.get('type', "Master's thesis")
        school   = entry.get('school', '')
        venue    = f'{type_str}, {school}' if school else type_str
        return venue, _entry_link_url(entry)

    if etype == 'techreport':
        type_str    = entry.get('type', 'Technical report')
        number      = entry.get('number', '')
        institution = entry.get('institution', '')
        type_str    = f'{type_str} {number}' if number else type_str
        venue       = f'{type_str}, {institution}' if institution else type_str
        return venue, _entry_link_url(entry)

    # Journal article, conference paper, book chapter, etc.
    journal = entry.get('journal', entry.get('booktitle', ''))
    volume  = entry.get('volume', '')
    pages   = entry.get('pages', '')

    venue = journal
    if volume:
        venue += f' {volume}'
    if pages:
        venue += f', {pages}'

    return venue, _entry_link_url(entry)

# ==========================================
# 3. Entry Formatting
# ==========================================

def format_entry(entry, bold_name=DEFAULT_BOLD_NAME):
    """Format a single BibTeX entry as a \\cvpub{} line."""
    authors  = format_authors(entry.get('author', ''), bold_name)
    year     = entry.get('year', '')
    title    = clean_title(entry.get('title', ''))
    venue, link_url = format_venue(entry)

    # Title is a hyperlink when a URL is available
    title_latex = f'\\href{{{link_url}}}{{{title}}}' if link_url else title

    # For published papers that also have an arXiv eprint, append a preprint link
    preprint = ''
    if not detect_arxiv(entry):
        eprint = entry.get('eprint', '').strip()
        if eprint:
            preprint = f' (\\href{{https://arxiv.org/abs/{eprint}}}{{preprint}})'

    return f'\\cvpub{{{authors} ({year}). {title_latex}. {venue}.{preprint}}}'

def format_entry_md(entry, number, bold_name=DEFAULT_BOLD_NAME):
    """Format a single BibTeX entry as a Markdown numbered list item."""
    authors  = format_authors_md(entry.get('author', ''), bold_name)
    year     = entry.get('year', '')
    title    = clean_title(entry.get('title', ''))
    venue, link_url = format_venue(entry)

    title_md = f'[{title}]({link_url})' if link_url else title

    if detect_arxiv(entry):
        # Venue: plain "arXiv preprint"; preprint link in parens
        venue_md = 'arXiv preprint'
        arxiv_url = link_url or (
            f'https://arxiv.org/abs/{entry["eprint"]}' if entry.get('eprint') else '')
        preprint = f' ([preprint]({arxiv_url}))' if arxiv_url else ''
    else:
        venue_md = _latex_to_md(venue)
        eprint = entry.get('eprint', '').strip()
        preprint = f' ([preprint](https://arxiv.org/abs/{eprint}))' if eprint else ''

    return f'{number}. {authors} ({year}). {title_md}. {venue_md}.{preprint}'

# ==========================================
# 4. Main
# ==========================================

def sort_key(entry):
    try:
        return -int(entry.get('year', 0))
    except ValueError:
        return 0

_SECTION_DIVIDER = '%---------------------------------------------------------'

def render_section(section_name, entries, bold_name):
    """Return the LaTeX block for one section."""
    pub_lines = []
    for entry in sorted(entries, key=sort_key):
        try:
            pub_lines.append(format_entry(entry, bold_name))
        except Exception as exc:
            key = entry.get('ID', 'unknown')
            print(f"Warning: skipping '{key}': {exc}", file=sys.stderr)

    if not pub_lines:
        return None

    inner = '\n\n'.join(pub_lines)
    body = f'\\begin{{cvpubs}}\n{inner}\n\\end{{cvpubs}}'

    if section_name is not None:
        return f'\\cvsubsection{{{section_name}}}\n{_SECTION_DIVIDER}\n\n{body}'
    else:
        return body

def render_section_md(section_name, entries, bold_name, start_num=1):
    """Return (markdown_block_or_None, next_number) for one section."""
    lines = []
    num = start_num
    for entry in sorted(entries, key=sort_key):
        try:
            lines.append(format_entry_md(entry, num, bold_name))
            num += 1
        except Exception as exc:
            key = entry.get('ID', 'unknown')
            print(f"Warning: skipping '{key}': {exc}", file=sys.stderr)

    if not lines:
        return None, num

    body = '\n'.join(lines)
    if section_name is not None:
        return f'### {section_name}\n\n{body}', num
    else:
        return body, num

def process_bibtex(input_file, bold_name, markdown_file=None):
    try:
        sections = parse_sections(input_file)
        with open(input_file, 'r', encoding='utf-8') as f:
            bib = bibtexparser.load(f, BibTexParser(common_strings=True))
    except FileNotFoundError:
        print(f"Error: '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    entry_dict = {e['ID']: e for e in bib.entries}

    if sections:
        latex_blocks = []
        md_blocks    = []
        rendered_keys = set()
        md_counter = 1

        for section_name, keys in sections:
            entries = [entry_dict[k] for k in keys if k in entry_dict]
            rendered_keys.update(k for k in keys if k in entry_dict)

            block = render_section(section_name, entries, bold_name)
            if block:
                latex_blocks.append(block)

            md_block, md_counter = render_section_md(section_name, entries, bold_name, md_counter)
            if md_block:
                md_blocks.append(md_block)

        # Append any entries not captured by a section
        leftover = [e for e in bib.entries if e['ID'] not in rendered_keys]
        if leftover:
            block = render_section(None, leftover, bold_name)
            if block:
                latex_blocks.append(block)

            md_block, md_counter = render_section_md(None, leftover, bold_name, md_counter)
            if md_block:
                md_blocks.append(md_block)

        print('\\cvsection{Publication List}\n\n\n' + '\n\n\n'.join(latex_blocks))
        md_output = '\n\n'.join(md_blocks)
    else:
        # No section structure — flat list
        block = render_section(None, bib.entries, bold_name)
        if block:
            print('\\cvsection{Publication List}\n\n\n' + block)

        md_block, _ = render_section_md(None, bib.entries, bold_name)
        md_output = md_block or ''

    if markdown_file and md_output:
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(md_output + '\n')
        print(f"Markdown written to: {markdown_file}", file=sys.stderr)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description='Convert a BibTeX file to \\cvpub{} entries for a LaTeX CV'
    )
    ap.add_argument('input', help='Input .bib file')
    ap.add_argument(
        '--bold', default=DEFAULT_BOLD_NAME, metavar='LAST_NAME',
        help=f'Last name to typeset in bold (default: {DEFAULT_BOLD_NAME})'
    )
    ap.add_argument(
        '--markdown', metavar='FILE',
        help='Also write a Markdown numbered list to FILE'
    )
    args = ap.parse_args()
    process_bibtex(args.input, args.bold, markdown_file=args.markdown)
