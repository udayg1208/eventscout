"""Ranking correctness."""

from __future__ import annotations

from datetime import date

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.ranking import completeness, rank

TODAY = date(2026, 7, 1)


def _event(
    title,
    *,
    start,
    city=None,
    description=None,
    end_date=None,
    price=None,
    is_free=None,
    category=EventCategory.CONFERENCE,
):
    return Event(
        title=title,
        description=description,
        url="https://example.com/" + title.replace(" ", "-").lower(),
        city=city,
        end_date=end_date,
        price=price,
        is_free=is_free,
        start_date=start,
        category=category,
        provider="t",
    )


def test_relevance_dominates_ranking():
    query = SearchQuery(keywords=["python"])
    relevant = _event("Python Summit", start=date(2026, 12, 1))  # keyword in title
    other = _event("Java Meetup", start=date(2026, 7, 2))  # sooner, but irrelevant
    ranked = rank([other, relevant], query, TODAY)
    assert ranked[0].title == "Python Summit"


def test_date_proximity_breaks_ties_when_relevance_equal():
    query = SearchQuery()  # no relevance signal
    soon = _event("A", start=date(2026, 7, 5))
    later = _event("B", start=date(2026, 10, 5))
    ranked = rank([later, soon], query, TODAY)
    assert [e.title for e in ranked] == ["A", "B"]


def test_completeness_used_when_relevance_and_date_equal():
    query = SearchQuery()
    same_day = date(2026, 8, 1)
    rich = _event(
        "Rich",
        start=same_day,
        city="Pune",
        description="d",
        end_date=date(2026, 8, 2),
        price="Free",
        is_free=True,
    )
    sparse = _event("Sparse", start=same_day)
    assert completeness(rich) > completeness(sparse)
    ranked = rank([sparse, rich], query, TODAY)
    assert ranked[0].title == "Rich"


def test_past_events_rank_below_upcoming_with_equal_relevance():
    query = SearchQuery()
    past = _event("Past", start=date(2026, 6, 1))  # before TODAY
    upcoming = _event("Upcoming", start=date(2026, 7, 10))
    ranked = rank([past, upcoming], query, TODAY)
    assert ranked[0].title == "Upcoming"
