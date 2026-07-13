"""The QueryParser interface — one of the two architectural seams.

The application depends on this contract, never on Gemini. Any parser (Gemini,
deterministic, or a future model) implements `parse()` and returns a validated
SearchQuery. It must never raise for user input: a parser always returns a valid
SearchQuery, degrading rather than failing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.search import SearchQuery


class QueryParser(ABC):
    """Converts natural-language text into a validated SearchQuery."""

    @abstractmethod
    async def parse(self, text: str) -> SearchQuery:
        """Return a valid SearchQuery for `text`. Never raises for user input."""
        raise NotImplementedError
