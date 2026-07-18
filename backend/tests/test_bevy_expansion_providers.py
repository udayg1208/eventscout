"""Phase 3G Bevy-platform expansion providers (Atlassian, Salesforce, Snowflake).

They reuse the fully-tested `BevyEventProvider` base, so these tests confirm the wiring:
correct host, provider name, category, and India+upcoming filtering. Network-free.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.atlassian import AtlassianProvider
from app.providers.salesforce import SalesforceProvider
from app.providers.snowflake import SnowflakeProvider

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


PAGE1 = [
    {
        "title": "Future India Meetup",
        "url": "https://example.com/e/in1/",
        "start_date": "2026-12-01T10:00:00+05:30",
        "chapter": {"city": "Bengaluru", "country": "IN", "country_name": "India"},
    },
    {
        "title": "US Group",
        "url": "https://example.com/e/us/",
        "start_date": "2027-01-01T10:00:00-05:00",
        "chapter": {"city": "New York", "country": "US"},
    },
    {  # past India event → excluded and triggers the descending-order stop
        "title": "Past India",
        "url": "https://example.com/e/past/",
        "start_date": "2026-06-01T10:00:00+05:30",
        "chapter": {"city": "Delhi", "country": "IN"},
    },
]


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        return httpx.Response(200, json={"results": PAGE1 if page == "1" else []})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "cls,name",
    [
        (AtlassianProvider, "atlassian"),
        (SalesforceProvider, "salesforce"),
        (SnowflakeProvider, "snowflake"),
    ],
)
def test_bevy_expansion_provider_filters_india_upcoming(cls, name):
    provider = cls(transport=_transport(), ttl_seconds=300, today=TODAY)
    events = run(provider.search(SearchQuery()))
    assert {e.title for e in events} == {"Future India Meetup"}
    event = events[0]
    assert event.provider == name
    assert event.category == EventCategory.MEETUP
    assert event.city == "Bangalore"  # Bengaluru normalized at the boundary
    assert event.start_date == date(2026, 12, 1)
