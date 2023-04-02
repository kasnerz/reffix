#!/usr/bin/env python3

import logging
import re
import logging
import requests
import titlecase
import re
import unidecode
import dateparser

from bibtexparser.bparser import BibTexParser
import bibtexparser.customization as bc
from termcolor import colored
from collections import namedtuple

logging.basicConfig(format="%(message)s", level=logging.INFO, datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"

DATE_REGEX = (
    r"([1-3]?[0-9](?:st|rd|nd|th)?((?: *[-–] *)[1-3]?[0-9](?:st|rd|nd|th)?)?) "
    + "+(january|february|march|april|may|june|july|august|september|october|november|december|"
    + "jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec),? +[12][90][0-9]{2}"
)
PLACE_LIST = [
    "Copenhagen",
    "Groningen",
    "Heraklion",
    "Hersonissos",
    "Online Event",
    "Online",
    "Pisa",
    "Punta Cana",
    "Santa Fe",
    "Schloss Dagstuhl",
    "Tilburg University",
    "Virtual Event",
]
SUFFIX_REGEX = (
    r"(?:(?:volume|and|long|demo|demonstration|short|papers|selected|proceedings|part| [0-9]|[IVX]{1,4}|[,;:\(\)]) *)+$"
)


def log_message(message, info, level=logging.INFO):
    padding = 10

    if info == "update":
        info_str = colored(f"[UPDATE]".ljust(padding), "green", attrs=["bold"])
    elif info == "update_arxiv":
        info_str = colored(f"[UPD_ARX]".ljust(padding), "green", attrs=["bold"])
    elif info == "non_arxiv_found":
        info_str = colored(f"[KEEP_ARX]".ljust(padding), "light_grey", attrs=["bold"])
    elif info == "keep":
        info_str = colored(f"[KEEP]".ljust(padding), "light_grey", attrs=["bold"])
    elif info == "error":
        info_str = colored(f"[ERROR]".ljust(padding), "red", attrs=["bold"])
    elif info == "warning":
        info_str = colored(f"[WARNING]".ljust(padding), "yellow", attrs=["bold"])
    elif info == "info":
        info_str = colored(f"[INFO]".ljust(padding), "blue", attrs=["bold"])
    else:
        info_str = ""

    logger.log(level=level, msg=f"{info_str} {message}")


def get_dblp_results(query):
    params = {"format": "bib", "q": query}
    res = requests.get(DBLP_API, params=params)

    try:
        if res.status_code == 200:
            # new instance needs to be created to use a new database
            bp = BibTexParser(interpolate_strings=False, common_strings=True)
            bib = bp.parse(res.text)

            return bib.entries
        else:
            log_message(f"DBLP API returned status code {res.status_code}", "error", level=logging.ERROR)
            return None
    except Exception as e:
        logger.exception(e)
        raise e


def is_arxiv(entry):
    # find if the entry comes from arXiv
    journal = entry.get("journal", "").lower()
    eprinttype = entry.get("eprinttype", "").lower()
    url = entry.get("url", "").lower()

    return ("arxiv" in journal + eprinttype + url) or "corr" in journal


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


def entry_to_str(entry):
    authors = get_authors_canonical(entry)
    first_author_surname = authors[0].split(" ")[-1] if authors else None
    year = entry.get("year", "")

    s = []
    if first_author_surname and year:
        s.append(f"({first_author_surname}, {year})".ljust(20))

    title = entry.get("title", "")
    title = title.replace("\n", " ").replace("{", "").replace("}", "")

    # shorten title to 100 characters, append ellipsis if necessary
    title = title[:97] + "..." if len(title) > 100 else title
    title = title.ljust(100)

    s.append(f"{title}")
    url = entry.get("url", None)
    if url:
        s.append(f"[{url}]")

    return " ".join(s)


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
        log_message(f"Cannot parse authors: {entry_tmp['author']}", "warning", level=logging.WARNING)
        return []
    except KeyError:
        log_message(f"No authors found: {entry['title']}", "warning", level=logging.WARNING)
        return []
    except Exception as e:
        logger.exception(e)
        raise e

    return authors


def protect_titlecase(title):
    # wrap the capital letters in curly braces to protect them
    # see https://tex.stackexchange.com/questions/10772/bibtex-loses-capitals-when-creating-bbl-file
    words = []

    for word in title.split():
        if "{" in word:
            # already (presumably) protected
            words.append(word)
            continue

        letters = []

        for i, letter in enumerate(word):
            # protect individual capital letters
            protect = True
            subwords = word.split("-")

            if (
                len(subwords) > 1
                and len(subwords[0]) > 1
                and i > 0
                and word[i - 1] == "-"
                and all(l.islower() for l in word[i + 1 :])
            ):
                # 3-D, U-Net, Mip-NeRF: protect
                # Spatially-Varying: don't protect
                protect = False

            if letter.isupper() and protect:
                letters.append(r"{" + letter + r"}")
            else:
                letters.append(letter)

        words.append("".join(letters))

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
    # sort entries using timestamp (newer better) -> year (newer better) -> # of keys (more complete better) -> ID (ensure deterministic order)
    entries.sort(
        key=lambda x: (
            dateparser.parse(x.get("timestamp", "")),
            x.get("year", ""),
            len(x.keys()),
            x.get("ID", ""),
        ),
        reverse=True,
    )
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

    return entries[-1]


def process_conf_location(entry, nlp):
    """Process conference location & date -- remove date, put location into address."""
    entry = entry.copy()
    if "booktitle" not in entry:
        return entry
    proc_title = entry["booktitle"].replace("\n", " ")
    proc_suffix = re.search(SUFFIX_REGEX, proc_title, re.I)
    if proc_suffix:
        proc_title = proc_title[: proc_suffix.start()].rstrip(",; ")
        proc_suffix = proc_suffix.group(0)
    else:
        proc_suffix = ""
    annot = nlp(proc_title)
    # taking entities from NER
    ents = list(annot.ents)
    # adding dates not catched by NER
    ents.extend(
        [
            namedtuple("found", ["label_", "start_char", "end_char"])("DATE", m.start(), m.end())
            for m in re.finditer(DATE_REGEX, proc_title, re.I)
        ]
    )
    # adding places not catched by NER
    ents.extend(
        [
            namedtuple("found", ["label_", "start_char", "end_char"])("GPE", m.start(), m.end())
            for m in re.finditer(r"\b(" + "|".join(PLACE_LIST) + r")\b", proc_title, re.I)
        ]
    )
    # removing numbers (not to confuse with dates)
    ents = [ent for ent in ents if ent.label_ not in ["ORDINAL", "CARDINAL"]]
    # sorting by position
    ents.sort(key=lambda ent: ent.start_char)
    # starting search
    # proceedings name typically ends with the location and the date in DBLP
    dates = []
    gpes = []
    # look for dates first
    while ents and ents[-1].label_ == "DATE" and (not dates or ents[-1].end_char + 3 >= dates[0].start_char):
        dates.insert(0, ents.pop())
    # then look for location
    while ents and ents[-1].label_ == "GPE" and (not gpes or gpes[-1].end_char + 3 >= gpes[0].start_char):
        gpes.insert(0, ents.pop())
    logger.debug(
        "\nORIG:"
        + entry["booktitle"].replace("\n", " ")
        + "\nSHRT:"
        + proc_title
        + "\nGPES: "
        + str(gpes)
        + "\nDTES: "
        + str(dates)
    )
    if gpes:  # location found -- move to address
        entry["address"] = proc_title[gpes[0].start_char : gpes[-1].end_char]
        entry["booktitle"] = proc_title[: gpes[0].start_char].rstrip(",; ") + proc_suffix
    elif dates:  # date found -- just strip
        entry["booktitle"] = proc_title[: dates[0].start_char].rstrip(",; ") + proc_suffix
    # TODO case where date precedes the place
    return entry
