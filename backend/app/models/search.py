"""The SearchQuery model — normalized search parameters.

This is the provider-facing contract: every provider's `search()` consumes a
SearchQuery. Gemini (Milestone 3) is one producer of it; in tests and early
milestones we construct it by hand. Keeping it decoupled from Gemini is what lets
us prove the whole pipeline without any AI.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator

from app.models.event import EventCategory


class SearchQuery(BaseModel):
    """Structured search parameters. Every field defaults to "no constraint",
    so an empty SearchQuery means "match everything"."""

    keywords: list[str] = []
    city: str | None = None
    categories: list[EventCategory] = []
    date_from: date | None = None
    date_to: date | None = None
    free_only: bool = False

    @model_validator(mode="after")
    def _check_date_range(self) -> SearchQuery:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self
