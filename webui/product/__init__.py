"""Product-facing Streamlit pages for El Centinela del Universo."""

from . import pages, review

# The old boolean review page is retained only as implementation history inside
# pages.py. Any package-level consumer that resolves pages.review_page is routed
# to the structured seven-gate review implementation.
pages.review_page = review.review_page

__all__ = ["pages", "review"]
