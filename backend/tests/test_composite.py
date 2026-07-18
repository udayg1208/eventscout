"""CompositeProvider: parallel fan-out, merge, city normalization, dedup, failure."""

from __future__ import annotations

import asyncio
from datetime import date

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.composite import CompositeProvider

TODAY = date(2026, 7, 1)


def run(coro):
    return asyncio.run(coro)


def _event(
    title,
    *,
    provider,
    city=None,
    description=None,
    start=date(2026, 9, 1),
    category=EventCategory.CONFERENCE,
):
    return Event(
        title=title,
        description=description,
        url=f"https://{provider}.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        start_date=start,
        category=category,
        provider=provider,
    )


class StubProvider(EventProvider):
    def __init__(self, name, events=None, error=None):
        self.name = name
        self._events = events or []
        self._error = error

    async def search(self, query):
        if self._error is not None:
            raise self._error
        return list(self._events)


def _composite(*providers):
    return CompositeProvider(list(providers), today=TODAY)


def test_single_provider_success():
    p = StubProvider("a", [_event("Alpha", provider="a"), _event("Beta", provider="a")])
    events = run(_composite(p).search(SearchQuery()))
    assert {e.title for e in events} == {"Alpha", "Beta"}


def test_multi_provider_results_are_merged():
    a = StubProvider("a", [_event("Alpha", provider="a")])
    b = StubProvider("b", [_event("Beta", provider="b")])
    events = run(_composite(a, b).search(SearchQuery()))
    assert {e.title for e in events} == {"Alpha", "Beta"}


def test_one_provider_failure_does_not_break_the_others():
    good = StubProvider("good", [_event("Alpha", provider="good")])
    bad = StubProvider("bad", error=RuntimeError("boom"))
    events = run(_composite(good, bad).search(SearchQuery()))
    assert {e.title for e in events} == {"Alpha"}


def test_duplicate_events_across_providers_are_deduplicated():
    same_day = date(2026, 9, 1)
    a = StubProvider("a", [_event("PyConf India", provider="a", start=same_day)])
    b = StubProvider(
        "b",
        [_event("PyConf India", provider="b", start=same_day, city="Hyderabad", description="d")],
    )
    events = run(_composite(a, b).search(SearchQuery()))
    assert len(events) == 1
    assert events[0].city == "Hyderabad"  # richer record survived


def test_city_is_canonicalized_in_output():
    p = StubProvider("a", [_event("AI Conf", provider="a", city="Bengaluru")])
    events = run(_composite(p).search(SearchQuery()))
    assert events[0].city == "Bangalore"  # normalized at the boundary


# --------------------------- classification (Phase 2 #1) ---------------------------


def test_meetup_classified_and_ai_filter_matches():
    p = StubProvider(
        "a",
        [
            _event("GenAI Builders Meetup", provider="a", category=EventCategory.MEETUP),
            _event("Rust Bangalore Meetup", provider="a", category=EventCategory.MEETUP),
        ],
    )
    # An "AI events" query (category filter would have dropped these at the provider,
    # but the composite strips it, classifies, then filters).
    events = run(_composite(p).search(SearchQuery(categories=[EventCategory.AI])))
    assert [e.title for e in events] == ["GenAI Builders Meetup"]
    assert events[0].category == EventCategory.AI


def test_specific_category_preserved_under_ai_filter():
    p = StubProvider("a", [_event("AI Hackathon", provider="a", category=EventCategory.HACKATHON)])
    # AI-themed hackathon keeps its format category, so it is not an `ai` result...
    assert run(_composite(p).search(SearchQuery(categories=[EventCategory.AI]))) == []
    # ...but is still found by a hackathon search.
    hack = run(_composite(p).search(SearchQuery(categories=[EventCategory.HACKATHON])))
    assert [e.title for e in hack] == ["AI Hackathon"]
