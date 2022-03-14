# reffix: A tool for fixing and completing BibTeX references using DBLP API :wrench:

:arrow_right: *Reffix* is a simple tool for improving the BibTeX list of references in your paper. It can fix several common errors such as incorrect capitalization, missing URLs or using arXiv pre-prints instead of published version.


:arrow_right: *Reffix* uses a **conservative approach** to keep your bibliography valid. It also does not require any local database of papers since it uses online queries for **DBLP API**.

:arrow_right: The tool is developed with NLP papers in mind, but it can be used on any BibTeX list of references.

## Example
**Before the update:** 
- :negative_squared_cross_mark: arXiv version 
- :negative_squared_cross_mark: no URL 
- :negative_squared_cross_mark: capitalization lost
```
{
    'ENTRYTYPE': 'inproceedings',
    'ID': 'Lee2018HigherorderCR',
    'author': 'Kenton Lee and Luheng He and L. Zettlemoyer',
    'booktitle': 'NAACL-HLT',
    'title': 'Higher-order Coreference Resolution with Coarse-to-fine '
             'Inference',
    'year': '2018'
}
```

**After the update:**
- :ballot_box_with_check: ACL version
- :ballot_box_with_check: URL included
- :ballot_box_with_check: capitalization preserved 
```
 {  
    'ENTRYTYPE': 'inproceedings',
    'ID': 'Lee2018HigherorderCR',
    'author': 'Kenton Lee and\nLuheng He and\nLuke Zettlemoyer',
    'bibsource': 'dblp computer science bibliography, https://dblp.org',
    'biburl': 'https://dblp.org/rec/conf/naacl/LeeHZ18.bib',
    'booktitle': 'Proceedings of the 2018 Conference of the North American '
                 'Chapter of\n'
                 'the Association for Computational Linguistics: Human '
                 'Language Technologies,\n'
                 'NAACL-HLT, New Orleans, Louisiana, USA, June 1-6, 2018, '
                 'Volume 2 (Short\n'
                 'Papers)',
    'doi': '10.18653/v1/n18-2108',
    'editor': 'Marilyn A. Walker and\nHeng Ji and\nAmanda Stent',
    'pages': '687--692',
    'publisher': 'Association for Computational Linguistics',
    'timestamp': 'Fri, 06 Aug 2021 01:00:00 +0200',
    'title': '{Higher-Order} {Coreference} {Resolution} with {Coarse-to-Fine} '
             '{Inference}',
    'url': 'https://doi.org/10.18653/v1/n18-2108',
    'year': '2018'
}

```

## Main features
- **Completing references** – *reffix* queries DBLP API to find a complete reference for each entry in the BibTeX file. 
- **Replacing arXiv preprints** –  *reffix* can replace arXiv pre-prints with the version published at a conference or in a journal.
- **Preserving titlecase** – in order to [preserve correct casing](https://tex.stackexchange.com/questions/10772/bibtex-loses-capitals-when-creating-bbl-file), *reffix* wraps individual title-cased words in the title using the curly brackets
- **Conservative approach**: 
  + the original .bib file is preserved 
  + no references are deleted
  + papers are updated only if the title and at least one of the authors match
  + the version of the paper corresponding to the original entry should be selected first
- **Interactive mode** – you can confirm every change manually.

The package uses [bibtexparser](https://github.com/sciunto-org/python-bibtexparser) for parsing the BibTex files, [DBLP API](https://dblp.org/faq/How+to+use+the+dblp+search+API.html) for updating the references and the [titlecase](https://github.com/ppannuto/python-titlecase) package for optional titlecasing of papers not found in DBLP.


## Usage

1. Clone the repository and install the requirements:
```
git clone https://github.com/kasnerz/reffix.git
cd reffix
pip install -r requirements.txt
```
2. Run the script with the .bib file as the first argument:
```
./reffix.py path/to/bibtex_file.bib
```
Or with all the features enabled:
```
./reffix.py -iat path/to/bibtex_file.bib -o path/to/output_file.bib
```
### Flags
| short | long | description |
| ---------- | ---------------------- |-----------  |
| `-o`       | `--out`   | Output filename. If not specified, the default filename `<original_name>.fixed` is used. |
| `-i` | `--interact` | Interactive mode. Every replacement of an entry with DBLP result has to be confirmed manually. |
| `-a` | `--replace_arxiv` | Replace arXiv versions. If a non-arXiv version (e.g. published at a conference or in a journal) is found at DBLP, it is preferred to the arXiv version. |
| `-t` | `--force_titlecase` | Force titlecase for all entries. The `titlecase` package is used to fix casing of titles also for the entries not found on DBLP. (Note that the capitalizaton rules used by the package may be a bit different, which is why by default the capitalization at DBLP is assumed to be correct.)|

## Notes
Although *reffix* uses a conservative approach, it provides **no guarantees** that the output references are actually correct. 

If you want to make sure that *reffix* does not introduce any unwanted changes, please use the interactive mode (flag `-i`).

The tool depends on **DBLP API** which is subject to change. I will try to update the project if necessary, but it may still occasionally break. I welcome any pull requests with improvements.

Please be considerate regarding the DBLP API and do not generate high traffic for their servers.