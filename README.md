# reffix: Fixing BibTeX reference list with DBLP API :wrench:

:arrow_right: *Reffix* is a simple tool for improving the BibTeX list of references in your paper. It can fix several common errors such as incorrect capitalization, missing URLs, or using arXiv pre-prints instead of published version.


:arrow_right: *Reffix* uses a **conservative approach** to keep your bibliography valid. It also does not require any local database of papers since it uses online queries to **DBLP API**.

:arrow_right: The tool is developed with NLP papers in mind, but it can be used on any BibTeX list of references.

## Example
**Before the update (Google Scholar):** 
- :negative_squared_cross_mark: arXiv version 
- :negative_squared_cross_mark: no URL 
- :negative_squared_cross_mark: capitalization lost
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
- :heavy_check_mark: ACL version
- :heavy_check_mark: URL included
- :heavy_check_mark: capitalization preserved 
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
- **Completing references** – *reffix* queries DBLP API to find a complete reference for each entry in the BibTeX file. 
- **Replacing arXiv preprints** –  *reffix* can replace arXiv pre-prints with the version published at a conference or in a journal.
- **Preserving titlecase** – in order to [preserve correct casing](https://tex.stackexchange.com/questions/10772/bibtex-loses-capitals-when-creating-bbl-file), *reffix* wraps individual title-cased words in the title using the curly brackets.
- **Conservative approach**: 
  + the original .bib file is preserved 
  + no references are deleted
  + papers are updated only if the title and at least one of the authors match
  + the version of the paper corresponding to the original entry should be selected first
- **Interactive mode** – you can confirm every change manually.

The package uses [bibtexparser](https://github.com/sciunto-org/python-bibtexparser) for parsing the BibTex files, [DBLP API](https://dblp.org/faq/How+to+use+the+dblp+search+API.html) for updating the references, and the [titlecase](https://github.com/ppannuto/python-titlecase) package for optional extra titlecasing of the titles.


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

## Contact
For any questions or suggestions, send an e-mail to kasner@ufal.mff.cuni.cz.