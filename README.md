# reffix

Fix common errors in BibTeX bibliography files:
- missing URLs
- incorrect capitalization
- using arXiv preprints instead of published version

The package uses the DBLP API: https://dblp.org/faq/How+to+use+the+dblp+search+API.html

Use with caution not to overload the servers. Please note that the API may also change in future.

The package uses a conservative approach:
- if possible, the matching reference is selected
- no references are deleted