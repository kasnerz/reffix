import unittest
import os
from unittest.mock import patch, Mock
import reffix.reffix as reffix


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
        results = reffix.get_dblp_results(query)
        self.assertGreaterEqual(len(results), 1)

    def test_protect_titlecase(self):
        title = "Test {T}itle in a 3-D U-Net Spatially-Varying Mip-NeRF"
        protected_title = reffix.protect_titlecase(title)

        self.assertEqual(protected_title, "{T}est {T}itle in a 3-{D} {U}-{N}et {S}patially-Varying {M}ip-{N}e{R}{F}")

    def test_is_equivalent(self):
        entry1 = {"booktitle": "Test Book", "year": "2022", "pages": "1-10"}
        entry2 = {"journal": "Test Journal", "year": "2022", "pages": "1-10"}
        entry3 = {"booktitle": "Test Book XYZ", "year": "2022", "pages": "15-20"}
        entry4 = {"booktitle": "Test Book XYZ", "year": "2023", "pages": "15-20"}

        self.assertTrue(reffix.is_equivalent(entry1, self.entry))
        self.assertTrue(reffix.is_equivalent(entry2, self.entry))
        self.assertTrue(reffix.is_equivalent(entry3, self.entry))
        self.assertFalse(reffix.is_equivalent(entry4, self.entry))

    def test_is_arxiv(self):
        arxiv_entry1 = {"journal": "CoRR"}
        arxiv_entry2 = {"eprinttype": "arxiv"}
        arxiv_entry3 = {"url": "https://arxiv.org/abs/1234.56789"}
        non_arxiv_entry = {"journal": "Test Journal", "year": "2022", "pages": "1-10"}

        self.assertTrue(reffix.is_arxiv(arxiv_entry1))
        self.assertTrue(reffix.is_arxiv(arxiv_entry2))
        self.assertTrue(reffix.is_arxiv(arxiv_entry3))
        self.assertFalse(reffix.is_arxiv(non_arxiv_entry))

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
        reffix.process(
            "tests/test.bib", "tests/test.fixed.bib", replace_arxiv=False, force_titlecase=False, interact=False
        )
        self.assertTrue(os.path.exists("tests/test.fixed.bib"))

        reffix.process(
            "tests/test.bib", "tests/test.fixed_arxiv.bib", replace_arxiv=True, force_titlecase=False, interact=False
        )
        self.assertTrue(os.path.exists("tests/test.fixed_arxiv.bib"))

        os.remove("tests/test.fixed.bib")
        os.remove("tests/test.fixed_arxiv.bib")


if __name__ == "__main__":
    unittest.main()
