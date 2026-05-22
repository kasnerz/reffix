import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, Mock
import requests
import reffix.reffix as reffix
import reffix.utils as ut
import bibtexparser
from bibtexparser.bparser import BibTexParser


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
            bp = BibTexParser(interpolate_strings=False, common_strings=True)

            with open(out_arxiv_file) as bibtex_file:
                bibtexparser.load(bibtex_file, parser=bp)

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


if __name__ == "__main__":
    unittest.main()
