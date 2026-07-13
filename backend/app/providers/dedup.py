"""Deduplication of merged events.

Two providers can list the same event under different URLs, so the dedup key is
(normalized title, start_date) rather than URL. When duplicates collide, the more
complete record is kept.
"""

from __future__ import annotations

import re

from app.models.event import Event
from app.providers.ranking import completeness

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _title_key(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.casefold()).strip()


def deduplicate(events: list[Event]) -> list[Event]:
    best: dict[tuple[str, object], Event] = {}
    for event in events:
        key = (_title_key(event.title), event.start_date)
        current = best.get(key)
        if current is None or completeness(event) > completeness(current):
            best[key] = event
    return list(best.values())
