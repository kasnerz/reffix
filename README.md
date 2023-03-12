# reffix: Fixing BibTeX reference list with DBLP API 🔧

➡️ *Reffix* is a simple tool for improving the BibTeX list of references in your paper. It can fix several common errors such as incorrect capitalization, missing URLs, or using arXiv pre-prints instead of published version.

➡️ *Reffix* queries the **[DBLP API](https://dblp.org/faq/How+to+use+the+dblp+search+API.html)**, so it does not require any local database of papers.

➡️ *Reffix* uses a conservative approach to keep your bibliography valid. 

➡️ The tool is developed with NLP papers in mind, but it can be used on any BibTeX list of references containing computer science papers present on [DBLP](https://dblp.org).

## Quickstart

👉️ You can now install `reffix` from [PyPI](https://pypi.org/project/reffix/):
```
pip install -U reffix
reffix [BIB_FILE]
```

See the Installation and Usage section below for more details.

## Example
**Before the update (Google Scholar):** 
- ❎ arXiv version 
- ❎ no URL 
- ❎ capitalization lost
```
 {  
    'ENTRYTYPE': 'article',
    'ID': 'duvsek2020evaluating',
    'author': 'Du{\\v{s}}ek, Ond{\\v{r}}ej and Kasner, Zden{\\v{e}}k',
    'journal': 'arXiv preprint arXiv:2011.10819',
    'title': 'Evaluating semantic accuracy of data-to-text generation with '
             'natural language inference',
    'year': '2020'
}

```
**After the update (DBLP + preserving capitalization):**
- ✔️ ACL version
- ✔️ URL included
- ✔️ capitalization preserved 
```
 {   
    'ENTRYTYPE': 'inproceedings',
    'ID': 'duvsek2020evaluating',
    'author': 'Ondrej Dusek and\nZdenek Kasner',
    'bibsource': 'dblp computer science bibliography, https://dblp.org',
    'biburl': 'https://dblp.org/rec/conf/inlg/DusekK20.bib',
    'booktitle': 'Proceedings of the 13th International Conference on Natural '
                 'Language\n'
                 'Generation, {INLG} 2020, Dublin, Ireland, December 15-18, '
                 '2020',
    'editor': 'Brian Davis and\n'
              'Yvette Graham and\n'
              'John D. Kelleher and\n'
              'Yaji Sripada',
    'pages': '131--137',
    'publisher': 'Association for Computational Linguistics',
    'timestamp': 'Mon, 03 Jan 2022 00:00:00 +0100',
    'title': '{Evaluating} {Semantic} {Accuracy} of {Data-to-Text} '
             '{Generation} with {Natural} {Language} {Inference}',
    'url': 'https://aclanthology.org/2020.inlg-1.19/',
    'year': '2020'
}
```

## Main features
- **Completing references** – *reffix* queries the DBLP API with the paper title and the first author's name to find a complete reference for each entry in the BibTeX file. 
- **Replacing arXiv preprints** –  *reffix* can try to replace arXiv pre-prints with the version published at a conference or in a journal whenever possible.
- **Preserving titlecase** – in order to [preserve correct casing](https://tex.stackexchange.com/questions/10772/bibtex-loses-capitals-when-creating-bbl-file), *reffix* wraps individual uppercased words in the paper title in curly brackets.
- **Conservative approach**: 
  + the original .bib file is preserved 
  + no references are deleted
  + papers are updated only if the title and at least one of the authors match
  + the version of the paper corresponding to the original entry should be selected first
- **Interactive mode** – you can confirm every change manually.

The package uses [bibtexparser](https://github.com/sciunto-org/python-bibtexparser) for parsing the BibTex files, [DBLP API](https://dblp.org/faq/How+to+use+the+dblp+search+API.html) for updating the references, and the [titlecase](https://github.com/ppannuto/python-titlecase) package for optional extra titlecasing.


## Installation

You can install `reffix` from [PyPI](https://pypi.org/project/reffix/):
```
pip install reffix
```

For development, you can install the package in the editable mode:
```
pip install -e .
```
## Usage
Run the script with the .bib file as the first argument:
```
reffix [IN_BIB_FILE]
```
By default, the program will run in batch mode, save the outputs in the file with an extra ".fixed" suffix, and keep the arXiv versions.

The following command will run reffix in interactive mode, save the outputs to a custom file, and replace arXiv versions:
```
reffix [IN_BIB_FILE] -o [OUT_BIB_FILE] -i -a
```
### Flags
| short | long                | description                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `-o`  | `--out`             | Output filename. If not specified, the default filename `<original_name>.fixed.bib` is used.                                                                                                                                                                                                                                                                                                                       |
| `-i`  | `--interact`        | Interactive mode. Every replacement of an entry with DBLP result has to be confirmed manually.                                                                                                                                                                                                                                                                                                                     |
| `-a`  | `--replace_arxiv`   | Replace arXiv versions. If a non-arXiv version (e.g. published at a conference or in a journal) is found at DBLP, it is preferred to the arXiv version.                                                                                                                                                                                                                                                            |
| `-t`  | `--force_titlecase` | Force titlecase for all entries. The `titlecase` package is used to fix casing of titles which are not titlecased. (Note that the capitalizaton rules used by the package may be a bit different.)                                                                                                                                                                                                                 |
| `-s`  | `--sort_by`         | Multiple sort conditions compatible with [bibtexparser.BibTexWriter](https://bibtexparser.readthedocs.io/en/master/_modules/bibtexparser/bwriter.html) applied in the provided order. Example: `-s ENTRYTYPE year` sorts the list by the entry type as its primary key and year as its secondary key. `ID` can be used to refer to the Bibtex key. The default None value keeps the original order of Bib entries. |

## Notes
Although *reffix* uses a conservative approach, it provides no guarantees that the output references are actually correct. 

If you want to make sure that *reffix* does not introduce any unwanted changes, please use the interactive mode (flag `-i`).

The tool depends on **DBLP API** which may change any time in the future. I will try to update the script if necessary, but it may still occasionally break. I welcome any pull requests with improvements.

Please be considerate regarding the DBLP API and do not generate high traffic for their servers :-) 

## Contact
For any questions or suggestions, send an e-mail to kasner@ufal.mff.cuni.cz.