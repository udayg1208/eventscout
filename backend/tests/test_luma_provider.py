"""LumaProvider: embedded-JSON extraction, IST dates, online/offline, dedup, cache, failure."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.luma import (
    LumaProvider,
    _ist_date,
    extract_events,
    normalize_event,
)

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


def _ev(name, slug, start, end=None, location_type="offline"):
    e = {"name": name, "url": slug, "start_at": start, "location_type": location_type}
    if end:
        e["end_at"] = end
    return e


def _page(events: list[dict]) -> str:
    nd = {
        "props": {
            "pageProps": {"initialData": {"data": {"events": [{"event": e} for e in events]}}}
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(nd)}</script></body></html>"
    )


BENGALURU = [
    _ev(
        "Gemma x Hugging Face Bengaluru Meetup",
        "cqo8g0a2",
        "2026-07-15T12:00:00.000Z",
        "2026-07-15T16:00:00.000Z",
    ),
    _ev("AI Workshop", "wshop1", "2026-08-01T05:00:00.000Z"),
    _ev("Online DevOps Talk", "onl1", "2026-07-20T13:00:00.000Z", location_type="online"),
    _ev("Past Meetup", "past1", "2026-06-01T05:00:00.000Z"),  # past -> filtered
    _ev("Cross City", "dup1", "2026-07-18T05:00:00.000Z"),  # also on Mumbai page
]
MUMBAI = [
    _ev("Mumbai Startup Mixer", "mum1", "2026-07-25T10:00:00.000Z"),
    _ev("Cross City", "dup1", "2026-07-18T05:00:00.000Z"),  # duplicate of Bengaluru
]


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        slug = request.url.path.strip("/")
        calls.append(slug)
        if status != 200:
            return httpx.Response(status)
        pages = {"bengaluru": BENGALURU, "mumbai": MUMBAI}
        return httpx.Response(200, text=_page(pages.get(slug, [])))

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> LumaProvider:
    return LumaProvider(
        transport=_transport(calls, status),
        ttl_seconds=300,
        today=TODAY,
        cities={"bengaluru": "Bangalore", "mumbai": "Mumbai", "empty": "Nowhere"},
    )


# --------------------------- helpers ---------------------------


def test_ist_date_converts_utc_to_local_day():
    assert _ist_date("2026-07-15T12:00:00.000Z") == date(2026, 7, 15)
    # 20:00 UTC + 5:30 = 01:30 next day IST
    assert _ist_date("2026-07-15T20:00:00.000Z") == date(2026, 7, 16)


def test_extract_events_defensive():
    assert len(extract_events(_page(BENGALURU))) == 5
    assert extract_events("<html>no next data</html>") == []
    assert extract_events(_page([])) == []


# --------------------------- normalization ---------------------------


def test_normalize_offline_meetup():
    event = normalize_event(BENGALURU[0], "Bangalore")
    assert event is not None
    assert event.category == EventCategory.MEETUP
    assert event.city == "Bangalore"
    assert event.is_online is False
    assert event.start_date == date(2026, 7, 15)
    assert str(event.url) == "https://lu.ma/cqo8g0a2"
    assert event.provider == "luma"


def test_normalize_online_has_no_city():
    event = normalize_event(BENGALURU[2], "Bangalore")
    assert event is not None
    assert event.is_online is True
    assert event.city is None
    assert event.location == "Online"


def test_category_from_title_workshop():
    assert normalize_event(BENGALURU[1], "Bangalore").category == EventCategory.WORKSHOP


# --------------------------- search / dedup ---------------------------


def test_search_upcoming_deduped_across_cities():
    events = run(_provider([]).search(SearchQuery()))
    titles = [e.title for e in events]
    # Past filtered; "Cross City" deduped to one despite being on both pages.
    assert set(titles) == {
        "Gemma x Hugging Face Bengaluru Meetup",
        "AI Workshop",
        "Online DevOps Talk",
        "Cross City",
        "Mumbai Startup Mixer",
    }
    assert titles.count("Cross City") == 1


# --------------------------- cache & failure ---------------------------


def test_data_is_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Mumbai")))
    assert len(calls) == after_first


def test_fetch_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
