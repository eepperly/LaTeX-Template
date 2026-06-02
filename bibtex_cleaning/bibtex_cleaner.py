#!/usr/bin/env python

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
import re
import argparse
import sys
import json
import os

RULES_FILE = 'title_rules.json'

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

def deduplicate_entries(bib_database, ignored_duplicates, ignore_file, ignore_data):
    """
    Interactively resolve duplicate titles.
    Returns the set of entry indices to remove.
    """
    groups = find_duplicate_groups(bib_database.entries)
    indices_to_remove = set()

    for group in groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                idx_a, entry_a = group[i]
                idx_b, entry_b = group[j]
                id_a = entry_a.get('ID', 'unknown')
                id_b = entry_b.get('ID', 'unknown')

                pair = make_pair_key(id_a, id_b)
                if pair in ignored_duplicates:
                    continue  # Already decided to keep both

                print(f"\n--- Possible Duplicate ---")
                print(f"  [1] Key: {id_a}")
                print(f"      Title: {entry_a.get('title', 'No Title')}")
                print(f"      Authors: {entry_a.get('author', 'Unknown')[:80]}")
                print(f"  [2] Key: {id_b}")
                print(f"      Title: {entry_b.get('title', 'No Title')}")
                print(f"      Authors: {entry_b.get('author', 'Unknown')[:80]}")

                while True:
                    response = input("Keep [1], [2], or [B]oth (default: both)? ").strip().lower()
                    if response == '1':
                        indices_to_remove.add(idx_b)
                        print(f"-> Keeping '{id_a}', removing '{id_b}'.")
                        break
                    elif response == '2':
                        indices_to_remove.add(idx_a)
                        print(f"-> Keeping '{id_b}', removing '{id_a}'.")
                        break
                    elif response in ('b', 'both', ''):
                        ignored_duplicates.append(pair)
                        ignore_data['ignored_duplicates'] = ignored_duplicates
                        save_json_file(ignore_file, ignore_data)
                        print(f"-> Keeping both. Pair recorded in ignore file.")
                        break

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
            if 'arxiv' in url.lower() or 'arxiv' in doi.lower():
                arxiv_id = extract_arxiv_id(doi) or extract_arxiv_id(url)
                if arxiv_id:
                    entry['ENTRYTYPE'] = 'article'
                    entry['journal'] = (
                        f"arXiv preprint \\href{{http://arxiv.org/abs/{arxiv_id}}}"
                        f"{{arXiv:{arxiv_id}}}"
                    )
                    entry.pop('url', None)
                    entry.pop('doi', None)
                    entry.pop('howpublished', None)
                    arxiv_count += 1
                    is_arxiv = True

        # --- A2. ArXiv Safety Check ---
        if not is_arxiv:
            if 'arxiv' in entry.get('journal', '').lower() or \
               'arxiv' in entry.get('url', '').lower() or \
               'arxiv' in entry.get('eprint', '').lower():
                is_arxiv = True

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
