"""Deterministic keyword parser.

Zero-dependency, no-network fallback that always returns a valid SearchQuery. Used
both as the standalone parser when no Gemini key is configured, and as the last-
resort fallback inside GeminiQueryParser. It intentionally does simple, predictable
extraction (city, category, free flag, keywords) and does NOT attempt relative-date
resolution — dates stay None rather than being guessed.

City aliases are normalized here (e.g. "Bengaluru" -> "Bangalore"), honoring the
project rule to normalize provider/input quirks at the boundary.
"""

from __future__ import annotations

import re

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.parsers.base import QueryParser

# alias (lowercase) -> canonical display name
_CITY_ALIASES: dict[str, str] = {
    "bangalore": "Bangalore",
    "bengaluru": "Bangalore",
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "pune": "Pune",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "hyderabad": "Hyderabad",
    "chennai": "Chennai",
    "madras": "Chennai",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",
    "gurgaon": "Gurgaon",
    "gurugram": "Gurgaon",
    "noida": "Noida",
    "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur",
    "kochi": "Kochi",
    "chandigarh": "Chandigarh",
}

# Each category maps to regex triggers (word-boundary matched, case-insensitive).
_CATEGORY_TRIGGERS: dict[EventCategory, list[str]] = {
    EventCategory.HACKATHON: [r"hackathons?"],
    EventCategory.WORKSHOP: [r"workshops?"],
    EventCategory.WEBINAR: [r"webinars?"],
    EventCategory.MEETUP: [r"meet\s?ups?"],
    EventCategory.CONFERENCE: [r"conferences?", r"\bconf\b", r"summits?"],
    EventCategory.STARTUP: [r"startups?"],
    EventCategory.AI: [
        r"\bai\b",
        r"\bml\b",
        r"machine learning",
        r"artificial intelligence",
        r"deep learning",
        r"\bllms?\b",
        r"generative ai",
        r"gen ai",
    ],
}

# Short trigger tokens removed from free-text keywords (topical words like
# "machine"/"learning" are deliberately kept so keyword search still works).
_TRIGGER_TOKENS = {
    "hackathon",
    "hackathons",
    "workshop",
    "workshops",
    "webinar",
    "webinars",
    "meetup",
    "meetups",
    "conference",
    "conferences",
    "conf",
    "summit",
    "summits",
    "startup",
    "startups",
    "ai",
    "ml",
}

_STOPWORDS = {
    "in",
    "on",
    "at",
    "the",
    "a",
    "an",
    "for",
    "this",
    "next",
    "near",
    "me",
    "of",
    "to",
    "and",
    "or",
    "happening",
    "around",
    "find",
    "show",
    "events",
    "event",
    "upcoming",
    "by",
    "with",
    "some",
    "any",
    "is",
    "are",
    "there",
}


class KeywordQueryParser(QueryParser):
    """Rule-based extraction; always yields a valid SearchQuery."""

    async def parse(self, text: str) -> SearchQuery:
        low = text.casefold().strip()
        if not low:
            return SearchQuery()

        return SearchQuery(
            keywords=self._keywords(low),
            city=self._city(low),
            categories=self._categories(low),
            free_only=self._free(low),
        )

    @staticmethod
    def _city(low: str) -> str | None:
        # Longest alias first so "new delhi" wins over "delhi".
        for alias in sorted(_CITY_ALIASES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", low):
                return _CITY_ALIASES[alias]
        return None

    @staticmethod
    def _categories(low: str) -> list[EventCategory]:
        found: list[EventCategory] = []
        for category, patterns in _CATEGORY_TRIGGERS.items():
            if any(re.search(p, low) for p in patterns):
                found.append(category)
        return found

    @staticmethod
    def _free(low: str) -> bool:
        return bool(re.search(r"\bfree\b", low))

    @staticmethod
    def _keywords(low: str) -> list[str]:
        removable = _STOPWORDS | _TRIGGER_TOKENS | {"free"}
        for alias in _CITY_ALIASES:
            removable.update(alias.split())
        keywords: list[str] = []
        for token in re.findall(r"[a-z0-9+#]+", low):
            if len(token) > 1 and token not in removable and token not in keywords:
                keywords.append(token)
        return keywords
