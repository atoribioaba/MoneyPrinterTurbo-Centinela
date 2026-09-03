"""Product-facing Streamlit pages for El Centinela del Universo."""

from . import pages, publication, review, studio, ui

# Structured human review remains the only product review boundary.
pages.review_page = review.review_page

# G-006 productive manual-package implementation remains the public publication page.
pages.publication_page = publication.publication_page

__all__ = ["pages", "publication", "review", "studio", "ui"]
