"""Product-facing Streamlit pages for El Centinela del Universo."""

from . import pages, publication, review

# The old boolean review page is retained only as implementation history inside
# pages.py. Any package-level consumer that resolves pages.review_page is routed
# to the structured seven-gate review implementation.
pages.review_page = review.review_page

# G-006 follows the same product-facade pattern: keep the legacy publication
# placeholder in pages.py as history, but route the public page to the productive
# manual-package implementation.
pages.publication_page = publication.publication_page

__all__ = ["pages", "publication", "review"]
