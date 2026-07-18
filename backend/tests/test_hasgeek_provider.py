"""HasgeekProvider: URL extraction, JSON-LD normalization, date filter, cache, failure."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.hasgeek import (
    HasgeekProvider,
    extract_project_paths,
    normalize_event,
    parse_event_ldjson,
)

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


def _ld(name, start, end=None, venue=None, locality=None):
    event: dict = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": name,
        "startDate": start,
    }
    if end:
        event["endDate"] = end
    if venue or locality:
        loc: dict = {"@type": "Place", "name": venue}
        if locality:
            loc["address"] = {"@type": "PostalAddress", "addressLocality": locality}
        event["location"] = loc
    return event


def _page(ld: dict | None) -> str:
    script = f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else ""
    return f"<html><head>{script}</head><body>x</body></html>"


HOME = """<html><body>
<a class="card card--upcoming clickable-card" href="/fifthelephant/2026/">FE</a>
<a class="card card--upcoming clickable-card" href="/rustbangalore/meetup/">Rust</a>
<a class="card card--upcoming clickable-card" href="/rootconf/oldcfp/">Old</a>
<a href="/about/team/">About</a>
</body></html>"""

FE_LD = _ld(
    "The Fifth Elephant 2026 Annual Conference",
    "2026-07-31T09:00:00+05:30",
    "2026-08-01T18:00:00+05:30",
    venue="NIMHANS Convention Centre",
    locality="Bengaluru",
)
RUST_LD = _ld(
    "July 2026 Rustacean Meetup", "2026-07-18T11:00:00+05:30", venue="Juspay", locality="Bengaluru"
)
OLD_LD = _ld("Rootconf CFP", "2026-03-30T09:00:00+05:30", "2026-06-13T18:00:00+05:30")

PAGES = {
    "/fifthelephant/2026/": _page(FE_LD),
    "/rustbangalore/meetup/": _page(RUST_LD),
    "/rootconf/oldcfp/": _page(OLD_LD),  # past -> filtered
    "/about/team/": _page(None),  # no Event -> skipped
}


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if status != 200:
            return httpx.Response(status)
        if path == "/":
            return httpx.Response(200, text=HOME)
        return httpx.Response(200, text=PAGES.get(path, _page(None)))

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> HasgeekProvider:
    return HasgeekProvider(transport=_transport(calls, status), ttl_seconds=300, today=TODAY)


# --------------------------- parsing helpers ---------------------------


def test_extract_project_paths():
    assert extract_project_paths(HOME) == [
        "/fifthelephant/2026/",
        "/rustbangalore/meetup/",
        "/rootconf/oldcfp/",
        "/about/team/",
    ]


def test_parse_event_ldjson():
    assert parse_event_ldjson(_page(FE_LD))["name"].startswith("The Fifth Elephant")
    assert parse_event_ldjson(_page(None)) is None


# --------------------------- normalization ---------------------------


def test_normalize_conference_with_city():
    event = normalize_event(FE_LD, "/fifthelephant/2026/")
    assert event is not None
    assert event.category == EventCategory.CONFERENCE
    assert event.city == "Bangalore"  # Bengaluru normalized
    assert event.location == "NIMHANS Convention Centre"
    assert event.start_date == date(2026, 7, 31)
    assert event.end_date == date(2026, 8, 1)
    assert str(event.url) == "https://hasgeek.com/fifthelephant/2026/"
    assert event.provider == "hasgeek"


def test_category_derived_from_title():
    assert normalize_event(RUST_LD, "/x/y/").category == EventCategory.MEETUP


# --------------------------- search / filtering ---------------------------


def test_search_returns_upcoming_events_only():
    events = run(_provider([]).search(SearchQuery()))
    # Rootconf CFP (past) and /about/team (no Event) are excluded.
    assert {e.title for e in events} == {
        "The Fifth Elephant 2026 Annual Conference",
        "July 2026 Rustacean Meetup",
    }


def test_city_filter():
    events = run(_provider([]).search(SearchQuery(city="Bangalore")))
    assert len(events) == 2  # both venues resolve to Bangalore


# --------------------------- cache & failure ---------------------------


def test_data_is_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Bangalore")))
    assert len(calls) == after_first


def test_home_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
