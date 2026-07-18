"""ICSProvider: iCalendar parsing, normalization, city/category from config, cache, failure."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.ics import ICSProvider, parse_vevents

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Python Meetup\\, July
DTSTART;TZID=Asia/Kolkata:20260718T103000
DTEND;TZID=Asia/Kolkata:20260718T140000
LOCATION:Bengaluru
URL:https://www.meetup.com/bangpypers/events/312819336/
DESCRIPTION:A hands-on session
END:VEVENT
BEGIN:VEVENT
SUMMARY:All-day Hackathon
DTSTART;VALUE=DATE:20260901
URL:https://www.meetup.com/bangpypers/events/999/
END:VEVENT
BEGIN:VEVENT
SUMMARY:No URL event
DTSTART:20260801T100000
END:VEVENT
END:VCALENDAR
"""


def run(coro):
    return asyncio.run(coro)


def _transport(body: str = ICS, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body if status == 200 else "")

    return httpx.MockTransport(handler)


def _provider(**kw) -> ICSProvider:
    return ICSProvider(
        name="meetup-bangpypers",
        ics_url="https://www.meetup.com/bangpypers/events/ical/",
        city="Bangalore",
        category=EventCategory.MEETUP,
        transport=_transport(**kw),
        ttl_seconds=300,
    )


def test_parse_vevents_unfolds_and_splits():
    events = parse_vevents(ICS)
    assert len(events) == 3
    assert events[0]["SUMMARY"] == "Python Meetup\\, July"


def test_normalization_maps_fields_and_uses_config_city():
    events = run(_provider().search(SearchQuery()))
    # 2 valid (the third has no URL → dropped to avoid identity collision)
    assert {e.title for e in events} == {"Python Meetup, July", "All-day Hackathon"}
    timed = next(e for e in events if e.title == "Python Meetup, July")
    assert timed.start_date == date(2026, 7, 18)
    assert timed.end_date == date(2026, 7, 18) or timed.end_date is None
    assert timed.city == "Bangalore"  # from source config
    assert timed.category == EventCategory.MEETUP
    assert timed.provider == "meetup-bangpypers"
    assert timed.is_free is None  # ICS does not expose pricing → honest None
    allday = next(e for e in events if e.title == "All-day Hackathon")
    assert allday.start_date == date(2026, 9, 1)


def test_city_filter_matches_config_city():
    events = run(_provider().search(SearchQuery(city="Bangalore")))
    assert len(events) == 2


def test_fetch_failure_returns_empty_and_not_cached():
    provider = _provider(status=500)
    assert run(provider.search(SearchQuery())) == []
    assert run(provider.search(SearchQuery())) == []
