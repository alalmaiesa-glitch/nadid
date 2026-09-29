from __future__ import annotations

from app.contracts import DocumentNode, Suggestion
from app.pipeline.arabic_review import review_arabic_document


def fast_review(nodes: list[DocumentNode]) -> list[Suggestion]:
    """
    Backward-compatible entry point for the fast review pipeline.

    The implementation is now delegated to the structured Arabic
    Language & Style Review Engine so API and worker callers do not need
    to change while the review core can evolve independently.
    """
    return review_arabic_document(nodes)
