#!/usr/bin/env python

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase, BibDataStringExpression
import re
import argparse
import sys
import json
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_RULES_FILE = os.path.join(_SCRIPT_DIR, 'title_rules.json')
REMOVE_FIELDS_FILE = os.path.join(_SCRIPT_DIR, 'remove_fields.json')
DEFAULT_REMOVE_FIELDS = ['abstract', 'shorttitle', 'file', 'langid', 'issn', 'keywords']

# Fields that are arXiv-specific and should be removed when reformatting
_ARXIV_FIELDS = ('eprint', 'archiveprefix', 'primaryclass', 'publisher',
                 'number', 'urldate', 'url', 'doi', 'howpublished')

# ==========================================
# 1. Helper Functions
# ==========================================

_SECTION_RE = re.compile(r'^%%%\s+(.+)$')
_ENTRY_KEY_RE = re.compile(r'^@(?!string\b|comment\b|preamble\b)\w+\s*\{([^,\s\}]+)', re.IGNORECASE)

def flatten_string_exprs(bib_database):
    """
    Replace every BibDataStringExpression field value with its resolved plain
    string, and return a mapping {(entry_id, field): (expression, resolved)}
    so the expressions can be restored later for fields we didn't modify.
    """
    abbrev_map = {}
    for entry in bib_database.entries:
        eid = entry.get('ID', '')
        for key, val in list(entry.items()):
            if isinstance(val, BibDataStringExpression):
                resolved = val.get_value()
                abbrev_map[(eid, key)] = (val, resolved)
                entry[key] = resolved
    return abbrev_map

def restore_string_exprs(bib_database, abbrev_map):
    """
    For any field that still holds the originally-resolved string value,
    put the BibDataStringExpression back so the writer outputs the abbreviation.
    """
    for entry in bib_database.entries:
        eid = entry.get('ID', '')
        for key in list(entry.keys()):
            pair = abbrev_map.get((eid, key))
            if pair is not None:
                expr, resolved = pair
                if entry[key] == resolved:
                    entry[key] = expr

def extract_string_defs(filepath):
    """
    Return a list of raw @STRING(...) / @STRING{...} blocks from the file,
    preserving the original text exactly so they can be written back out.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    defs = []
    for m in re.finditer(r'@[Ss][Tt][Rr][Ii][Nn][Gg]\s*([({])', content):
        start = m.start()
        opener = m.group(1)
        closer = ')' if opener == '(' else '}'
        depth = 0
        for i in range(m.start(1), len(content)):
            if content[i] == opener:
                depth += 1
            elif content[i] == closer:
                depth -= 1
                if depth == 0:
                    defs.append(content[start:i + 1])
                    break
    return defs

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

def load_json_file(filename, default=None):
    if default is None:
        default = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
    return default

def save_json_file(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4, sort_keys=True)

def extract_arxiv_id(text):
    if not text: return None
    pattern = r'(\d{4}\.\d{4,5}|[a-z\-\.]+\/\d{7})'
    match = re.search(pattern, text)
    return match.group(1) if match else None

def read_bibtex_paste(first_line):
    """
    Collect a multi-line BibTeX entry from stdin.
    first_line is the line already read that starts with '@'.
    Reads until the top-level braces are balanced, then returns the full string.
    """
    lines = [first_line]
    depth = first_line.count('{') - first_line.count('}')
    while depth > 0:
        try:
            line = input()
        except EOFError:
            break
        lines.append(line)
        depth += line.count('{') - line.count('}')
    return '\n'.join(lines)

def parse_bibtex_entry(raw_text):
    """Parse a raw BibTeX string and return the first entry as a dict, or None."""
    try:
        parser = bibtexparser.bparser.BibTexParser(common_strings=True)
        db = bibtexparser.loads(raw_text, parser)
        if db.entries:
            return db.entries[0]
    except Exception:
        pass
    return None

def clean_doi_value(doi_text):
    # Removes https://doi.org/ prefixes
    return re.sub(r'https?://(dx\.)?doi\.org/', '', doi_text, flags=re.IGNORECASE).strip()

def apply_doi_to_entry(entry, doi):
    """
    Set DOI (and URL) on an entry.  DOIs of the form 10.5555/... are ACM
    placeholder DOIs: store the dl.acm.org link as the URL instead and leave
    the doi field empty so it doesn't appear in the output.
    """
    if doi.startswith('10.5555/'):
        entry['url'] = f'https://dl.acm.org/doi/{doi}'
        entry.pop('doi', None)
        return 'url'
    else:
        entry['doi'] = doi
        entry.pop('url', None)
        return 'doi'

def clean_word_key(word):
    return re.sub(r'[^\w]', '', word)

# ==========================================
# Key Standardization Helpers
# ==========================================

def _last_name(raw):
    """Extract last name from a single BibTeX author string."""
    raw = raw.strip()
    if ',' in raw:
        return raw[:raw.index(',')].strip()
    parts = raw.split()
    return parts[-1] if parts else ''

def _author_last_names(author_field):
    """Return list of last names from a BibTeX author field."""
    if not author_field:
        return []
    return [_last_name(a) for a in re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE) if a.strip()]

def _alpha_letters(last_names):
    """Return the author-letter prefix for the alpha key style."""
    n = len(last_names)
    clean = [re.sub(r'[^A-Za-z]', '', ln) for ln in last_names]
    if n == 0:
        return '?'
    elif n == 1:
        s = clean[0]
        return (s[0].upper() + s[1:3].lower()) if s else '?'
    elif n <= 4:
        return ''.join(s[0].upper() for s in clean if s)
    else:  # 5+ authors
        return ''.join(s[0].upper() for s in clean[:3] if s) + '+'

def make_alpha_key(entry):
    """Generate an alpha-style key: Che25, CE25, CET25, CETW25, CET+25."""
    last_names = _author_last_names(entry.get('author', ''))
    year = entry.get('year', '????')
    year2 = year[-2:] if len(year) >= 2 else year
    return _alpha_letters(last_names) + year2

_TITLE_SKIP = {'a', 'an', 'the', 'on', 'in', 'of', 'for', 'to', 'and', 'or', 'with', 'via', 'by'}

def make_namedateword_key(entry):
    """Generate a namedateword key: chen2025randomly."""
    last_names = _author_last_names(entry.get('author', ''))
    last = re.sub(r'[^A-Za-z]', '', last_names[0]).lower() if last_names else 'unknown'
    year = entry.get('year', '')
    title_clean = re.sub(r'[{}\\$]', '', entry.get('title', ''))
    words = [w.lower() for w in re.split(r'\W+', title_clean) if w]
    word = next((w for w in words if w not in _TITLE_SKIP), words[0] if words else 'unknown')
    return f'{last}{year}{word}'

def standardize_keys(entries, style):
    """
    Return an {old_id: new_id} mapping applying the given style
    ('alpha' or 'namedateword').  Conflicts get a/b/c suffixes.
    """
    keyfn = make_alpha_key if style == 'alpha' else make_namedateword_key
    proposed = {e['ID']: keyfn(e) for e in entries}

    # Count collisions
    from collections import Counter
    counts = Counter(proposed.values())

    seen = {}
    result = {}
    for eid, key in proposed.items():
        if counts[key] > 1:
            idx = seen.get(key, 0)
            result[eid] = key + chr(ord('a') + idx)
            seen[key] = idx + 1
        else:
            result[eid] = key
    return result

def write_rename_script(key_renames, script_path):
    """
    Write a shell script that find-replaces old BibTeX keys with new ones
    across all .tex and .bib files under the current directory.
    """
    pairs = [(old, new) for old, new in sorted(key_renames.items()) if old != new]
    if not pairs:
        return
    esc = lambda s: re.sub(r'([-_.+])', r'\\\1', s)
    with open(script_path, 'w') as f:
        f.write('#!/bin/bash\n')
        f.write('# Auto-generated by bibtex_cleaner.py — rename BibTeX cite keys\n')
        f.write('# Run from your project root: bash rename_keys.sh\n\n')
        f.write('FILES=$(find . \\( -name "*.tex" -o -name "*.bib" \\) -print)\n\n')
        subs = '\n  '.join(f's/\\b{esc(old)}\\b/{new}/g;' for old, new in pairs)
        f.write(f'perl -pi -e \'\n  {subs}\n\' $FILES\n')
    print(f"-> Key rename script written to: {script_path}")

# ==========================================
# Conference-Specific Booktitle Helpers
# ==========================================

_ORDINAL_ONES = [
    '', 'First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh',
    'Eighth', 'Ninth', 'Tenth', 'Eleventh', 'Twelfth', 'Thirteenth',
    'Fourteenth', 'Fifteenth', 'Sixteenth', 'Seventeenth', 'Eighteenth',
    'Nineteenth',
]
_ORDINAL_TENS     = ['', '', 'Twentieth', 'Thirtieth', 'Fortieth', 'Fiftieth',
                     'Sixtieth', 'Seventieth', 'Eightieth', 'Ninetieth']
_ORDINAL_TENS_PFX = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
                     'Sixty', 'Seventy', 'Eighty', 'Ninety']

def ordinal_word(n):
    """Return the spelled-out ordinal for n (1 → 'First', 32 → 'Thirty-Second')."""
    if 1 <= n <= 19:
        return _ORDINAL_ONES[n]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _ORDINAL_TENS[tens]
    return f'{_ORDINAL_TENS_PFX[tens]}-{_ORDINAL_ONES[ones]}'

_SODA_FIRST_YEAR = 1990

def format_soda_booktitle(year):
    edition = year - _SODA_FIRST_YEAR + 1
    return (f'Proceedings of the {ordinal_word(edition)} Annual '
            f'ACM-SIAM Symposium on Discrete Algorithms')

def is_soda(entry):
    """Fuzzy-match a bib entry as a SODA paper."""
    bt = entry.get('booktitle', '')
    bt_lower = bt.lower()
    return ('discrete algorithms' in bt_lower or
            re.search(r'\bsoda\b', bt_lower) is not None)

def numeric_ordinal(n):
    """Return a numeric ordinal string: 49 → '49th', 51 → '51st', etc."""
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'

_STOC_FIRST_YEAR = 1969
_STOC_NUMERIC_FROM = 49  # use numeric ordinal for 49th STOC onward

def format_stoc_booktitle(year):
    edition = year - _STOC_FIRST_YEAR + 1
    ordinal = (numeric_ordinal(edition) if edition >= _STOC_NUMERIC_FROM
               else ordinal_word(edition))
    return (f'Proceedings of the {ordinal} Annual '
            f'ACM Symposium on the Theory of Computing')

def is_stoc(entry):
    """Fuzzy-match a bib entry as a STOC paper."""
    bt = entry.get('booktitle', '')
    bt_lower = bt.lower()
    return ('theory of computing' in bt_lower or
            re.search(r'\bstoc\b', bt_lower) is not None)

_FOCS_FIRST_YEAR = 1960

def format_focs_booktitle(year):
    edition = year - _FOCS_FIRST_YEAR + 1
    return (f'{year} IEEE {numeric_ordinal(edition)} Annual Symposium on '
            f'Foundations of Computer Science (FOCS)')

def is_focs(entry):
    """Fuzzy-match a bib entry as a FOCS paper."""
    bt = entry.get('booktitle', '')
    bt_lower = bt.lower()
    return ('foundations of computer science' in bt_lower or
            re.search(r'\bfocs\b', bt_lower) is not None)

def tokenize_words(text):
    """Split text into words, but keep $...$ math spans as single tokens."""
    tokens = []
    current = []
    in_math = False
    for ch in text:
        if ch == '$':
            in_math = not in_math
            current.append(ch)
        elif ch == ' ' and not in_math:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append(''.join(current))
    return tokens

def normalize_title(title):
    """Normalize a title for duplicate detection."""
    if not title:
        return ""
    t = re.sub(r'[{}]', '', title)   # Remove BibTeX braces
    t = t.lower()
    t = re.sub(r'[^\w\s]', '', t)    # Remove punctuation
    t = ' '.join(t.split())           # Collapse whitespace
    return t

# ==========================================
# Global Bibliography Cache
# ==========================================
#
# The global .bib accumulates every entry the cleaner has ever processed,
# keyed (for matching) by normalized title.  It lets a later run reuse an
# arXiv version or DOI that was resolved in an earlier run -- possibly for
# a completely different paper -- instead of asking the user again.

DEFAULT_GLOBAL_BIB = os.path.join(_SCRIPT_DIR, 'global.bib')

def plain_entry(entry):
    """Return a copy of an entry with every value as a plain string."""
    out = {}
    for k, v in entry.items():
        out[k] = v.get_value() if isinstance(v, BibDataStringExpression) else v
    return out

def load_global_bib(path):
    """
    Load the global .bib file.
    Returns (entries_list, index) where index maps normalized title -> entry.
    A missing file is not an error -- it will be created on write.
    """
    if not path or not os.path.exists(path):
        return [], {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            db = bibtexparser.load(f, parser=parser)
    except Exception as exc:
        print(f"Warning: could not read global bib '{path}': {exc}")
        return [], {}

    index = {}
    for e in db.entries:
        norm = normalize_title(e.get('title', ''))
        if norm:
            index[norm] = e
    return db.entries, index

def global_lookup(global_index, entry):
    """Return the global entry with the same normalized title, or None."""
    norm = normalize_title(entry.get('title', ''))
    return global_index.get(norm) if norm else None

def entry_is_arxiv(entry):
    """True if an entry looks like an arXiv preprint."""
    return ('arxiv' in str(entry.get('journal', '')).lower() or
            'arxiv' in str(entry.get('url', '')).lower())

def arxiv_version_of(entry):
    """Return an arXiv entry's version number (e.g. '2'), or '' if unversioned."""
    m = re.search(r'arXiv:(?:\d{4}\.\d{4,5}|[a-z\-\.]+/\d{7})v(\d+)',
                  str(entry.get('journal', '')))
    return m.group(1) if m else ''

def apply_global_entry(entry, gentry):
    """Replace an entry's fields with the global entry's, keeping the local key."""
    eid = entry['ID']
    entry.clear()
    entry.update(plain_entry(gentry))
    entry['ID'] = eid

def merge_into_global(global_entries, global_index, local_entries):
    """
    Merge processed local entries into the global bibliography.
    Existing entries (matched by normalized title) keep their global key but
    take the local entry's fields; new entries are appended.
    Returns (added, updated) counts.
    """
    added = updated = 0
    existing_ids = {e.get('ID', '') for e in global_entries}

    for entry in local_entries:
        plain = plain_entry(entry)
        norm = normalize_title(plain.get('title', ''))
        if not norm:
            continue

        gentry = global_index.get(norm)
        if gentry is not None:
            gid = gentry.get('ID', plain['ID'])
            merged = dict(plain)
            merged['ID'] = gid
            if plain_entry(gentry) != merged:
                gentry.clear()
                gentry.update(merged)
                updated += 1
        else:
            new = dict(plain)
            base = new.get('ID', 'unknown')
            key, n = base, 1
            while key in existing_ids:
                key = f'{base}_{n}'
                n += 1
            new['ID'] = key
            existing_ids.add(key)
            global_entries.append(new)
            global_index[norm] = new
            added += 1

    return added, updated

def write_global_bib(path, entries):
    """Write the global bibliography, sorted by cite key."""
    writer = BibTexWriter()
    writer.indent = '  '
    db = BibDatabase()
    db.entries = sorted(entries, key=lambda e: e.get('ID', '').lower())
    with open(path, 'w', encoding='utf-8') as f:
        f.write(writer.write(db))

# ==========================================
# 2. Logic: Word Interaction
# ==========================================

def process_word_list(words, rules_dict, context_str):
    processed = []
    updated = False
    header_printed = False

    for word in words:
        if '$' in word:
            # Math expressions are wrapped in braces so LaTeX preserves their
            # casing; rules prompts don't apply inside math mode.
            processed.append(f'{{{word}}}')
            continue

        core = word.strip(',')
        key = clean_word_key(core)
        if not key or key.isdigit():
            processed.append(word)
            continue

        if key in rules_dict:
            should_cap = rules_dict[key]
        else:
            if not header_printed:
                print(f"\n--- Title Context: ... {context_str} ... ---")
                header_printed = True

            while True:
                response = input(f"Wrap '{core}' in braces {{}}? [y/N]: ").strip().lower()
                if response in ['y', 'yes']:
                    should_cap = True
                    break
                elif response in ['n', 'no', '']:
                    should_cap = False
                    break

            rules_dict[key] = should_cap
            updated = True

        if should_cap:
            processed.append(f"{{{word}}}")
        else:
            processed.append(word)

    return processed, updated

# ==========================================
# 3. Logic: Title Splitting
# ==========================================

def process_title_interactive(title, rules_dict):
    if not title:
        return "", False

    parts = title.split(':', 1)

    # Part A: Main Title
    raw_main = parts[0].strip()
    clean_main = raw_main.replace('{', '').replace('}', '')
    main_words = tokenize_words(clean_main)

    proc_main_words, main_updated = process_word_list(main_words, rules_dict, clean_main)
    new_main = " ".join(proc_main_words)

    # Part B: Subtitle
    if len(parts) > 1:
        raw_sub = parts[1].strip()
        clean_sub = raw_sub.replace('{', '').replace('}', '')
        sub_tokens = tokenize_words(clean_sub)

        if sub_tokens:
            protected_word = sub_tokens[0]  # Protect first word of subtitle
            remainder_tokens = sub_tokens[1:]

            context_snippet = ' '.join(sub_tokens)
            proc_remainder, sub_updated = process_word_list(remainder_tokens, rules_dict, context_snippet)

            if proc_remainder:
                new_sub = f"{protected_word} {' '.join(proc_remainder)}"
            else:
                new_sub = protected_word

            return f"{new_main}: {new_sub}", (main_updated or sub_updated)
        else:
            return f"{new_main}:", main_updated
    else:
        return new_main, main_updated

# ==========================================
# 4. Logic: Deduplication
# ==========================================

def find_duplicate_groups(entries):
    """Return groups of (index, entry) sharing the same normalized title."""
    title_map = {}
    for i, entry in enumerate(entries):
        norm = normalize_title(entry.get('title', ''))
        if norm:
            title_map.setdefault(norm, []).append((i, entry))
    return [group for group in title_map.values() if len(group) >= 2]

def make_pair_key(id_a, id_b):
    """Canonical sorted pair for storage in the ignore list."""
    return sorted([id_a, id_b])

def publication_status(entry):
    """Return a short human-readable string describing where the entry is published."""
    journal = entry.get('journal', '')
    booktitle = entry.get('booktitle', '')
    doi = entry.get('doi', '')
    eprint = entry.get('eprint', '')
    url = entry.get('url', '')

    # ArXiv detection
    is_arxiv = (
        'arxiv' in journal.lower() or
        'arxiv' in url.lower() or
        'arxiv' in eprint.lower()
    )
    if is_arxiv:
        arxiv_id = extract_arxiv_id(eprint) or extract_arxiv_id(url) or extract_arxiv_id(journal)
        if arxiv_id:
            return f"arXiv:{arxiv_id}"
        return "arXiv preprint"

    if journal:
        status = journal
        if doi:
            status += f" (DOI: {doi})"
        return status

    if booktitle:
        status = f"In: {booktitle}"
        if doi:
            status += f" (DOI: {doi})"
        return status

    if doi:
        return f"DOI: {doi}"

    return "No publication info"

def deduplicate_entries(bib_database, ignored_duplicates, ignore_file, ignore_data):
    """
    Interactively resolve duplicate titles one group at a time.
    Returns (indices_to_remove, kept_to_removed) where kept_to_removed maps
    the first kept entry ID to a list of removed entry IDs.
    """
    groups = find_duplicate_groups(bib_database.entries)
    indices_to_remove = set()
    kept_to_removed = {}  # kept_id -> [removed_id, ...]

    for group in groups:
        # Skip the whole group if every pair has already been resolved
        all_resolved = all(
            make_pair_key(entry_a.get('ID', ''), entry_b.get('ID', '')) in ignored_duplicates
            for i, (_, entry_a) in enumerate(group)
            for _, entry_b in group[i + 1:]
        )
        if all_resolved:
            continue

        n = len(group)
        print(f"\n--- Possible {'Duplicate' if n == 2 else f'{n}-way Duplicate'} ---")
        for k, (_, entry) in enumerate(group, 1):
            print(f"  [{k}] Key: {entry.get('ID', 'unknown')}")
            print(f"      Title: {entry.get('title', 'No Title')}")
            print(f"      Authors: {entry.get('author', 'Unknown')[:80]}")
            print(f"      Published: {publication_status(entry)}")

        while True:
            prompt = (
                "Keep which? Enter number(s) to keep "
                f"[1–{n}, comma-separated], or Enter to keep all: "
            )
            response = input(prompt).strip()

            if response == '':
                # Keep all — record every pair so we never ask again
                for i in range(n):
                    for j in range(i + 1, n):
                        _, entry_a = group[i]
                        _, entry_b = group[j]
                        pair = make_pair_key(entry_a.get('ID', ''), entry_b.get('ID', ''))
                        if pair not in ignored_duplicates:
                            ignored_duplicates.append(pair)
                ignore_data['ignored_duplicates'] = ignored_duplicates
                save_json_file(ignore_file, ignore_data)
                print("-> Keeping all. Pairs recorded in ignore file.")
                break
            else:
                try:
                    keep_nums = {int(x.strip()) for x in response.split(',')}
                    if not all(1 <= num <= n for num in keep_nums):
                        print(f"Please enter numbers between 1 and {n}.")
                        continue
                    kept_ids = []
                    removed_ids = []
                    for k, (idx, entry) in enumerate(group, 1):
                        eid = entry.get('ID', 'unknown')
                        if k not in keep_nums:
                            indices_to_remove.add(idx)
                            removed_ids.append(eid)
                            print(f"-> Removing '{eid}'.")
                        else:
                            kept_ids.append(eid)
                    if removed_ids and kept_ids:
                        kept_to_removed[kept_ids[0]] = removed_ids
                    break
                except ValueError:
                    print("Invalid input. Please enter numbers separated by commas.")

    return indices_to_remove, kept_to_removed

# ==========================================
# 5. Main Processing Loop
# ==========================================

def process_bibtex(input_file, output_file, dupes_file=None, standardize=None,
                   global_bib=DEFAULT_GLOBAL_BIB, force_arxiv_checks=False,
                   rules_file=DEFAULT_RULES_FILE):
    try:
        sections = parse_sections(input_file)
        string_defs = extract_string_defs(input_file)
        with open(input_file, 'r', encoding='utf-8') as bibtex_file:
            parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            parser.interpolate_strings = False
            bib_database = bibtexparser.load(bibtex_file, parser=parser)
        abbrev_map = flatten_string_exprs(bib_database)
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")
        sys.exit(1)

    # Generate a dynamic ignore file name based on the input file
    input_basename = os.path.splitext(os.path.basename(input_file))[0]
    input_dir = os.path.dirname(os.path.abspath(input_file))
    ignore_file = os.path.join(input_dir, f"{input_basename}.json")

    rules = load_json_file(rules_file, default={})
    if rules:
        print(f"Title rules: {len(rules)} words known from '{rules_file}'.")
    else:
        print(f"Title rules: '{rules_file}' is new or empty; it will be created.")

    if not os.path.exists(REMOVE_FIELDS_FILE):
        save_json_file(REMOVE_FIELDS_FILE, DEFAULT_REMOVE_FIELDS)
        print(f"Created '{REMOVE_FIELDS_FILE}' with default fields to remove.")
    remove_fields = load_json_file(REMOVE_FIELDS_FILE, default=DEFAULT_REMOVE_FIELDS)
    if not isinstance(remove_fields, list):
        remove_fields = DEFAULT_REMOVE_FIELDS
    remove_fields_lower = {f.lower() for f in remove_fields}

    ignore_data = load_json_file(ignore_file, default={})
    if not isinstance(ignore_data, dict):
        ignore_data = {}
    ignored_dois = ignore_data.get('ignored_dois', [])
    ignored_duplicates = ignore_data.get('ignored_duplicates', [])
    arxiv_versions = ignore_data.get('arxiv_versions', {})
    published_entries = ignore_data.get('published_entries', {})

    arxiv_count = 0
    doi_count = 0
    url_count = 0
    global_hits = 0

    # --- Global bibliography cache ---
    global_entries, global_index = load_global_bib(global_bib)
    if global_bib:
        if global_entries:
            print(f"Global bib: {len(global_entries)} entries loaded from '{global_bib}'.")
        else:
            print(f"Global bib: '{global_bib}' is new or empty; it will be created.")

    # --- Pre-pass: Deduplication ---
    print("Checking for duplicate titles...")
    indices_to_remove, kept_to_removed = deduplicate_entries(
        bib_database, ignored_duplicates, ignore_file, ignore_data
    )
    if indices_to_remove:
        bib_database.entries = [
            e for i, e in enumerate(bib_database.entries)
            if i not in indices_to_remove
        ]
        print(f"Removed {len(indices_to_remove)} duplicate(s).")

    if kept_to_removed:
        out = dupes_file or os.path.join(
            os.path.dirname(os.path.abspath(input_file)),
            os.path.splitext(os.path.basename(input_file))[0] + '_duplicates.txt'
        )
        with open(out, 'w', encoding='utf-8') as f:
            for kept, dups in kept_to_removed.items():
                f.write(f"{kept}: {', '.join(dups)}\n")
        print(f"Duplicate log written to: {out}")

    print("Scanning bibliography...")

    for entry in bib_database.entries:
        entry_id = entry.get('ID', 'unknown')
        is_arxiv = False

        # Track if we need to save JSON files after this specific entry
        entry_rules_changed = False
        entry_ignore_changed = False

        # --- 0. Remove Configured Fields ---
        for key in [k for k in list(entry.keys()) if k.lower() in remove_fields_lower]:
            del entry[key]

        # --- A. Conversion Logic (@misc -> @article) ---
        if entry.get('ENTRYTYPE', '').lower() == 'misc':
            url = entry.get('url', '')
            doi = entry.get('doi', '')
            eprint = entry.get('eprint', '')
            archiveprefix = entry.get('archiveprefix', '')
            is_arxiv_misc = (
                'arxiv' in url.lower() or
                'arxiv' in doi.lower() or
                'arxiv' in archiveprefix.lower() or
                bool(extract_arxiv_id(eprint))
            )
            if is_arxiv_misc:
                arxiv_id = (extract_arxiv_id(eprint) or
                            extract_arxiv_id(doi) or
                            extract_arxiv_id(url))
                if arxiv_id:
                    entry['ENTRYTYPE'] = 'article'
                    entry['journal'] = (
                        f"arXiv preprint \\href{{http://arxiv.org/abs/{arxiv_id}}}"
                        f"{{arXiv:{arxiv_id}}}"
                    )
                    for field in _ARXIV_FIELDS:
                        entry.pop(field, None)
                    arxiv_count += 1
                    is_arxiv = True

        # --- A2. ArXiv Detection ---
        # Only the journal/url fields indicate the entry ITSELF is an arXiv
        # preprint. A published entry (e.g. @inproceedings with a booktitle)
        # may still carry eprint/archiveprefix to cross-reference its arXiv
        # version, and that should not turn it into an arXiv-only entry.
        if not is_arxiv:
            if 'arxiv' in entry.get('journal', '').lower() or \
               'arxiv' in entry.get('url', '').lower():
                is_arxiv = True

        # --- A3. ArXiv Journal Reformatting ---
        # Catches @article entries with a raw arXiv journal string (no \href)
        # e.g. journal = {arXiv:1911.05858 [cs, math]}
        if is_arxiv and r'\href' not in entry.get('journal', ''):
            arxiv_id = (extract_arxiv_id(entry.get('eprint', '')) or
                        extract_arxiv_id(entry.get('url', '')) or
                        extract_arxiv_id(entry.get('journal', '')))
            if arxiv_id:
                entry['journal'] = (
                    f"arXiv preprint \\href{{http://arxiv.org/abs/{arxiv_id}}}"
                    f"{{arXiv:{arxiv_id}}}"
                )
                for field in _ARXIV_FIELDS:
                    entry.pop(field, None)
                arxiv_count += 1

        # --- A4. ArXiv Version / Published Update ---
        if is_arxiv and r'\href' in entry.get('journal', ''):
            gentry = global_lookup(global_index, entry)
            handled = False

            # Consult caches unless the user demanded a fresh check of every
            # arXiv entry.  Global bib wins: it is shared across projects.
            if not force_arxiv_checks:
                if gentry is not None and not entry_is_arxiv(gentry):
                    # The global bib knows this preprint was published
                    apply_global_entry(entry, gentry)
                    is_arxiv = False
                    handled = True
                    global_hits += 1
                    print(f"-> '{entry_id}': published version from global bib.")
                elif gentry is not None and arxiv_version_of(gentry):
                    # Still a preprint at a version we already recorded
                    entry['journal'] = gentry.get('journal', entry['journal'])
                    handled = True
                    global_hits += 1
                elif entry_id in published_entries:
                    # Restore saved published fields, preserving the original key
                    saved = published_entries[entry_id]
                    entry.clear()
                    entry.update(saved)
                    entry['ID'] = entry_id
                    is_arxiv = False
                    handled = True
                elif entry_id in arxiv_versions:
                    version = arxiv_versions[entry_id]
                    handled = True
                    if version:
                        id_match = re.search(r'arXiv:(\d{4}\.\d{4,5}|[a-z\-\.]+/\d{7})', entry['journal'])
                        if id_match:
                            base_id = id_match.group(1)
                            vid = f"{base_id}v{version}"
                            entry['journal'] = (
                                f"arXiv preprint \\href{{http://arxiv.org/abs/{vid}}}"
                                f"{{arXiv:{vid}}}"
                            )

            if not handled:
                print(f"\nEntry '{entry_id}': {entry.get('title', 'No Title')}")
                print("Options: enter an arXiv version number (e.g. 2), paste a BibTeX entry")
                print("for the published version (starting with '@'), or press Enter to leave unversioned.")
                first_line = input("> ").strip()

                if first_line.startswith('@'):
                    # User is pasting a published BibTeX entry
                    raw = read_bibtex_paste(first_line)
                    parsed = parse_bibtex_entry(raw)
                    if parsed:
                        parsed['ID'] = entry_id
                        entry.clear()
                        entry.update(parsed)
                        is_arxiv = False
                        # Save all fields except ID (we always override ID on restore)
                        to_save = {k: v for k, v in parsed.items() if k != 'ID'}
                        published_entries[entry_id] = to_save
                        ignore_data['published_entries'] = published_entries
                        entry_ignore_changed = True
                        print(f"-> Updated '{entry_id}' to published version.")
                    else:
                        print("-> Could not parse BibTeX entry; leaving as arXiv.")
                        arxiv_versions[entry_id] = ''
                        ignore_data['arxiv_versions'] = arxiv_versions
                        entry_ignore_changed = True
                else:
                    version = first_line
                    if version.lower().startswith('v'):
                        version = version[1:]
                    arxiv_versions[entry_id] = version
                    entry_ignore_changed = True
                    if version:
                        id_match = re.search(r'arXiv:(\d{4}\.\d{4,5}|[a-z\-\.]+/\d{7})', entry['journal'])
                        if id_match:
                            base_id = id_match.group(1)
                            vid = f"{base_id}v{version}"
                            entry['journal'] = (
                                f"arXiv preprint \\href{{http://arxiv.org/abs/{vid}}}"
                                f"{{arXiv:{vid}}}"
                            )

        # --- B. Missing DOI/URL Logic ---
        if not is_arxiv and 'doi' not in entry:
            gentry = global_lookup(global_index, entry)
            gdoi = str(gentry.get('doi', '')).strip() if gentry else ''
            gurl = str(gentry.get('url', '')).strip() if gentry else ''

            if gdoi or gurl:
                # The global bib already has an identifier for this paper
                if gdoi:
                    apply_doi_to_entry(entry, clean_doi_value(gdoi))
                    shown = entry.get('doi') or entry.get('url')
                    print(f"-> '{entry_id}': DOI from global bib: {shown}")
                else:
                    entry['url'] = gurl
                    print(f"-> '{entry_id}': URL from global bib.")
                global_hits += 1
            elif entry_id not in ignored_dois:
                current_url = entry.get('url', '')
                print(f"\nEntry '{entry_id}' is missing a DOI.")
                print(f"Title: {entry.get('title', 'No Title')}")
                if current_url:
                    print(f"Current URL: {current_url}")
                value = input("Enter DOI or URL [Enter to skip]: ").strip()

                if value:
                    cleaned = clean_doi_value(value)
                    if cleaned != value or not value.startswith('http'):
                        # doi.org URL (cleaned differs) or bare DOI (no http prefix)
                        field = apply_doi_to_entry(entry, cleaned)
                        if field == 'url':
                            print(f"-> ACM placeholder DOI; set URL: {entry['url']}")
                        else:
                            print(f"-> Added DOI: {entry['doi']}")
                        doi_count += 1
                    else:
                        entry['url'] = value
                        print(f"-> Added URL.")
                        url_count += 1
                    ignored_dois.append(entry_id)
                    entry_ignore_changed = True
                elif current_url:
                    print("-> Keeping existing URL.")
                    ignored_dois.append(entry_id)
                    entry_ignore_changed = True
                else:
                    print("-> No identifier provided. Ignoring entry.")
                    ignored_dois.append(entry_id)
                    entry_ignore_changed = True

        # --- C. Clean Existing DOI ---
        if 'doi' in entry and not is_arxiv:
            cleaned = clean_doi_value(entry['doi'])
            apply_doi_to_entry(entry, cleaned)

        # --- C2. Conference-Specific Booktitle Cleanup ---
        try:
            year = int(entry.get('year', ''))
            if is_soda(entry):
                entry['booktitle'] = format_soda_booktitle(year)
            elif is_stoc(entry):
                entry['booktitle'] = format_stoc_booktitle(year)
            elif is_focs(entry):
                entry['booktitle'] = format_focs_booktitle(year)
        except (ValueError, TypeError):
            pass

        # --- D. Interactive Title Logic ---
        if 'title' in entry:
            entry['title'] = ' '.join(entry['title'].split())
            new_title, changed = process_title_interactive(entry['title'], rules)
            entry['title'] = new_title
            if changed:
                entry_rules_changed = True

        # --- E. Save Progress As You Go ---
        if entry_rules_changed or entry_ignore_changed:
            save_json_file(rules_file, rules)
            ignore_data['ignored_dois'] = ignored_dois
            ignore_data['ignored_duplicates'] = ignored_duplicates
            ignore_data['arxiv_versions'] = arxiv_versions
            ignore_data['published_entries'] = published_entries
            save_json_file(ignore_file, ignore_data)

    restore_string_exprs(bib_database, abbrev_map)

    # --- Key Renames: deduplication + optional standardization ---
    # Collect removed-key → kept-key mappings from deduplication
    key_renames = {}  # old_id -> new_id
    for kept, removed_list in kept_to_removed.items():
        for removed in removed_list:
            key_renames[removed] = kept

    if standardize:
        std_map = standardize_keys(bib_database.entries, standardize)
        # Apply renames to entry IDs and update abbrev_map keys
        for entry in bib_database.entries:
            old_id = entry['ID']
            new_id = std_map.get(old_id, old_id)
            if new_id != old_id:
                entry['ID'] = new_id
                key_renames[old_id] = new_id
        # Section key lists need updating too
        sections = [
            (name, [std_map.get(k, k) for k in keys])
            for name, keys in sections
        ]
        print(f"Standardized {sum(1 for o, n in std_map.items() if o != n)} key(s) to '{standardize}' style.")

    if key_renames:
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(input_file)),
            os.path.splitext(os.path.basename(input_file))[0] + '_rename_keys.sh'
        )
        write_rename_script(key_renames, script_path)

    # --- Update the global bibliography with everything we just processed ---
    if global_bib:
        added, updated = merge_into_global(global_entries, global_index,
                                           bib_database.entries)
        try:
            write_global_bib(global_bib, global_entries)
            print(f"Global bib updated: {added} added, {updated} updated "
                  f"({len(global_entries)} total) -> {global_bib}")
        except OSError as exc:
            print(f"Warning: could not write global bib '{global_bib}': {exc}")

    # Save final bibliography, preserving %%% section comments
    writer = BibTexWriter()
    writer.indent = '  '
    entry_dict = {e['ID']: e for e in bib_database.entries}

    def render_entry(e):
        tmp = BibDatabase()
        tmp.entries = [e]
        return writer.write(tmp).strip()

    chunks = list(string_defs)  # @STRING defs go first
    written = set()

    for section_name, keys in sections:
        section_entries = [entry_dict[k] for k in keys if k in entry_dict]
        if not section_entries:
            continue
        if section_name is not None:
            chunks.append(f'%%% {section_name}')
        for e in section_entries:
            chunks.append(render_entry(e))
            written.add(e['ID'])

    # Append any entries not captured by a section
    for e in bib_database.entries:
        if e['ID'] not in written:
            chunks.append(render_entry(e))

    with open(output_file, 'w', encoding='utf-8') as bibtex_file:
        bibtex_file.write('\n\n'.join(chunks) + '\n')

    print(f"\nDone! Output saved to: {output_file}")
    print(f"Title rules are safely stored in '{rules_file}'.")
    print(f"Ignored entries for this paper are stored in '{ignore_file}'.")
    print(f"Stats: {arxiv_count} ArXiv, {doi_count} DOIs, {url_count} URLs added, "
          f"{global_hits} resolved from global bib.")

_DESCRIPTION = """\
Clean and normalize a BibTeX bibliography.

The cleaner walks every entry and, interactively where needed:
  * converts arXiv @misc entries to @article with a linked arXiv journal
    field, and asks whether a preprint has a newer version or has since
    been published (paste the published BibTeX to replace it)
  * fills in a missing DOI or URL
  * rewrites SODA / STOC / FOCS booktitles to their canonical form
  * asks which title words need {brace} protection, remembering answers
  * offers to remove duplicate entries
  * preserves @STRING abbreviations and %%% section comments

Answers are remembered so you are never asked twice. Two caches are shared
by every bibliography you clean, and each can be pointed elsewhere for a
single run:

  global.bib        entries resolved before (arXiv versions, DOIs),
                    matched by title so it works across projects
                    --global FILE   /  --no-global
  title_rules.json  which title words need {brace} protection
                    --rules FILE

Decisions that only make sense for one bibliography -- which duplicate to
keep, which entries to stop asking about -- live alongside the input as
<input>.json.
"""

_EPILOG = """\
examples:
  # Clean refs.bib into cleaned.bib
  %(prog)s refs.bib cleaned.bib

  # Also renumber every cite key to alpha style (CET+25)
  %(prog)s refs.bib cleaned.bib --standardize alpha

  # Re-check every arXiv preprint for a new version or publication
  %(prog)s refs.bib cleaned.bib --force_arxiv_checks

  # Use project-specific caches instead of the shared ones
  %(prog)s refs.bib cleaned.bib --global ~/papers/global.bib \\
                               --rules  ~/papers/title_rules.json

files written:
  <output>                   the cleaned bibliography
  <input>.json               per-file memory of your answers
  <input>_duplicates.txt     kept-key: removed-key, ... (only if duplicates)
  <input>_rename_keys.sh     find-replace script (only if keys changed)
  global.bib                 shared cache of every entry ever processed
  title_rules.json           shared title-casing rules
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'input', metavar='INPUT.bib',
        help='BibTeX file to clean.')
    parser.add_argument(
        'output', nargs='?', metavar='OUTPUT.bib',
        help='Where to write the cleaned bibliography '
             '(default: clean_output.bib in the current directory).')
    parser.add_argument(
        '--standardize', choices=['alpha', 'namedateword'], default=None,
        metavar='STYLE',
        help='Rewrite every cite key in a uniform style, then emit a '
             'find-replace script for your .tex files. '
             "'alpha' gives Che25, CE25, CET25, CETW25, CET+25 (initials by "
             "author count + 2-digit year); 'namedateword' gives "
             'chen2025randomly (first author, year, first title word). '
             'Default: keys are left alone.')
    parser.add_argument(
        '--global', dest='global_bib', metavar='FILE',
        default=DEFAULT_GLOBAL_BIB,
        help='Shared bibliography cache consulted before asking you about an '
             'arXiv version or a missing DOI, and updated with every entry '
             'processed. Matching is by normalized title, so it works across '
             'projects with different cite keys. '
             f'Default: {DEFAULT_GLOBAL_BIB}')
    parser.add_argument(
        '--no-global', dest='global_bib', action='store_const', const=None,
        help='Do not read or write the global bibliography cache.')
    parser.add_argument(
        '--rules', dest='rules_file', metavar='FILE',
        default=DEFAULT_RULES_FILE,
        help='Shared record of which title words need {brace} protection. '
             'Consulted before asking about a word and updated with every '
             'answer, so each word is only ever asked about once across all '
             'your bibliographies. '
             f'Default: {DEFAULT_RULES_FILE}')
    parser.add_argument(
        '--force_arxiv_checks', action='store_true',
        help='Ask about every arXiv preprint even when the global cache or '
             'this file\'s .json already records a version. Use this to sweep '
             'a bibliography for preprints that have since been published. '
             'Anything you update is written back to the global cache.')
    parser.add_argument(
        '--dupes', metavar='FILE',
        help='Where to write the duplicate log, one "kept: removed, removed" '
             'line per group (default: <input>_duplicates.txt).')
    args = parser.parse_args()

    out_path = args.output if args.output else 'clean_output.bib'
    process_bibtex(args.input, out_path,
                   dupes_file=args.dupes,
                   standardize=args.standardize,
                   global_bib=args.global_bib,
                   force_arxiv_checks=args.force_arxiv_checks,
                   rules_file=args.rules_file)
