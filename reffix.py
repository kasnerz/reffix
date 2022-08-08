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
from collections import namedtuple
import logging
import requests
import bibtexparser
import titlecase
import re
import pprint
import unidecode

from bibtexparser.bparser import BibTexParser
import bibtexparser.customization as bc


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
            # new instance needs to be created to use a new database
            bp = BibTexParser(interpolate_strings=False, common_strings=True)
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

    if len(entries) == 1:
        return entries[0]

    equivalent_entry = get_equivalent_entry(entries, orig_entry)
    if equivalent_entry:
        return equivalent_entry

    # sorting the results by year (newer is better) and by the number of entries (more is better)
    entries.sort(key=lambda x: (int(x.get("year", 0)), len(x.keys())))

    return entries[-1]


def is_arxiv(entry):
    journal = entry.get("journal", "").lower()
    eprinttype = entry.get("eprinttype", "").lower()
    url = entry.get("url", "").lower()
    return "arxiv" in journal + eprinttype + url

def get_authors_canonical(entry):
    try:
        authors = bc.author({'author': entry.get('author', '')})
        authors = bc.convert_to_unicode(authors)["author"]
        authors = [unidecode.unidecode(name) for name in authors]
        authors = [bc.splitname(a, strict_mode=False) for a in authors]
        authors = [" ".join(a["first"]) + " " + " ".join(a["last"]) for a in authors]
    except (bc.InvalidName, TypeError, KeyError):
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

    # keep only entries where at least one of the authors is also present in the original entry
    orig_authors = get_authors_canonical(orig_entry)

    for entry in entries:
        title = re.sub(r"[^0-9a-zA-Z]+", "", entry["title"]).lower()
        authors = get_authors_canonical(entry)

        if title == orig_title and len(set(orig_authors).intersection(set(authors))) > 0:
            matching_entries.append(entry)

    if replace_arxiv:
        # split into arxiv and non-arxiv publications
        entries_other = [entry for entry in matching_entries if not is_arxiv(entry)]
        entries_arxiv = [entry for entry in matching_entries if is_arxiv(entry)]

        if entries_other:
            entry = get_best_entry(entries_other, orig_entry)
        else:
            logger.info(f"[INFO] Found arXiv entry only: {orig_entry['title']}")
            entry = get_best_entry(entries_arxiv, orig_entry)
    else:
        entry = get_best_entry(matching_entries, orig_entry)

    if entry and is_arxiv(entry) and not is_arxiv(orig_entry):
        logger.info(f"[INFO] Will not replace a conference entry with arXiv: {orig_entry['title']}")
        return None
    return entry


def fix_reflabel(entry, orig_entry):
    entry["ID"] = orig_entry["ID"]
    return entry

DATE_REGEX = (r'([1-3]?[0-9](?:st|rd|nd|th)?((?: *[-–] *)[1-3]?[0-9](?:st|rd|nd|th)?)?) '
              + '+(january|february|march|april|may|june|july|august|september|october|november|december|'
              + 'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec),? +[12][90][0-9]{2}')
PLACE_LIST = ['Copenhagen', 'Groningen', 'Heraklion', 'Hersonissos',
              'Online Event', 'Online',
              'Pisa', 'Punta Cana', 'Santa Fe', 'Schloss Dagstuhl', 'Tilburg University',
              'Virtual Event',]
SUFFIX_REGEX = r'(?:(?:volume|and|long|demo|demonstration|short|papers|selected|proceedings|part| [0-9]|[IVX]{1,4}|[,;:\(\)]) *)+$'

def process_conf_location(entry, nlp):
    """Process conference location & date -- remove date, put location into address."""
    entry = entry.copy()
    if 'booktitle' not in entry:
        return entry
    proc_title = entry['booktitle'].replace('\n', ' ')
    proc_suffix = re.search(SUFFIX_REGEX, proc_title, re.I)
    if proc_suffix:
        proc_title = proc_title[:proc_suffix.start()].rstrip(',; ')
        proc_suffix = proc_suffix.group(0)
    else:
        proc_suffix = ''
    annot = nlp(proc_title)
    # taking entities from NER
    ents = list(annot.ents)
    # adding dates not catched by NER
    ents.extend([namedtuple('found', ['label_', 'start_char', 'end_char'])('DATE', m.start(), m.end())
                   for m in re.finditer(DATE_REGEX, proc_title, re.I)])
    # adding places not catched by NER
    ents.extend([namedtuple('found', ['label_', 'start_char', 'end_char'])('GPE', m.start(), m.end())
                   for m in re.finditer(r'\b(' + '|'.join(PLACE_LIST) + r')\b', proc_title, re.I)])
    # removing numbers (not to confuse with dates)
    ents = [ent for ent in ents if ent.label_ not in ['ORDINAL', 'CARDINAL']]
    # sorting by position
    ents.sort(key=lambda ent: ent.start_char)
    # starting search
    # proceedings name typically ends with the location and the date in DBLP
    dates = []
    gpes = []
    # look for dates first
    while (ents and ents[-1].label_ == 'DATE' and
           (not dates or ents[-1].end_char + 3 >= dates[0].start_char)):
        dates.insert(0, ents.pop())
    # then look for location
    while (ents and ents[-1].label_ == 'GPE' and
           (not gpes or gpes[-1].end_char + 3 >= gpes[0].start_char)):
        gpes.insert(0, ents.pop())
    logger.debug('\nORIG:' + entry['booktitle'].replace('\n', ' ') + '\nSHRT:' + proc_title + '\nGPES: ' + str(gpes) + '\nDTES: ' + str(dates))
    if gpes:  # location found -- move to address
        entry['address'] = proc_title[gpes[0].start_char:gpes[-1].end_char]
        entry['booktitle'] = proc_title[:gpes[0].start_char].rstrip(',; ') + proc_suffix
    elif dates:  # date found -- just strip
        entry['booktitle'] = proc_title[:dates[0].start_char].rstrip(',; ') + proc_suffix
    # TODO case where date precedes the place
    return entry


def main(in_file, out_file, replace_arxiv, force_titlecase, interact, no_publisher, process_conf_loc):
    bp = BibTexParser(interpolate_strings=False, common_strings=True)

    if args.process_conf_loc:
        import spacy
        nlp = spacy.load('en_core_web_sm')

    with open(in_file) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file, parser=bp)
        logger.info("[INFO] Bibliography file loaded successfully.")
        orig_entries_cnt = len(bib_database.entries)

        for i in range(len(bib_database.entries)):
            orig_entry = bib_database.entries[i]
            title = orig_entry["title"]
            entries = get_dblp_results(title)
            entry = select_entry(entries, orig_entry=orig_entry, replace_arxiv=replace_arxiv)

            if entry:
                entry = fix_reflabel(entry, orig_entry)
                entry["title"] = protect_titlecase(entry["title"])

                if process_conf_loc and entry.get('ENTRYTYPE') == 'inproceedings':
                    entry = process_conf_location(entry, nlp)

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
                else:
                    logging.info(f"[UPDATE] {title}")
                if conf == "y":
                    bib_database.entries[i] = entry
            else:
                logging.info(f"[KEEP] No result found, keeping the original entry: {title}")
                entry = bib_database.entries[i]

                if force_titlecase:
                    new_title = to_titlecase(title)

                    if new_title != title:
                        entry["title"] = new_title
                        logger.info(f"[INFO] Using custom titlecasing: {new_title}")

            if no_publisher and entry.get('ENTRYTYPE') in ['article', 'inproceedings'] and 'publisher' in entry:
                del entry['publisher']


    new_entries_cnt = len(bib_database.entries)
    assert orig_entries_cnt == new_entries_cnt

    with open(out_file, "w") as f:
        bwriter = bibtexparser.bwriter.BibTexWriter()
        bwriter.order_entries_by = None
        bibtex_str = bibtexparser.dump(bib_database, f, writer=bwriter)
        logger.info(f"[FINISHED] Saving the results to {out_file}.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("in_file", type=str, help="Bibliography file")
    parser.add_argument("-o", "--out", type=str, default=None, help="Output file")
    parser.add_argument("-a", "--replace_arxiv", action="store_true", help="")
    parser.add_argument("-t", "--force_titlecase", action="store_true", help="Use `titlecase` to fix titlecasing for references not found on DBLP")
    parser.add_argument("-i", "--interact", action="store_true", help="Interactive mode - confirm every change")
    parser.add_argument("--publisher", action=argparse.BooleanOptionalAction, default=True,
                        help="Use --no-publisher to suppress publishers in conference papers and journals (still kept for books)")
    parser.add_argument("--process-conf-loc", action="store_true",
                        help="Parse conference dates and locations, remove from proceedings names, store locations under address")

    args = parser.parse_args()
    logger.info(args)

    if args.out is None:
        out_file = args.in_file + ".fixed"
    else:
        out_file = args.out

    out_dir = os.path.dirname(out_file) if os.path.dirname(out_file) else '.'
    os.makedirs(out_dir, exist_ok=True)

    main(
        in_file=args.in_file,
        out_file=out_file,
        replace_arxiv=args.replace_arxiv,
        force_titlecase=args.force_titlecase,
        interact=args.interact,
        no_publisher=not args.publisher,
        process_conf_loc=args.process_conf_loc
    )
