"""Deduplication."""

from __future__ import annotations

from datetime import date

from app.models.event import Event, EventCategory
from app.providers.dedup import deduplicate


def _event(title, *, provider, city=None, description=None, start=date(2026, 9, 1)):
    return Event(
        title=title,
        description=description,
        url=f"https://{provider}.example.com/x",
        city=city,
        start_date=start,
        category=EventCategory.CONFERENCE,
        provider=provider,
    )


def test_duplicate_titles_same_date_collapse_keeping_most_complete():
    sparse = _event("PyConf India", provider="a")
    rich = _event("PyConf  India!", provider="b", city="Hyderabad", description="details")
    result = deduplicate([sparse, rich])
    assert len(result) == 1
    assert result[0].provider == "b"  # richer record kept
    assert result[0].city == "Hyderabad"


def test_same_title_different_dates_are_kept_separate():
    a = _event("DevConf", provider="a", start=date(2026, 9, 1))
    b = _event("DevConf", provider="a", start=date(2027, 9, 1))
    assert len(deduplicate([a, b])) == 2


def test_distinct_events_are_preserved():
    a = _event("Alpha", provider="a")
    b = _event("Beta", provider="a")
    assert len(deduplicate([a, b])) == 2
