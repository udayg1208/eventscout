"""Shared title -> category helper.

Some sources state the event type in the title (e.g. "... Meetup", "... Workshop")
but expose no structured type field. This maps those stated types to a category,
falling back to a per-source default. It reads only what the title says — it does
not invent a type.
"""

from __future__ import annotations

from app.models.event import EventCategory

_TITLE_KEYWORDS: list[tuple[str, EventCategory]] = [
    ("hackathon", EventCategory.HACKATHON),
    ("workshop", EventCategory.WORKSHOP),
    ("webinar", EventCategory.WEBINAR),
    ("meetup", EventCategory.MEETUP),
    ("meet up", EventCategory.MEETUP),
    ("conference", EventCategory.CONFERENCE),
    ("summit", EventCategory.CONFERENCE),
]


def category_from_title(title: str, *, default: EventCategory) -> EventCategory:
    """Return the category named in the title, else `default`."""
    t = title.casefold()
    for keyword, category in _TITLE_KEYWORDS:
        if keyword in t:
            return category
    return default
