#!/usr/bin/env python3

"""
===========
Reffix
===========
Fix common errors in BibTeX bibliography files:
- missing URLs
- incorrect titlecase
- using arXiv preprints instead of published version

The package uses the DBLP API: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
Make sure not to overload the DBLP servers. Please note that the API may change in future.

The package uses a conservative approach:
- if possible, the matching reference is selected
- no references are deleted
- papers are updated only if the title and at least one of the authors match
"""

import os
import argparse
import logging
import requests
import bibtexparser
import titlecase
import re
import pprint
import unidecode

from bibtexparser.bparser import BibTexParser
import bibtexparser.customization as bc
from termcolor import colored

logging.basicConfig(format="%(message)s", level=logging.INFO, datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

dblp_api = "https://dblp.org/search/publ/api"


def get_dblp_results(query):
    params = {"format": "bib", "q": query}
    res = requests.get(dblp_api, params=params)
    try:
        if res.status_code == 200:
            # new instance needs to be created to use a new database
            bp = BibTexParser(interpolate_strings=False, common_strings=True)
            bib = bp.parse(res.text)

            return bib.entries
    except Exception as e:
        logger.exception(e)
        raise e


def protect_titlecase(title):
    # wrap the capital letters in curly braces to protect them
    # see https://tex.stackexchange.com/questions/10772/bibtex-loses-capitals-when-creating-bbl-file
    words = []

    for word in title.split():
        if word[0] == "{" and word[-1] == "}":
            # already (presumably) protected
            words.append(word)
        else:
            protect = False
            subwords = word.split("-")
            for sw in subwords:
                if len(subwords) > 1 and len(sw) == 1:
                    # 3-D, U-Net
                    protect = True
                    break
                if any(l.isupper() for l in sw[1:]):
                    # Only considers capitals after the first letter
                    # Mip-NeRF: protect
                    # Spatially-Varying: don't protect
                    protect = True
                    break
            if protect:
                # leave the : out of the protection
                if word[-1] == ":":
                    words.append(r"{" + word[:-1] + r"}:")
                else:
                    words.append(r"{" + word + r"}")
            else:
                words.append(word)

    return " ".join(words)


def to_titlecase(title):
    # use the titlecase package to capitalize first letters (note that this may not be accurate)
    return titlecase.titlecase(title)


def is_equivalent(entry, orig_entry):
    # a bit more bulletproof (because of variability in the names of venues): year and pages match
    year_match = "year" in entry and "year" in orig_entry and entry["year"] == orig_entry["year"]
    pages_match = "pages" in entry and "pages" in orig_entry and entry["pages"] == orig_entry["pages"]

    if year_match and pages_match:
        return True

    # venue of one of the entries matches or is a substring of the other entry
    venue_match = (
        "booktitle" in entry
        and "booktitle" in orig_entry
        and (entry["booktitle"] in orig_entry["booktitle"] or orig_entry["booktitle"] in entry["booktitle"])
    )

    if year_match and venue_match:
        return True

    return False


def get_equivalent_entry(entries, orig_entry):
    for entry in entries:
        if is_equivalent(entry, orig_entry):
            return entry

    return None


def get_best_entry(entries, orig_entry):
    # return the most appropriate result given a list of results and the original entry
    if not entries:
        return None

    if len(entries) == 1:
        return entries[0]

    equivalent_entry = get_equivalent_entry(entries, orig_entry)
    if equivalent_entry:
        return equivalent_entry

    # sorting the results by year (newer is better) and by the number of entries (more is better)
    entries.sort(key=lambda x: (int(x.get("year", 0)), len(x.keys())))

    return entries[-1]


def is_arxiv(entry):
    # find if the entry comes from arXiv
    journal = entry.get("journal", "").lower()
    eprinttype = entry.get("eprinttype", "").lower()
    url = entry.get("url", "").lower()
    return "arxiv" in journal + eprinttype + url


def is_titlecased(title):
    # find if the title is correctly capitalized (this heuristics could definitely be improved)
    words = title.split()
    nr_uppercased = sum([int(w[0].isupper()) for w in words])

    if len(words) <= 2:
        return nr_uppercased == len(words)
    elif len(words) <= 4:
        return nr_uppercased >= 2
    else:
        return nr_uppercased >= 3


def log_title(title):
    return title.replace("\n", " ").replace("{", "").replace("}", "")


def get_authors_canonical(entry):
    try:
        # bc.author modifies the entry in place -> copy
        # we only need the author, so drop everything else
        entry_tmp = {"author": entry["author"]}
        # removing what the parser cannot read
        entry_tmp["author"] = entry_tmp["author"].replace("and others", "").replace("~", " ")

        # convert the string with author names to list
        entry_tmp = bc.author(entry_tmp)
        # convert LaTeX special characters to unicode
        authors = bc.convert_to_unicode({"author": entry_tmp["author"]})["author"]
        # convert special unicode characters to ascii
        authors = [unidecode.unidecode(name) for name in authors]
        authors = [bc.splitname(a, strict_mode=False) for a in authors]
        authors = [" ".join(a["first"]) + " " + " ".join(a["last"]) for a in authors]
    except (bc.InvalidName, TypeError) as x:
        logger.warning(colored(f"[WARNING] Cannot parse authors: {entry_tmp['author']}", "yellow"))
        return []
    except KeyError:
        logger.warning(colored(f"[WARNING] No authors found: {entry['title']}", "yellow"))
        return []
    except Exception as e:
        logger.exception(e)
        raise e

    return authors


def select_entry(entries, orig_entry, replace_arxiv):
    if not entries:
        return None

    matching_entries = []
    # keep only entries with matching title, ignoring casing and non-alpha numeric characters
    # (some titles are returned with trailing dot, dashes may be inconsistent, etc.)
    orig_title = re.sub(r"[^0-9a-zA-Z]+", "", orig_entry["title"]).lower()
    orig_authors = get_authors_canonical(orig_entry)

    for entry in entries:
        title = re.sub(r"[^0-9a-zA-Z]+", "", entry["title"]).lower()

        if "author" not in entry:
            continue

        authors = get_authors_canonical(entry)

        # keep only entries where at least one of the authors is also present in the original entry
        if title == orig_title and len(set(orig_authors).intersection(set(authors))) > 0:
            matching_entries.append(entry)

    if replace_arxiv:
        # split into arxiv and non-arxiv publications
        entries_other = [entry for entry in matching_entries if not is_arxiv(entry)]
        entries_arxiv = [entry for entry in matching_entries if is_arxiv(entry)]

        if entries_other:
            entry = get_best_entry(entries_other, orig_entry)
        else:
            entry = get_best_entry(entries_arxiv, orig_entry)
    else:
        entry = get_best_entry(matching_entries, orig_entry)

    if entry and is_arxiv(entry) and not is_arxiv(orig_entry):
        logger.info(colored(f"[KEEP][NON_ARXIV_FOUND]: {log_title(orig_entry['title'])}", "grey", attrs=["bold"]))
        return None
    return entry


def process(in_file, out_file, replace_arxiv, force_titlecase, interact, order_entries_by=None):
    bp = BibTexParser(interpolate_strings=False, common_strings=True)

    with open(in_file) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file, parser=bp)
        logger.info(colored("[INFO] Bibliography file loaded successfully.", "cyan"))
        orig_entries_cnt = len(bib_database.entries)

        for i in range(len(bib_database.entries)):
            orig_entry = bib_database.entries[i]
            title = orig_entry["title"]
            try:
                first_author = get_authors_canonical(orig_entry)[0]
            except IndexError:
                first_author = ""

            query = title + " " + first_author
            entries = get_dblp_results(query)
            entry = select_entry(entries, orig_entry=orig_entry, replace_arxiv=replace_arxiv)

            if entry is not None:
                # replace the new BibTeX reference label with the original one
                entry["ID"] = orig_entry["ID"]

                # if the title is titlecased in the original entry, do not modify it
                if force_titlecase and not is_titlecased(entry["title"]):
                    entry["title"] = to_titlecase(entry["title"])

                entry["title"] = protect_titlecase(entry["title"])
                orig_str = pprint.pformat(orig_entry, indent=4)
                new_str = pprint.pformat(entry, indent=4)
                conf = "y"

                if interact:
                    logging.info(f"\n---------------- Original ----------------\n {orig_str}\n")
                    logging.info(f"\n---------------- Retrieved ---------------\n {new_str}\n")
                    while True:
                        conf = input("==> Replace the entry (y/n)?: ").lower()
                        if conf == "y" or conf == "n":
                            break
                        print("Please accept (y) or reject (n) the change.")
                if conf == "y":
                    bib_database.entries[i] = entry

                    if is_equivalent(entry, orig_entry):
                        # the entry is equivalent, using the DBLP bib entry
                        logging.info(colored(f"[UPDATE] {log_title(entry['title'])}", "green"))
                    elif replace_arxiv and is_arxiv(orig_entry) and not is_arxiv(entry):
                        # non-arxiv version was found on DBLP
                        logging.info(colored(f"[UPDATE_ARXIV] {log_title(entry['title'])}", "green", attrs=["bold"]))
                    else:
                        # a different version was found on DBLP
                        logging.info(colored(f"[UPDATE] {log_title(entry['title'])}", "green"))

            else:
                # no result found, keeping the original entry
                if force_titlecase and not is_titlecased(title):
                    title = to_titlecase(title)

                title = protect_titlecase(title)
                bib_database.entries[i]["title"] = title
                logging.info(colored(f"[KEEP] {log_title(title)}", "grey"))

    new_entries_cnt = len(bib_database.entries)
    assert orig_entries_cnt == new_entries_cnt

    with open(out_file, "w") as f:
        bwriter = bibtexparser.bwriter.BibTexWriter()
        bwriter.order_entries_by = order_entries_by

        bibtexparser.dump(bib_database, f, writer=bwriter)
        logger.info(colored(f"[FINISH] Saving the results to {out_file}.", "cyan"))


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("in_file", type=str, help="Bibliography file")
    parser.add_argument("-o", "--out", type=str, default=None, help="Output file")
    parser.add_argument(
        "-a",
        "--replace_arxiv",
        action="store_true",
        help="Try to use a non-arXiv version whenever possible",
    )
    parser.add_argument(
        "-t",
        "--force_titlecase",
        action="store_true",
        help="Use the `titlecase` package to fix titlecasing for paper names which are not titlecased",
    )
    parser.add_argument(
        "-i",
        "--interact",
        action="store_true",
        help="Interactive mode - confirm every change",
    )
    parser.add_argument(
        "-s",
        "--sort_by",
        default=None,
        nargs="*",
        help="Multiple sort conditions compatible with bibtexparser.BibTexWriter applied in the provided order. "
        "Example: `-s ENTRYTYPE year` sorts the list by the entry type as its primary key and year as its secondary key. "
        "`ID` can be used to refer to the Bibtex key. The default None value keeps the original order of Bib entries. ",
    )

    args = parser.parse_args()
    logger.info(args)

    if args.out is None:
        out_file = args.in_file.replace(".bib", "") + ".fixed.bib"
    else:
        out_file = args.out

    out_dir = os.path.dirname(out_file) if os.path.dirname(out_file) else "."
    os.makedirs(out_dir, exist_ok=True)

    process(
        in_file=args.in_file,
        out_file=out_file,
        replace_arxiv=args.replace_arxiv,
        force_titlecase=args.force_titlecase,
        interact=args.interact,
        order_entries_by=args.sort_by,
    )


if __name__ == "__main__":
    cli()
