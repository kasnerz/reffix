#!/usr/bin/env python3

"""
Query a local copy of the DBLP database instead of the DBLP API.

The DBLP team offers the complete dataset as a single XML file (see
https://dblp.uni-trier.de/faq/1474679.html) and encourages users with many
queries to run them locally. This module builds a SQLite
index (with full-text search on normalized titles) from `dblp.xml` or
`dblp.xml.gz` and serves lookups from it. The index is built once and cached
next to the XML file; subsequent runs reuse it.

Parsing the XML requires the accompanying `dblp.dtd` file (available from
https://dblp.org/xml/dblp.dtd) in the same directory, since the dump uses
character entities defined there.
"""

import gzip
import logging
import os
import re
import sqlite3
import time
import xml.sax
import xml.sax.handler

import unidecode

from .utils import log_message

logger = logging.getLogger(__name__)

INDEX_SCHEMA_VERSION = 4

DBLP_BIBSOURCE = "dblp computer science bibliography, https://dblp.org"

# publication record types of the DBLP XML that map directly to BibTeX entry types
RECORD_TYPES = {
    "article",
    "inproceedings",
    "proceedings",
    "book",
    "incollection",
    "phdthesis",
    "mastersthesis",
}
FIELD_TAGS = {
    "author",
    "editor",
    "title",
    "booktitle",
    "pages",
    "year",
    "journal",
    "volume",
    "number",
    "ee",
    "crossref",
    "publisher",
    "school",
    "series",
    "isbn",
}

# DBLP disambiguates homonymous authors with a numeric suffix ("Wei Wang 0001");
# the BibTeX exports of the API drop it
HOMONYM_SUFFIX_REGEX = re.compile(r"\s+\d{4}$")


def _normalize_title(title):
    # unlike the LaTeX-flavored titles of BibTeX files (handled by
    # utils.normalize_dblp_query_text), XML titles are plain unicode, so a
    # transliteration is enough; both normalizations end in the same space
    # of lowercase alphanumeric words, which makes them comparable
    text = unidecode.unidecode(title)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


class _DblpDtdResolver(xml.sax.handler.EntityResolver):
    """Resolve the `dblp.dtd` reference to a file next to the XML dump."""

    def __init__(self, dtd_file):
        self.dtd_file = dtd_file

    def resolveEntity(self, publicId, systemId):
        if systemId and os.path.basename(systemId) == os.path.basename(self.dtd_file):
            return self.dtd_file
        return systemId


class _DblpRecordHandler(xml.sax.handler.ContentHandler):
    """Stream DBLP publication records to a callback as plain dicts."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.record = None
        self.field = None
        self.buffer = ""

    def startElement(self, name, attrs):
        if name in RECORD_TYPES and self.record is None:
            self.record = {
                "type": name,
                "key": attrs.get("key", ""),
                "mdate": attrs.get("mdate", ""),
                "authors": [],
                "editors": [],
                "ees": [],
            }
        elif self.record is not None and name in FIELD_TAGS and self.field is None:
            self.field = name
            self.buffer = ""
        # nested formatting elements inside fields (<i>, <sub>, ...) are ignored:
        # their character data is collected into the current field buffer

    def characters(self, content):
        if self.field is not None:
            self.buffer += content

    def endElement(self, name):
        if self.record is None:
            return

        if name == self.field:
            value = " ".join(self.buffer.split())
            if value:
                if name == "author":
                    self.record["authors"].append(HOMONYM_SUFFIX_REGEX.sub("", value))
                elif name == "editor":
                    self.record["editors"].append(HOMONYM_SUFFIX_REGEX.sub("", value))
                elif name == "ee":
                    self.record["ees"].append(value)
                else:
                    # some fields appear multiple times (e.g. one isbn per
                    # edition); like the BibTeX exports of the API, keep the first
                    self.record.setdefault(name, value)
            self.field = None
        elif name in RECORD_TYPES and name == self.record["type"]:
            if self.record["key"]:
                self.callback(self.record)
            self.record = None


def _record_to_row(record):
    title = record.get("title", "")
    # the BibTeX exports of the API drop the trailing dot of DBLP titles
    if title.endswith(".") and not title.endswith(".."):
        title = title[:-1]

    pages = record.get("pages", "")
    # single hyphens in page ranges become double hyphens in BibTeX
    if pages and "--" not in pages:
        pages = re.sub(r"(?<=[0-9a-zA-Z])-(?=[0-9a-zA-Z])", "--", pages)

    # like the BibTeX exports of the API: the first electronic edition becomes
    # the url, while DOI and URN links among them additionally yield the doi
    # and urn fields
    ees = record["ees"]
    url = ees[0] if ees else ""
    doi = ""
    urn = ""
    for ee in ees:
        doi_match = re.search(r"doi\.org/(.+)$", ee)
        if doi_match and not doi:
            doi = doi_match.group(1).upper()
        urn_match = re.search(r"nbn-resolving\.(?:org|de)/(.+)$", ee)
        if urn_match and not urn:
            urn = urn_match.group(1)

    return (
        record["key"],
        record["type"],
        record["mdate"],
        title,
        " and ".join(record["authors"]),
        " and ".join(record["editors"]),
        record.get("year", ""),
        pages,
        record.get("journal", ""),
        record.get("booktitle", ""),
        record.get("volume", ""),
        record.get("number", ""),
        record.get("publisher", ""),
        record.get("school", ""),
        record.get("series", ""),
        record.get("isbn", ""),
        record.get("crossref", ""),
        url,
        doi,
        urn,
        _normalize_title(title),
    )


ROW_COLUMNS = (
    "key, type, mdate, title, author, editor, year, pages, journal, "
    "booktitle, volume, number, publisher, school, series, isbn, crossref, url, doi, urn, title_norm"
)


class LocalDblp:
    """A searchable index over a local DBLP XML dump."""

    def __init__(self, xml_file, index_file=None, batch_size=50000):
        self.xml_file = xml_file
        self.index_file = index_file or xml_file + ".sqlite"
        self.batch_size = batch_size

        if not os.path.exists(self.xml_file):
            raise FileNotFoundError(f"DBLP XML dump not found: {self.xml_file}")

        if not self._index_is_current():
            self._build_index()

        self.conn = sqlite3.connect(self.index_file)

    def _xml_fingerprint(self):
        stat = os.stat(self.xml_file)
        return f"{INDEX_SCHEMA_VERSION}:{stat.st_size}:{int(stat.st_mtime)}"

    def _index_is_current(self):
        if not os.path.exists(self.index_file):
            return False
        try:
            conn = sqlite3.connect(self.index_file)
            try:
                row = conn.execute("SELECT value FROM meta WHERE name = 'fingerprint'").fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return False
        return row is not None and row[0] == self._xml_fingerprint()

    def _open_xml(self):
        if self.xml_file.endswith(".gz"):
            return gzip.open(self.xml_file, "rb")
        return open(self.xml_file, "rb")

    def _build_index(self):
        dtd_file = os.path.join(os.path.dirname(os.path.abspath(self.xml_file)), "dblp.dtd")
        if not os.path.exists(dtd_file):
            raise FileNotFoundError(
                f"{dtd_file} is required to parse the DBLP XML dump. "
                "Download it from https://dblp.org/xml/dblp.dtd and place it next to the XML file."
            )

        log_message(
            f"Building the DBLP index at {self.index_file} (one-time operation, takes several minutes)...", "info"
        )
        start_time = time.monotonic()

        tmp_index_file = self.index_file + ".tmp"
        if os.path.exists(tmp_index_file):
            os.remove(tmp_index_file)

        conn = sqlite3.connect(tmp_index_file)
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            """CREATE TABLE pubs (
                key TEXT PRIMARY KEY, type TEXT, mdate TEXT, title TEXT, author TEXT, editor TEXT,
                year TEXT, pages TEXT, journal TEXT, booktitle TEXT, volume TEXT, number TEXT,
                publisher TEXT, school TEXT, series TEXT, isbn TEXT, crossref TEXT, url TEXT,
                doi TEXT, urn TEXT, title_norm TEXT
            )"""
        )

        batch = []
        counter = {"records": 0}
        placeholders = ", ".join("?" * 21)

        def insert_record(record):
            batch.append(_record_to_row(record))
            counter["records"] += 1
            if len(batch) >= self.batch_size:
                conn.executemany(f"INSERT OR REPLACE INTO pubs ({ROW_COLUMNS}) VALUES ({placeholders})", batch)
                batch.clear()
            if counter["records"] % 1000000 == 0:
                elapsed = time.monotonic() - start_time
                log_message(f"Indexed {counter['records']:,} records ({elapsed:.0f}s elapsed)...", "info")

        parser = xml.sax.make_parser()
        parser.setFeature(xml.sax.handler.feature_external_ges, True)
        parser.setEntityResolver(_DblpDtdResolver(dtd_file))
        parser.setContentHandler(_DblpRecordHandler(insert_record))

        try:
            with self._open_xml() as f:
                parser.parse(f)

            if batch:
                conn.executemany(f"INSERT OR REPLACE INTO pubs ({ROW_COLUMNS}) VALUES ({placeholders})", batch)

            log_message("Building the full-text search index on titles...", "info")
            conn.execute("CREATE VIRTUAL TABLE pubs_fts USING fts5(title_norm, content='pubs', content_rowid='rowid')")
            conn.execute("INSERT INTO pubs_fts (rowid, title_norm) SELECT rowid, title_norm FROM pubs")
            conn.execute("INSERT INTO meta (name, value) VALUES ('fingerprint', ?)", (self._xml_fingerprint(),))
            conn.commit()
            conn.close()
            os.replace(tmp_index_file, self.index_file)
        except BaseException:
            conn.close()
            if os.path.exists(tmp_index_file):
                os.remove(tmp_index_file)
            raise

        elapsed = time.monotonic() - start_time
        log_message(f"DBLP index built: {counter['records']:,} records in {elapsed:.0f}s.", "info")

    def _row_to_entry(self, row):
        columns = [c.strip() for c in ROW_COLUMNS.split(",")]
        record = dict(zip(columns, row))

        entry = {
            "ID": record["key"],
            "ENTRYTYPE": record["type"],
            "title": record["title"],
            # allows sorting DBLP results by recency, mirroring the API exports
            "timestamp": record["mdate"],
            "biburl": f"https://dblp.org/rec/{record['key']}.bib",
            "bibsource": DBLP_BIBSOURCE,
        }
        for field in ("author", "editor", "year", "pages", "journal", "booktitle", "volume", "number", "publisher", "school", "series", "isbn", "url", "doi", "urn"):
            if record[field]:
                entry[field] = record[field]

        # the API exports omit the page count for entry types that have no
        # pages field in standard BibTeX, and the booktitle of monographs
        if record["type"] in ("book", "proceedings", "phdthesis", "mastersthesis"):
            entry.pop("pages", None)
        if record["type"] == "book":
            entry.pop("booktitle", None)

        # arXiv preprints are indexed as CoRR articles; the API exports expose
        # the arXiv identifier in the eprint fields
        if record["journal"] == "CoRR" and record["volume"].startswith("abs/"):
            entry["eprinttype"] = "arXiv"
            entry["eprint"] = record["volume"][len("abs/") :]

        # resolve the crossref to the proceedings record to obtain the full venue
        # name, mirroring the "standard" BibTeX export format of the API
        if record["crossref"]:
            parent = self.conn.execute(
                f"SELECT {ROW_COLUMNS} FROM pubs WHERE key = ?", (record["crossref"],)
            ).fetchone()
            if parent is not None:
                parent_record = dict(zip(columns, parent))
                # the short venue name is replaced with the full proceedings title;
                # the crossref itself is not kept, since the proceedings entry is
                # not part of the output and BibTeX rejects dangling crossrefs
                if parent_record["title"]:
                    entry["booktitle"] = parent_record["title"]
                for field in ("editor", "publisher", "series", "volume"):
                    if parent_record[field] and not entry.get(field):
                        entry[field] = parent_record[field]

        return entry

    def search(self, query, limit=10):
        """Return publications whose title contains all words of the query.

        The result entries use the same shape as the parsed BibTeX exports of
        the DBLP API, so they can be passed to the regular selection logic.
        """
        words = _normalize_title(query).split()
        if not words:
            return []

        match_query = " ".join('"{}"'.format(word.replace('"', "")) for word in words)
        qualified_columns = ", ".join(f"pubs.{column.strip()}" for column in ROW_COLUMNS.split(","))
        try:
            rows = self.conn.execute(
                f"SELECT {qualified_columns} FROM pubs_fts JOIN pubs ON pubs.rowid = pubs_fts.rowid "
                "WHERE pubs_fts MATCH ? ORDER BY rank LIMIT ?",
                (match_query, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            log_message(f"Local DBLP search failed for query `{query}`: {e}", "warning", level=logging.WARNING)
            return []

        return [self._row_to_entry(row) for row in rows]

    def close(self):
        self.conn.close()
