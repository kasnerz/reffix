#!/usr/bin/env python3

"""
===========
Reffix
===========
Fix common errors in BibTeX bibliography files:
- missing URLs
- incorrect capitalization
- using arXiv preprints instead of published version

The package uses the DBLP API: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
Use with caution not to overload the servers. Please note that the API may also change in future.

The package tries to use a conservative approach:
- no references are deleted
- if possible, the matching reference is selected
"""

import os
import argparse
import logging
import requests
import bibtexparser
import titlecase
import re
import pprint
from bibtexparser.bparser import BibTexParser


logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO, datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

dblp_api = "https://dblp.org/search/publ/api"

def get_dblp_results(title):
    params = {
        "format" : "bib",
        "q" : title
    }
    res = requests.get(dblp_api, params=params)

    try:
        if res.status_code == 200:
            bp = BibTexParser(interpolate_strings=False)
            bib = bp.parse(res.text)
            return bib.entries
    except Exception as e:
        logger.exception(e)
        raise e

def protect_titlecase(title):
    words = []

    for word in title.split():
        if word[0].isupper():
            words.append(r"{" + word + r"}")
        else:
            words.append(word)

    return " ".join(words)


def to_titlecase(title):
    new_title = titlecase.titlecase(title)
    return protect_titlecase(new_title)


def get_equivalent_entry(entries, orig_entry):
    for entry in entries:
        year_match = ("year" in entry and "year" in orig_entry and entry["year"] == orig_entry["year"])
        pages_match = ("pages" in entry and "pages" in orig_entry and entry["pages"] == orig_entry["pages"])

        if year_match and pages_match:
            return entry

        # venue of one of the entries matches or is a substring of the other entry
        venue_match = ("booktitle" in entry and "booktitle" in orig_entry and 
                (entry["booktitle"] in orig_entry["booktitle"] or orig_entry["booktitle"] in entry["booktitle"]))

        if year_match and venue_match:
            return entry

    return None


def get_best_entry(entries, orig_entry):
    if not entries:
        return None

    equivalent_entry = get_equivalent_entry(entries, orig_entry)

    if equivalent_entry:
        return equivalent_entry

    # assuming that the results are sorted by relevancy
    # logger.info(f"[INFO] Equivalent entry not found, using the most relevant result: {orig_entry['title']}")
    return entries[0]


def is_arxiv(entry):
    return entry.get("journal", None) == "CoRR" \
        or entry.get("eprinttype", None) == "arXiv" \
        or "arxiv" in entry.get("url", "")


def select_entry(entries, orig_entry, replace_arxiv):
    if not entries:
        return None

    # keep only hits with matching title, ignoring casing and non-alpha numeric characters
    # (some titles are returned with trailing dot, dashes may be inconsistent, etc.)
    entries = [entry for entry in entries if re.sub(r"[^0-9a-zA-Z]+", "", 
        entry["title"]).lower() == re.sub(r"[^0-9a-zA-Z]+", "", orig_entry["title"]).lower()]

    if replace_arxiv:
        # split into arxiv and non-arxiv publications
        entries_other = [entry for entry in entries if not is_arxiv(entry)]
        entries_arxiv = [entry for entry in entries if is_arxiv(entry)]

        if entries_other:
            entry = get_best_entry(entries_other, orig_entry)
        else:
            # logger.info(f"[INFO] Found arXiv entry only: {orig_entry['title']}")
            entry = get_best_entry(entries_arxiv, orig_entry)
    else:
        entry = get_best_entry(entries, orig_entry)

    return entry


def fix_reflabel(entry, orig_entry):
    entry["ID"] = orig_entry["ID"]
    return entry


def main(in_file, out_file, replace_arxiv, force_capitalization, interact):
    with open(in_file) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)

        logger.info("[INFO] Bibliography file loaded successfully.")

        for i in range(len(bib_database.entries)):
            orig_entry = bib_database.entries[i]
            title = orig_entry["title"]
            hits = get_dblp_results(title)
            entry = select_entry(hits, orig_entry=orig_entry, replace_arxiv=replace_arxiv)

            if entry:
                entry = fix_reflabel(entry, orig_entry)
                entry["title"] = protect_titlecase(entry["title"])

                orig_str = pprint.pformat(orig_entry, indent=4)
                new_str = pprint.pformat(entry, indent=4)
                conf = "y"

                if interact:
                    logging.info(f"\n<=== Original entry:\n {orig_str}\n ===> New entry:\n {new_str}")
                    while True:
                        conf = input("Replace the entry (y/n)?: ").lower()
                        if conf == "y" or conf == "n":
                            break
                        print("Please accept (y) or reject (n) the change.")
                else:
                    logging.info(f"[UPDATE] {title}")
                if conf == "y":
                    bib_database.entries[i] = entry
            else:
                logging.info(f"[KEEP] No result found, keeping the original entry: {title}")

                if force_capitalization:
                    new_title = to_titlecase(title)

                    if new_title != title:
                        bib_database.entries[i]["title"] = new_title
                        logger.info(f"[INFO] Using custom titlecasing: {title} -> {new_title}")


    with open(out_file, "w") as f:
        bibtex_str = bibtexparser.dump(bib_database, f)
        logger.info(f"Saving into {out_file}.")
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("in_file", type=str, help="Bibliography file")
    parser.add_argument("-o", "--out", type=str, default=None, help="Output file")
    parser.add_argument("-a", "--replace_arxiv", action="store_true", help="")
    parser.add_argument("-t", "--titlecase", action="store_true", help="Use `titlecase` to fix titlecasing for references not found on DBLP")
    parser.add_argument("-i", "--interact", action="store_true", help="Interactive mode - confirm every change")

    args = parser.parse_args()
    logger.info(args)

    if args.out is None:
        if args.in_file.endswith(".bib"):
            out_file = args.in_file.replace(".bib", ".fixed.bib")
        else:
            out_file = args.in_file + "_fixed"
    else:
        out_file = args.out

    main(
        in_file=args.in_file, 
        out_file=out_file, 
        replace_arxiv=args.replace_arxiv, 
        force_capitalization=args.titlecase,
        interact=args.interact
    )