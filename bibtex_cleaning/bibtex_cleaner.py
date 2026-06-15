#!/usr/bin/env python

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase
import re
import argparse
import sys
import json
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

RULES_FILE = os.path.join(_SCRIPT_DIR, 'title_rules.json')
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

def clean_word_key(word):
    return re.sub(r'[^\w]', '', word)

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
# 2. Logic: Word Interaction
# ==========================================

def process_word_list(words, rules_dict, context_str):
    processed = []
    updated = False
    header_printed = False

    for word in words:
        key = clean_word_key(word)
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
                response = input(f"Wrap '{word}' in braces {{}}? [y/N]: ").strip().lower()
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
    main_words = clean_main.split()

    proc_main_words, main_updated = process_word_list(main_words, rules_dict, clean_main)
    new_main = " ".join(proc_main_words)

    # Part B: Subtitle
    if len(parts) > 1:
        raw_sub = parts[1].strip()
        sub_words = raw_sub.split()

        if sub_words:
            protected_word = sub_words[0]  # Protect first word
            remainder_words = sub_words[1:]

            clean_remainder = [w.replace('{', '').replace('}', '') for w in remainder_words]
            context_snippet = f"{protected_word} {' '.join(clean_remainder)}"
            proc_remainder, sub_updated = process_word_list(clean_remainder, rules_dict, context_snippet)

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

def process_bibtex(input_file, output_file, dupes_file=None):
    try:
        sections = parse_sections(input_file)
        with open(input_file, 'r', encoding='utf-8') as bibtex_file:
            parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            bib_database = bibtexparser.load(bibtex_file, parser=parser)
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")
        sys.exit(1)

    # Generate a dynamic ignore file name based on the input file
    input_basename = os.path.splitext(os.path.basename(input_file))[0]
    input_dir = os.path.dirname(os.path.abspath(input_file))
    ignore_file = os.path.join(input_dir, f"{input_basename}.json")

    rules = load_json_file(RULES_FILE, default={})

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
            if entry_id in published_entries:
                # Restore saved published fields, preserving the original key
                saved = published_entries[entry_id]
                entry.clear()
                entry.update(saved)
                entry['ID'] = entry_id
                is_arxiv = False
            elif entry_id in arxiv_versions:
                version = arxiv_versions[entry_id]
                if version:
                    id_match = re.search(r'arXiv:(\d{4}\.\d{4,5}|[a-z\-\.]+/\d{7})', entry['journal'])
                    if id_match:
                        base_id = id_match.group(1)
                        vid = f"{base_id}v{version}"
                        entry['journal'] = (
                            f"arXiv preprint \\href{{http://arxiv.org/abs/{vid}}}"
                            f"{{arXiv:{vid}}}"
                        )
            else:
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
            if entry_id not in ignored_dois:
                print(f"\nEntry '{entry_id}' is missing a DOI.")
                print(f"Title: {entry.get('title', 'No Title')}")

                # 1. Ask for DOI
                new_doi = input("Enter DOI (or press Enter to skip): ").strip()

                if new_doi:
                    # Case 1: DOI provided
                    entry['doi'] = clean_doi_value(new_doi)
                    entry.pop('url', None)
                    print(f"-> Added DOI: {entry['doi']}")
                    doi_count += 1
                else:
                    # Case 2: DOI skipped -> Ask for URL
                    current_url = entry.get('url', '')
                    prompt = "Enter URL"
                    if current_url:
                        prompt += f" (current: {current_url})"
                    prompt += " [Enter to skip]: "

                    new_url = input(prompt).strip()

                    if new_url:
                        entry['url'] = new_url
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
            old_doi = entry['doi']
            cleaned = clean_doi_value(old_doi)
            if old_doi != cleaned:
                entry['doi'] = cleaned
            if 'url' in entry:
                entry.pop('url')

        # --- D. Interactive Title Logic ---
        if 'title' in entry:
            new_title, changed = process_title_interactive(entry['title'], rules)
            entry['title'] = new_title
            if changed:
                entry_rules_changed = True

        # --- E. Save Progress As You Go ---
        if entry_rules_changed or entry_ignore_changed:
            save_json_file(RULES_FILE, rules)
            ignore_data['ignored_dois'] = ignored_dois
            ignore_data['ignored_duplicates'] = ignored_duplicates
            ignore_data['arxiv_versions'] = arxiv_versions
            ignore_data['published_entries'] = published_entries
            save_json_file(ignore_file, ignore_data)

    # Save final bibliography, preserving %%% section comments
    writer = BibTexWriter()
    writer.indent = '  '
    entry_dict = {e['ID']: e for e in bib_database.entries}

    def render_entry(e):
        tmp = BibDatabase()
        tmp.entries = [e]
        return writer.write(tmp).strip()

    chunks = []
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
    print(f"Title rules are safely stored in '{RULES_FILE}'.")
    print(f"Ignored entries for this paper are stored in '{ignore_file}'.")
    print(f"Stats: {arxiv_count} ArXiv, {doi_count} DOIs, {url_count} URLs added.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input bib file')
    parser.add_argument('output', nargs='?', help='Output bib file')
    parser.add_argument('--dupes', metavar='FILE', help='File to write duplicate log (default: <input>_duplicates.txt)')
    args = parser.parse_args()

    out_path = args.output if args.output else 'clean_output.bib'
    process_bibtex(args.input, out_path, dupes_file=args.dupes)
