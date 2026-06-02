#!/usr/bin/env python

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
import re
import argparse
import sys
import json
import os

RULES_FILE = 'title_rules.json'

# Fields that are arXiv-specific and should be removed when reformatting
_ARXIV_FIELDS = ('eprint', 'archiveprefix', 'primaryclass', 'publisher',
                 'number', 'urldate', 'url', 'doi', 'howpublished')

# ==========================================
# 1. Helper Functions
# ==========================================

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
    Returns the set of entry indices to remove.
    """
    groups = find_duplicate_groups(bib_database.entries)
    indices_to_remove = set()

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
                    for k, (idx, entry) in enumerate(group, 1):
                        if k not in keep_nums:
                            indices_to_remove.add(idx)
                            print(f"-> Removing '{entry.get('ID', 'unknown')}'.")
                    break
                except ValueError:
                    print("Invalid input. Please enter numbers separated by commas.")

    return indices_to_remove

# ==========================================
# 5. Main Processing Loop
# ==========================================

def process_bibtex(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as bibtex_file:
            parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            bib_database = bibtexparser.load(bibtex_file, parser=parser)
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")
        sys.exit(1)

    # Generate a dynamic ignore file name based on the input file
    input_basename = os.path.splitext(os.path.basename(input_file))[0]
    ignore_file = f"{input_basename}.json"

    rules = load_json_file(RULES_FILE, default={})
    ignore_data = load_json_file(ignore_file, default={})
    if not isinstance(ignore_data, dict):
        ignore_data = {}
    ignored_dois = ignore_data.get('ignored_dois', [])
    ignored_duplicates = ignore_data.get('ignored_duplicates', [])
    arxiv_versions = ignore_data.get('arxiv_versions', {})

    arxiv_count = 0
    doi_count = 0
    url_count = 0

    # --- Pre-pass: Deduplication ---
    print("Checking for duplicate titles...")
    indices_to_remove = deduplicate_entries(
        bib_database, ignored_duplicates, ignore_file, ignore_data
    )
    if indices_to_remove:
        bib_database.entries = [
            e for i, e in enumerate(bib_database.entries)
            if i not in indices_to_remove
        ]
        print(f"Removed {len(indices_to_remove)} duplicate(s).")

    print("Scanning bibliography...")

    for entry in bib_database.entries:
        entry_id = entry.get('ID', 'unknown')
        is_arxiv = False

        # Track if we need to save JSON files after this specific entry
        entry_rules_changed = False
        entry_ignore_changed = False

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
        if not is_arxiv:
            if 'arxiv' in entry.get('journal', '').lower() or \
               'arxiv' in entry.get('url', '').lower() or \
               'arxiv' in entry.get('eprint', '').lower() or \
               'arxiv' in entry.get('archiveprefix', '').lower():
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

        # --- A4. ArXiv Version ---
        if is_arxiv and r'\href' in entry.get('journal', ''):
            if entry_id in arxiv_versions:
                version = arxiv_versions[entry_id]
            else:
                print(f"\nEntry '{entry_id}': {entry.get('title', 'No Title')}")
                version = input("arXiv version (e.g. 2, or press Enter to leave unversioned): ").strip()
                if version.lower().startswith('v'):
                    version = version[1:]  # store bare number
                arxiv_versions[entry_id] = version
                entry_ignore_changed = True

            if version:
                # Reconstruct journal with versioned ID
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
            save_json_file(ignore_file, ignore_data)

    # Save final bibliography
    writer = BibTexWriter()
    writer.indent = '  '
    with open(output_file, 'w', encoding='utf-8') as bibtex_file:
        bibtex_file.write(writer.write(bib_database))

    print(f"\nDone! Output saved to: {output_file}")
    print(f"Title rules are safely stored in '{RULES_FILE}'.")
    print(f"Ignored entries for this paper are stored in '{ignore_file}'.")
    print(f"Stats: {arxiv_count} ArXiv, {doi_count} DOIs, {url_count} URLs added.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input bib file')
    parser.add_argument('output', nargs='?', help='Output bib file')
    args = parser.parse_args()

    out_path = args.output if args.output else 'clean_output.bib'
    process_bibtex(args.input, out_path)
