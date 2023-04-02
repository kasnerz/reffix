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
import bibtexparser
import re
import pprint

from . import utils as ut

from bibtexparser.bparser import BibTexParser
import bibtexparser.customization as bc

logging.basicConfig(format="%(message)s", level=logging.INFO, datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def select_entry(entries, orig_entry, replace_arxiv):
    if not entries:
        return None

    matching_entries = []
    # keep only entries with matching title, ignoring casing and non-alpha numeric characters
    # (some titles are returned with trailing dot, dashes may be inconsistent, etc.)
    orig_title = re.sub(r"[^0-9a-zA-Z]+", "", orig_entry["title"]).lower()
    orig_authors = ut.get_authors_canonical(orig_entry)

    # try to find if any entry is better than the original one
    for entry in entries:
        title = re.sub(r"[^0-9a-zA-Z]+", "", entry["title"]).lower()

        # skip entries with no authors
        if "author" not in entry:
            continue

        authors = ut.get_authors_canonical(entry)

        # keep only entries where at least one of the authors is also present in the original entry
        if title == orig_title and len(set(orig_authors).intersection(set(authors))) > 0:
            matching_entries.append(entry)

    # split into arxiv and non-arxiv publications
    entries_other = [entry for entry in matching_entries if not ut.is_arxiv(entry)]
    entries_arxiv = [entry for entry in matching_entries if ut.is_arxiv(entry)]

    best_all = ut.get_best_entry(matching_entries, orig_entry)
    best_other = ut.get_best_entry(entries_other, orig_entry)
    best_arxiv = ut.get_best_entry(entries_arxiv, orig_entry)

    # we found a non-arxiv entry for an arxiv entry but not returning it because the flag was not set -> notify the user
    if not replace_arxiv and ut.is_arxiv(orig_entry) and best_other is not None:
        ut.log_message(ut.entry_to_str(orig_entry), "non_arxiv_found")

    # best entries can be None (if None is returned, no new entry was selected)
    if replace_arxiv:
        return best_other or best_all
    else:
        return best_arxiv or best_all


def process(
    in_file,
    out_file,
    replace_arxiv,
    force_titlecase,
    interact,
    no_publisher,
    process_conf_loc,
    order_entries_by=None,
    use_formatter=True,
):
    if process_conf_loc:
        import spacy

        # download spacy model if not existing
        if not spacy.util.is_package("en_core_web_sm"):
            ut.log_message("Downloading spacy model...", "info")
            os.system("python -m spacy download en_core_web_sm")
            ut.log_message("Spacy model downloaded successfully.", "info")

        nlp = spacy.load("en_core_web_sm")

    bp = BibTexParser(interpolate_strings=False, common_strings=True)

    with open(in_file) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file, parser=bp)
        ut.log_message("Bibliography file loaded successfully.", "info")
        orig_entries_cnt = len(bib_database.entries)

        for i in range(len(bib_database.entries)):
            orig_entry = bib_database.entries[i]
            title = orig_entry["title"]
            try:
                first_author = ut.get_authors_canonical(orig_entry)[0]
            except IndexError:
                # don't try to match if there is no first author
                continue

            query = title + " " + first_author

            entries = ut.get_dblp_results(query)
            entry = select_entry(entries, orig_entry=orig_entry, replace_arxiv=replace_arxiv)

            if entry is not None:
                # replace the new BibTeX reference label with the original one
                entry["ID"] = orig_entry["ID"]

                if process_conf_loc and entry.get("ENTRYTYPE") == "inproceedings":
                    entry = ut.process_conf_location(entry, nlp)

                # if the title is titlecased in the original entry, do not modify it
                if force_titlecase and not ut.is_titlecased(entry["title"]):
                    entry["title"] = ut.to_titlecase(entry["title"])

                entry["title"] = ut.protect_titlecase(entry["title"])
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

                    if ut.is_equivalent(entry, orig_entry):
                        # the entry is equivalent, using the DBLP bib entry
                        ut.log_message(ut.entry_to_str(entry), info="update")
                    elif replace_arxiv and ut.is_arxiv(orig_entry) and not ut.is_arxiv(entry):
                        # non-arxiv version was found on DBLP
                        ut.log_message(ut.entry_to_str(entry), info="update_arxiv")
                    else:
                        # a different version was found on DBLP
                        ut.log_message(ut.entry_to_str(entry), info="update")

            else:
                entry = orig_entry

                # no result found, keeping the original entry
                if force_titlecase and not ut.is_titlecased(title):
                    title = ut.to_titlecase(title)

                title = ut.protect_titlecase(title)
                entry["title"] = title
                ut.log_message(ut.entry_to_str(entry), info="keep")

            if no_publisher and entry.get("ENTRYTYPE") in ["article", "inproceedings"] and "publisher" in entry:
                del entry["publisher"]

            # attempt to fix potential errors
            entry = ut.clean_entry(entry)

    new_entries_cnt = len(bib_database.entries)
    assert orig_entries_cnt == new_entries_cnt

    with open(out_file, "w") as f:
        bwriter = bibtexparser.bwriter.BibTexWriter()
        bwriter.order_entries_by = order_entries_by

        if use_formatter:
            bwriter.indent = "  "  # indent entries with 2 spaces instead of one
            bwriter.align_values = True
            bwriter.align_multiline_values = True

        bibtexparser.dump(bib_database, f, writer=bwriter)
        ut.log_message(f"Saving the results to {out_file}.", info="info")


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=str, help="Bibliography file")
    parser.add_argument("-o", "--out", type=str, default=None, help="Output file")
    parser.add_argument(
        "-a",
        "--replace-arxiv",
        action="store_true",
        help="Try to use a non-arXiv version whenever possible",
    )
    parser.add_argument(
        "-t",
        "--force-titlecase",
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
        "--sort-by",
        default=None,
        nargs="*",
        help="Multiple sort conditions compatible with bibtexparser.BibTexWriter applied in the provided order. "
        "Example: `-s ENTRYTYPE year` sorts the list by the entry type as its primary key and year as its secondary key. "
        "`ID` can be used to refer to the Bibtex key. The default None value keeps the original order of Bib entries. ",
    )
    parser.add_argument(
        "--no-publisher",
        action="store_true",
        help="Suppress publishers in conference papers and journals (still kept for books)",
    )
    parser.add_argument(
        "--process-conf-loc",
        action="store_true",
        help="Parse conference dates and locations, remove from proceedings names, store locations under address",
    )
    parser.add_argument(
        "--no-formatting",
        action="store_true",
        help="Disable automatic BibTeX formatting.",
    )

    args = parser.parse_args()
    logger.info(args)

    if args.out is None:
        out_file = args.input.replace(".bib", "") + ".fixed.bib"
    else:
        out_file = args.out

    out_dir = os.path.dirname(out_file) if os.path.dirname(out_file) else "."
    os.makedirs(out_dir, exist_ok=True)

    if not args.replace_arxiv:
        ut.log_message(
            "Not replacing arXiv entries with entries found in a book or journal. Use the flag `--replace-arxiv` if you wish to replace arXiv entries.",
            "warning",
        )

    process(
        in_file=args.input,
        out_file=out_file,
        replace_arxiv=args.replace_arxiv,
        force_titlecase=args.force_titlecase,
        interact=args.interact,
        no_publisher=args.no_publisher,
        process_conf_loc=args.process_conf_loc,
        order_entries_by=args.sort_by,
        use_formatter=not args.no_formatting,
    )


if __name__ == "__main__":
    cli()
