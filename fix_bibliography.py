#!/usr/bin/env python3

"""
Fix common errors in BibTeX bibliography files.

Implemented so far:
- adding missing urls from DBLP
- 
"""


import os
import argparse
import logging
import requests
import bibtexparser
import titlecase
import re

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO, datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

dblp_api = "https://dblp.org/search/publ/api"

def get_dblp_results(title):
    params = {
        "format" : "json",
        "q" : title
    }
    resp = requests.get(dblp_api, params=params)
    return resp


def to_titlecase(title):
    new_title = titlecase.titlecase(title)
    words = []

    for word in new_title.split():
        if word[0].isupper():
            words.append(r"{" + word + r"}")
        else:
            words.append(word)

    return " ".join(words)


def main(bibfile, out_file, urls, titlecase):
    with open(bibfile) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)

        for entry in bib_database.entries:
            title = entry["title"]

            if titlecase:
                entry["title"] = to_titlecase(title)

                if entry["title"] != title:
                    logger.info(f"[TITLE] {title} -> {entry['title']}")

            if not urls or "url" in entry:
                logger.info(f"[OK] {title} ({entry['url']})")
                continue

            res = get_dblp_results(title)

            try:
                if res.json()["result"]["status"]["@code"] == "200":
                    hits = res.json()["result"]["hits"]

                    if type(hits) is dict:
                        if "@total" in hits and hits["@total"] == '0':
                            logger.info(f"[NOT_FOUND] {title}")
                            continue
                        hits = hits["hit"]
                else:
                    logger.error[f"[ERROR] {res.json()['result']}"]
            except Exception as e:
                logger.exception(e)

            for hit in hits:
                info = hit["info"]

            infos = [hit["info"] for hit in hits if "url" in hit["info"]]
            infos = [info for info in infos if re.sub("[^0-9a-zA-Z]+", "", 
                info["title"]).lower() == re.sub("[^0-9a-zA-Z]+", "", title).lower()]

            infos_other = [info for info in infos if info["venue"] != "CoRR"]
            infos_arxiv = [info for info in infos if info["venue"] == "CoRR"]

            if infos_other:
                info = infos_other[0]
                arxiv = False
            elif infos_arxiv:
                info = infos_arxiv[0]
                arxiv = True
            else:
                continue
            
            if "ee" in info:
                # DOI
                entry["url"] = info["ee"]
            elif "url" in info:
                entry["url"] = info["url"]
            else:
                return

            if not arxiv:
                logger.info(f"[ADD_URL] {title} ({entry['url']})")
            else:
                logger.info(f"[ADD_ARXIV_URL] {title} ({entry['url']})")

    with open(out_file, "w") as f:
        bibtex_str = bibtexparser.dump(bib_database, f)
        logger.info(f"Saving into {out_file}.")
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("bibfile", type=str, help="Bibliography file")
    parser.add_argument("-o", "--out", type=str, default=None, help="Output file")
    parser.add_argument("-u", "--urls", action="store_true", help="Add missing URLs")
    parser.add_argument("-t", "--titlecase", action="store_true", help="Fix titlecasing for names")

    args = parser.parse_args()
    logger.info(args)

    if not any([args.urls, args.titlecase]):
        print("No fixes specified: see --help for the list of available options.")

    if args.out is None:
        if args.bibfile.endswith(".bib"):
            out_file = args.bibfile.replace(".bib", ".fixed.bib")
        else:
            out_file = args.bibfile + "_fixed"
    else:
        out_file = args.out

    main(bibfile=args.bibfile, out_file=out_file, urls=args.urls, titlecase=args.titlecase)