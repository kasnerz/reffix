import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, Mock
import requests
import reffix.reffix as reffix
import reffix.utils as ut
from reffix.local_dblp import LocalDblp
import bibtexparser
from bibtexparser.bparser import BibTexParser

DBLP_XML_FIXTURE = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE dblp SYSTEM "dblp.dtd">
<dblp>
<article mdate="2024-06-01" key="journals/corr/abs-2404-05961">
<author>Parishad BehnamGhader 0001</author>
<author>Kalervo J&auml;rvelin</author>
<title>LLM2Vec: Large Language Models Are Secretly Powerful Text Encoders.</title>
<year>2024</year>
<journal>CoRR</journal>
<volume>abs/2404.05961</volume>
<ee type="oa">https://arxiv.org/abs/2404.05961</ee>
</article>
<inproceedings mdate="2023-05-02" key="conf/inlg/DusekK20">
<author>Ondrej Dusek</author>
<author>Zdenek Kasner</author>
<title>Evaluating Semantic Accuracy of Data-to-Text Generation with <i>Natural Language Inference</i>.</title>
<pages>131-137</pages>
<year>2020</year>
<crossref>conf/inlg/2020</crossref>
<booktitle>INLG</booktitle>
<ee>https://aclanthology.org/2020.inlg-1.19/</ee>
<ee>https://doi.org/10.18653/v1/2020.inlg-1.19</ee>
</inproceedings>
<proceedings mdate="2022-01-01" key="conf/inlg/2020">
<editor>Brian Davis</editor>
<title>Proceedings of the 13th International Conference on Natural Language Generation, INLG 2020</title>
<publisher>Association for Computational Linguistics</publisher>
<year>2020</year>
</proceedings>
<book mdate="2021-01-01" key="books/sp/NocedalW99">
<author>Jorge Nocedal</author>
<author>Stephen J. Wright</author>
<title>Numerical Optimization</title>
<pages>1-636</pages>
<year>1999</year>
<publisher>Springer</publisher>
<isbn>978-0-387-98793-4</isbn>
<isbn>978-0-387-22742-9</isbn>
<ee>https://doi.org/10.1007/b98874</ee>
<ee>https://nbn-resolving.org/urn:nbn:de:test-123</ee>
</book>
<phdthesis mdate="2021-07-17" key="phd/dnb/Varnik11">
<author>Ebadollah Varnik</author>
<title>Exploitation of structural sparsity in algorithmic differentiation.</title>
<year>2011</year>
<pages>1-145</pages>
<school>RWTH Aachen University</school>
<ee>http://darwin.example.org/3847.pdf</ee>
</phdthesis>
</dblp>
"""

# a minimal stand-in for the real dblp.dtd: the parser only needs the entity definitions
DBLP_DTD_FIXTURE = """<!ENTITY auml "&#228;">
"""


def write_dblp_fixture(temp_dir):
    xml_file = os.path.join(temp_dir, "dblp.xml")
    with open(xml_file, "w", encoding="iso-8859-1") as f:
        f.write(DBLP_XML_FIXTURE)
    with open(os.path.join(temp_dir, "dblp.dtd"), "w", encoding="iso-8859-1") as f:
        f.write(DBLP_DTD_FIXTURE)
    return xml_file


class TestReffix(unittest.TestCase):
    def setUp(self):
        self.query = "test"
        self.entry = {
            "title": "Test Entry",
            "author": "John Doe",
            "year": "2022",
            "pages": "1-10",
            "booktitle": "Test Book",
            "url": "https://arxiv.org/abs/1234.56789",
        }

    def test_get_dblp_results(self):
        query = "Evaluating semantic accuracy of data-to-text generation with natural language inference Dusek Ondrej"
        results = ut.get_dblp_results(query)
        if results is None:
            self.skipTest("DBLP temporarily unavailable in the current environment")
        self.assertGreaterEqual(len(results), 1)

    @patch("reffix.utils.requests.get")
    def test_get_dblp_results_uses_json_search_and_fetches_bib(self, get_mock):
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "key": "irrelevant/key",
                                "url": "https://dblp.org/rec/irrelevant/key",
                                "title": "Different Title",
                            }
                        },
                        {
                            "info": {
                                "key": "journals/corr/abs-2404-05961",
                                "url": "https://dblp.org/rec/journals/corr/abs-2404-05961",
                                "title": "LLM2Vec",
                            }
                        },
                    ]
                }
            }
        }

        bib_response = Mock()
        bib_response.raise_for_status.return_value = None
        bib_response.text = (
            """@article{llm2vec,\n  title={LLM2Vec},\n  author={BehnamGhader, Parishad},\n  year={2024}\n}"""
        )

        get_mock.side_effect = [search_response, bib_response]

        results = ut.get_dblp_results("llm2vec")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ID"], "llm2vec")
        get_mock.assert_any_call(
            ut.DBLP_API,
            params={"format": "json", "q": "llm2vec", "h": 10},
            timeout=30,
            headers=ut.DBLP_HEADERS,
        )
        get_mock.assert_any_call(
            "https://dblp.org/rec/journals/corr/abs-2404-05961.bib?param=1",
            params=None,
            timeout=30,
            headers=ut.DBLP_HEADERS,
        )
        self.assertEqual(get_mock.call_count, 2)

    def test_derive_bib_url_supports_all_dblp_bibtex_formats(self):
        hit = {
            "info": {
                "url": "https://dblp.org/rec/conf/inlg/DusekK20",
            }
        }

        self.assertEqual(
            ut._derive_bib_url(hit, bibtex_format="condensed"),
            "https://dblp.org/rec/conf/inlg/DusekK20.bib?param=0",
        )
        self.assertEqual(
            ut._derive_bib_url(hit, bibtex_format="standard"),
            "https://dblp.org/rec/conf/inlg/DusekK20.bib?param=1",
        )
        self.assertEqual(
            ut._derive_bib_url(hit, bibtex_format="crossref"),
            "https://dblp.org/rec/conf/inlg/DusekK20.bib?param=2",
        )

    @patch("reffix.reffix.ut.get_dblp_results", return_value=[])
    def test_process_passes_selected_dblp_bibtex_format(self, get_dblp_results_mock):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "test.fixed.bib")

            reffix.process(
                "tests/test.bib",
                out_file,
                replace_arxiv=False,
                dblp_bibtex_format="crossref",
                force_titlecase=False,
                interact=False,
                no_publisher=False,
                process_conf_loc=False,
            )

        self.assertTrue(get_dblp_results_mock.called)
        _, kwargs = get_dblp_results_mock.call_args
        self.assertEqual(kwargs["bibtex_format"], "crossref")

    @patch("reffix.utils.requests.get")
    def test_crossref_bibtex_fetch_keeps_matching_paper_entry(self, get_mock):
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "key": "conf/inlg/DusekK20",
                                "url": "https://dblp.org/rec/conf/inlg/DusekK20",
                                "title": "Evaluating Semantic Accuracy of Data-to-Text Generation with Natural Language Inference",
                            }
                        }
                    ]
                }
            }
        }

        bib_response = Mock()
        bib_response.raise_for_status.return_value = None
        bib_response.text = """@inproceedings{DusekK20,
  author    = {Ondrej Dusek and Zdenek Kasner},
  title     = {Evaluating Semantic Accuracy of Data-to-Text Generation with Natural Language Inference},
  crossref  = {conf/inlg/2020}
}

@proceedings{conf/inlg/2020,
  title     = {Proceedings of the 13th International Conference on Natural Language Generation}
}"""

        get_mock.side_effect = [search_response, bib_response]

        results = ut.get_dblp_results(
            "Evaluating semantic accuracy of data-to-text generation with natural language inference",
            bibtex_format="crossref",
        )
        selected = reffix.select_entry(
            results,
            {
                "title": "Evaluating semantic accuracy of data-to-text generation with natural language inference",
                "author": "Du{\\v{s}}ek, Ond{\\v{r}}ej and Kasner, Zden{\\v{e}}k",
            },
            replace_arxiv=False,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(selected["ID"], "DusekK20")
        self.assertEqual(selected["crossref"], "conf/inlg/2020")
        get_mock.assert_any_call(
            "https://dblp.org/rec/conf/inlg/DusekK20.bib?param=2",
            params=None,
            timeout=30,
            headers=ut.DBLP_HEADERS,
        )

    @patch("reffix.utils.time.sleep")
    @patch("reffix.utils.requests.get")
    def test_get_dblp_results_retries_transient_server_errors(self, get_mock, sleep_mock):
        failed_response = Mock(status_code=500)
        failed_response.headers = {}
        search_response = Mock()
        search_response.status_code = 200
        search_response.headers = {}
        search_response.json.return_value = {"result": {"hits": {"hit": []}}}
        get_mock.side_effect = [failed_response, search_response]

        results = ut.get_dblp_results("retry me")

        self.assertEqual(results, [])
        sleep_mock.assert_any_call(2)

    @patch("reffix.utils.time.sleep")
    @patch("reffix.utils.requests.get")
    def test_get_dblp_results_keeps_long_backoff_after_429_connection_reset(self, get_mock, sleep_mock):
        rate_limited_response = Mock(status_code=429)
        rate_limited_response.headers = {}
        search_response = Mock()
        search_response.status_code = 200
        search_response.headers = {}
        search_response.json.return_value = {"result": {"hits": {"hit": []}}}
        get_mock.side_effect = [
            rate_limited_response,
            requests.ConnectionError("connection reset"),
            search_response,
        ]

        original_interval = ut._dblp_request_interval
        try:
            ut._dblp_request_interval = ut.DBLP_MIN_REQUEST_INTERVAL
            results = ut.get_dblp_results("retry me after 429")
        finally:
            ut._dblp_request_interval = original_interval

        self.assertEqual(results, [])
        sleep_calls = [call.args[0] for call in sleep_mock.call_args_list]
        self.assertIn(60, sleep_calls)
        self.assertIn(120, sleep_calls)

    def test_build_dblp_query_normalizes_bibtex_markup(self):
        entry = {
            "title": '"{W}e {N}eed {S}tructured {O}utput": {T}owards {U}ser-centered {C}onstraints on {L}arge {L}anguage {M}odel {O}utput'
        }

        query = ut.build_dblp_query(entry)

        self.assertEqual(
            query,
            "We Need Structured Output Towards User centered Constraints on Large Language Model Output",
        )

    def test_preserve_original_authors_keeps_diacritics(self):
        orig_entry = {
            "author": "Du{\\v{s}}ek, Ond{\\v{r}}ej and Kasner, Zden{\\v{e}}k",
        }
        new_entry = {
            "author": "Ondrej Dusek and\nZdenek Kasner",
        }

        merged_entry = ut.preserve_original_authors(orig_entry, new_entry)

        self.assertEqual(merged_entry["author"], orig_entry["author"])

    def test_preserve_original_authors_keeps_new_authors_when_they_differ(self):
        orig_entry = {
            "author": "Du{\\v{s}}ek, Ond{\\v{r}}ej",
        }
        new_entry = {
            "author": "Ondrej Dusek and Zdenek Kasner",
        }

        merged_entry = ut.preserve_original_authors(orig_entry, new_entry)

        self.assertEqual(merged_entry["author"], new_entry["author"])

    @patch("reffix.utils.bc.splitname")
    def test_get_authors_canonical_falls_back_when_splitname_breaks(self, splitname_mock):
        splitname_mock.side_effect = StopIteration()

        authors = ut.get_authors_canonical(
            {
                "author": "Da San Martino, Giovanni and Yu, Seunghak",
                "title": "Fine-Grained Analysis of Propaganda in News Article",
            }
        )

        self.assertEqual(authors, ["Giovanni Da San Martino", "Seunghak Yu"])

    def test_update_dblp_request_interval_increases_after_429(self):
        original_interval = ut._dblp_request_interval
        try:
            ut._dblp_request_interval = ut.DBLP_MIN_REQUEST_INTERVAL
            response = Mock(status_code=429, headers={"Retry-After": "3"})

            ut._update_dblp_request_interval(response=response)

            self.assertEqual(ut._dblp_request_interval, 3.0)
        finally:
            ut._dblp_request_interval = original_interval

    def test_update_dblp_request_interval_relaxes_after_success(self):
        original_interval = ut._dblp_request_interval
        try:
            ut._dblp_request_interval = 2.0
            response = Mock(status_code=200, headers={})

            ut._update_dblp_request_interval(response=response)

            self.assertEqual(ut._dblp_request_interval, 1.8)
        finally:
            ut._dblp_request_interval = original_interval

    def test_protect_titlecase(self):
        title = (
            "PartNet: {A} Large-Scale Benchmark for Fine-Grained and Hierarchical Part-Level 3D Object Understanding"
        )
        protected_title = ut.protect_titlecase(title)

        self.assertEqual(
            protected_title,
            "{PartNet}: {A} Large-Scale Benchmark for Fine-Grained and Hierarchical Part-Level {3D} Object Understanding",
        )

    def test_is_equivalent(self):
        entry1 = {"booktitle": "Test Book", "year": "2022", "pages": "1-10"}
        entry2 = {"journal": "Test Journal", "year": "2022", "pages": "1-10"}
        entry3 = {"booktitle": "Test Book XYZ", "year": "2022", "pages": "15-20"}
        entry4 = {"booktitle": "Test Book XYZ", "year": "2023", "pages": "15-20"}

        self.assertTrue(ut.is_equivalent(entry1, self.entry))
        self.assertTrue(ut.is_equivalent(entry2, self.entry))
        self.assertTrue(ut.is_equivalent(entry3, self.entry))
        self.assertFalse(ut.is_equivalent(entry4, self.entry))

    def test_is_arxiv(self):
        arxiv_entry1 = {"journal": "CoRR"}
        arxiv_entry2 = {"eprinttype": "arxiv"}
        arxiv_entry3 = {"url": "https://arxiv.org/abs/1234.56789"}
        non_arxiv_entry = {"journal": "Test Journal", "year": "2022", "pages": "1-10"}

        self.assertTrue(ut.is_arxiv(arxiv_entry1))
        self.assertTrue(ut.is_arxiv(arxiv_entry2))
        self.assertTrue(ut.is_arxiv(arxiv_entry3))
        self.assertFalse(ut.is_arxiv(non_arxiv_entry))

    def test_select_entry(self):
        entries = [
            {
                "title": "Test Entry",
                "author": "John Doe",
                "year": "2022",
                "pages": "1-10",
                "booktitle": "Test Book",
                "url": "https://arxiv.org/abs/1234.56789",
            },
            {
                "title": "Test Entry",
                "author": "John Doe",
                "year": "2022",
                "pages": "1-10",
                "booktitle": "Test Book",
            },
            {
                "title": "Test Entry 2",
                "author": "John Doe",
                "year": "2023",
                "pages": "1-10",
                "booktitle": "Test Book",
                "url": "https://arxiv.org/abs/1234.56789",
            },
        ]

        best_entry_1 = reffix.select_entry(entries, self.entry, replace_arxiv=True)
        best_entry_2 = reffix.select_entry(entries, self.entry, replace_arxiv=False)

        self.assertEqual(best_entry_1, entries[1])
        self.assertEqual(best_entry_2, entries[0])

    def test_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "test.fixed.bib")
            out_arxiv_file = os.path.join(temp_dir, "test.fixed_arxiv.bib")

            with patch("reffix.reffix.ut.get_dblp_results", return_value=[]):
                reffix.process(
                    "tests/test.bib",
                    out_file,
                    replace_arxiv=False,
                    dblp_bibtex_format="standard",
                    force_titlecase=False,
                    interact=False,
                    no_publisher=False,
                    process_conf_loc=False,
                )
                self.assertTrue(os.path.exists(out_file))

                reffix.process(
                    "tests/test.bib",
                    out_arxiv_file,
                    replace_arxiv=True,
                    dblp_bibtex_format="standard",
                    force_titlecase=False,
                    interact=False,
                    no_publisher=False,
                    process_conf_loc=False,
                )
                self.assertTrue(os.path.exists(out_arxiv_file))

            # check if we can parse the output file
            bp = BibTexParser(interpolate_strings=False, common_strings=True, ignore_nonstandard_types=False)

            with open(out_arxiv_file) as bibtex_file:
                bibtexparser.load(bibtex_file, parser=bp)

    def test_process_preserves_online_entries_and_total_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "main.fixed.bib")

            with patch("reffix.reffix.ut.get_dblp_results", return_value=[]):
                reffix.process(
                    "tests/main.bib",
                    out_file,
                    replace_arxiv=False,
                    dblp_bibtex_format="standard",
                    force_titlecase=False,
                    interact=False,
                    no_publisher=False,
                    process_conf_loc=False,
                )

            bp = BibTexParser(interpolate_strings=False, common_strings=True, ignore_nonstandard_types=False)
            with open("tests/main.bib") as input_bibtex_file:
                original_db = bibtexparser.load(input_bibtex_file, parser=bp)

            with open(out_file) as output_bibtex_file:
                output_text = output_bibtex_file.read()

            output_db = bibtexparser.loads(
                output_text,
                parser=BibTexParser(interpolate_strings=False, common_strings=True, ignore_nonstandard_types=False),
            )

            original_online_ids = {entry["ID"] for entry in original_db.entries if entry.get("ENTRYTYPE") == "online"}
            output_online_ids = {entry["ID"] for entry in output_db.entries if entry.get("ENTRYTYPE") == "online"}

            self.assertEqual(len(output_db.entries), len(original_db.entries))
            self.assertEqual(output_online_ids, original_online_ids)
            self.assertIn("@online{", output_text.lower())

    @patch("reffix.reffix.importlib.util.find_spec")
    @patch("reffix.reffix.importlib.invalidate_caches")
    @patch("reffix.reffix.subprocess.run")
    @patch("builtins.__import__")
    def test_ensure_spacy_nlp_downloads_model_with_current_interpreter(
        self,
        import_mock,
        run_mock,
        invalidate_caches_mock,
        find_spec_mock,
    ):
        spacy_module = SimpleNamespace(load=Mock(return_value="nlp"))

        def import_side_effect(name, *args, **kwargs):
            if name == "spacy":
                return spacy_module
            return __import__(name, *args, **kwargs)

        import_mock.side_effect = import_side_effect
        find_spec_mock.side_effect = [None, object()]

        nlp = reffix._ensure_spacy_nlp()

        self.assertEqual(nlp, "nlp")
        run_mock.assert_called_once_with(
            [reffix.sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
            check=True,
        )
        invalidate_caches_mock.assert_called_once()
        spacy_module.load.assert_called_once_with("en_core_web_sm")

    @patch("builtins.__import__")
    def test_ensure_spacy_nlp_requires_optional_dependency(self, import_mock):
        def import_side_effect(name, *args, **kwargs):
            if name == "spacy":
                raise ImportError("missing spacy")
            return __import__(name, *args, **kwargs)

        import_mock.side_effect = import_side_effect

        with self.assertRaisesRegex(RuntimeError, "optional spaCy dependency"):
            reffix._ensure_spacy_nlp()

    def test_local_dblp_builds_index_and_searches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_file = write_dblp_fixture(temp_dir)
            local_dblp = LocalDblp(xml_file)

            results = local_dblp.search("Evaluating Semantic Accuracy of Data to Text Generation")
            self.assertEqual(len(results), 1)
            entry = results[0]

            self.assertEqual(entry["ID"], "conf/inlg/DusekK20")
            self.assertEqual(entry["ENTRYTYPE"], "inproceedings")
            # the trailing dot is stripped and nested markup is flattened
            self.assertEqual(
                entry["title"], "Evaluating Semantic Accuracy of Data-to-Text Generation with Natural Language Inference"
            )
            self.assertEqual(entry["author"], "Ondrej Dusek and Zdenek Kasner")
            self.assertEqual(entry["pages"], "131--137")
            # the first electronic edition becomes the url, and the DOI link
            # yields the doi field, as in the BibTeX exports of the API
            self.assertEqual(entry["url"], "https://aclanthology.org/2020.inlg-1.19/")
            self.assertEqual(entry["doi"], "10.18653/V1/2020.INLG-1.19")
            # the crossref is resolved to the full venue name, as in the standard export
            self.assertEqual(
                entry["booktitle"],
                "Proceedings of the 13th International Conference on Natural Language Generation, INLG 2020",
            )
            self.assertEqual(entry["publisher"], "Association for Computational Linguistics")
            # the proceedings editors are inlined as well
            self.assertEqual(entry["editor"], "Brian Davis")
            self.assertEqual(entry["timestamp"], "2023-05-02")
            self.assertEqual(entry["bibsource"], "dblp computer science bibliography, https://dblp.org")
            # the proceedings entry is not part of the output, so no crossref
            # may be emitted (BibTeX rejects dangling crossrefs)
            self.assertNotIn("crossref", entry)

            results = local_dblp.search("llm2vec large language models are secretly powerful text encoders")
            self.assertEqual(len(results), 1)
            entry = results[0]

            # homonym suffixes are stripped and DTD entities are resolved
            self.assertEqual(entry["author"], "Parishad BehnamGhader and Kalervo Järvelin")
            # CoRR articles carry the arXiv identifier, as in the API exports
            self.assertEqual(entry["eprinttype"], "arXiv")
            self.assertEqual(entry["eprint"], "2404.05961")
            self.assertTrue(ut.is_arxiv(entry))

            results = local_dblp.search("numerical optimization")
            self.assertEqual(len(results), 1)
            entry = results[0]

            self.assertEqual(entry["ENTRYTYPE"], "book")
            # of multiple isbn elements (one per edition), the first is kept
            self.assertEqual(entry["isbn"], "978-0-387-98793-4")
            self.assertEqual(entry["url"], "https://doi.org/10.1007/b98874")
            self.assertEqual(entry["doi"], "10.1007/B98874")
            self.assertEqual(entry["urn"], "urn:nbn:de:test-123")
            # the API exports omit the page count and booktitle of monographs
            self.assertNotIn("pages", entry)
            self.assertNotIn("booktitle", entry)

            results = local_dblp.search("exploitation of structural sparsity in algorithmic differentiation")
            self.assertEqual(len(results), 1)
            entry = results[0]

            self.assertEqual(entry["ENTRYTYPE"], "phdthesis")
            self.assertEqual(entry["school"], "RWTH Aachen University")
            # the API exports omit the page count of theses as well
            self.assertNotIn("pages", entry)

            self.assertEqual(local_dblp.search("no such publication anywhere"), [])
            local_dblp.close()

    def test_local_dblp_reads_gzipped_dump(self):
        import gzip

        with tempfile.TemporaryDirectory() as temp_dir:
            xml_file = write_dblp_fixture(temp_dir)
            gz_file = xml_file + ".gz"
            with open(xml_file, "rb") as f_in, gzip.open(gz_file, "wb") as f_out:
                f_out.write(f_in.read())
            os.remove(xml_file)

            local_dblp = LocalDblp(gz_file)
            results = local_dblp.search("numerical optimization")
            local_dblp.close()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["ID"], "books/sp/NocedalW99")

    def test_select_entry_matches_titles_across_latex_and_unicode(self):
        # entries from the local DBLP dump carry unicode titles, while BibTeX
        # files typically encode accents in LaTeX; both must match
        orig_entry = {
            "title": 'Gr{\\"o}bner Bases and Applications',
            "author": "Doe, John",
        }
        candidate = {
            "title": "Gröbner Bases and Applications",
            "author": "John Doe",
            "year": "1998",
        }

        selected = reffix.select_entry([candidate], orig_entry, replace_arxiv=False)

        self.assertEqual(selected, candidate)

    def test_local_dblp_reuses_cached_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_file = write_dblp_fixture(temp_dir)

            local_dblp = LocalDblp(xml_file)
            local_dblp.close()
            index_mtime = os.path.getmtime(local_dblp.index_file)

            local_dblp = LocalDblp(xml_file)
            local_dblp.close()

            self.assertEqual(os.path.getmtime(local_dblp.index_file), index_mtime)

    def test_local_dblp_requires_dtd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_file = write_dblp_fixture(temp_dir)
            os.remove(os.path.join(temp_dir, "dblp.dtd"))

            with self.assertRaisesRegex(FileNotFoundError, "dblp.dtd"):
                LocalDblp(xml_file)

    def test_process_with_local_dblp_queries_no_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_file = write_dblp_fixture(temp_dir)
            in_file = os.path.join(temp_dir, "test.bib")
            out_file = os.path.join(temp_dir, "test.fixed.bib")

            with open(in_file, "w") as f:
                f.write(
                    "@misc{llm2vec,\n"
                    "  title = {LLM2Vec: Large Language Models Are Secretly Powerful Text Encoders},\n"
                    "  author = {BehnamGhader, Parishad},\n"
                    "  year = {2024}\n"
                    "}\n"
                )

            # neither the API wrapper nor the network (and with it the API
            # rate limiting) may be touched in local mode
            with patch("reffix.reffix.ut.get_dblp_results", side_effect=AssertionError("API must not be queried")):
                with patch("reffix.utils.requests.get", side_effect=AssertionError("no network requests allowed")):
                    reffix.process(
                        in_file,
                        out_file,
                        replace_arxiv=False,
                        dblp_bibtex_format="standard",
                        force_titlecase=False,
                        interact=False,
                        no_publisher=False,
                        process_conf_loc=False,
                        dblp_xml=xml_file,
                    )

            bp = BibTexParser(interpolate_strings=False, common_strings=True, ignore_nonstandard_types=False)
            with open(out_file) as bibtex_file:
                output_db = bibtexparser.load(bibtex_file, parser=bp)

            self.assertEqual(len(output_db.entries), 1)
            entry = output_db.entries[0]
            # the entry was replaced with the record from the local dump, keeping the original key
            self.assertEqual(entry["ID"], "llm2vec")
            self.assertEqual(entry["url"], "https://arxiv.org/abs/2404.05961")
            self.assertEqual(entry["journal"], "CoRR")


if __name__ == "__main__":
    unittest.main()
