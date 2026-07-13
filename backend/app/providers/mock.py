"""In-memory MockProvider.

Purpose: prove the full normalize + filter pipeline independent of any external
source. Seed events are generated relative to *today* so the mock never goes stale.
When real providers arrive (M6), the filtering here is a reference for any provider
that must post-filter results locally.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

PROVIDER_NAME = "mock"


def _build_seed_events() -> list[Event]:
    """Realistic India tech events, dated relative to today (always upcoming)."""
    today = date.today()

    def upcoming(days: int) -> date:
        return today + timedelta(days=days)

    return [
        Event(
            title="Applied AI Workshop: Building with LLMs",
            description="Hands-on workshop on building applications with large language models.",
            url="https://example.com/events/applied-ai-workshop",
            city="Bangalore",
            location="Koramangala, Bangalore",
            start_date=upcoming(3),
            category=EventCategory.WORKSHOP,
            is_free=False,
            price="₹999",
            provider=PROVIDER_NAME,
        ),
        Event(
            title="Startup Networking Night",
            description="Meet founders, operators and investors from the Pune startup ecosystem.",
            url="https://example.com/events/startup-networking-pune",
            city="Pune",
            location="Baner, Pune",
            start_date=upcoming(6),
            category=EventCategory.STARTUP,
            is_free=True,
            price="Free",
            provider=PROVIDER_NAME,
        ),
        Event(
            title="National Machine Learning Hackathon",
            description="48-hour hackathon focused on machine learning solutions.",
            url="https://example.com/events/ml-hackathon",
            city="Hyderabad",
            location="HITEC City, Hyderabad",
            start_date=upcoming(20),
            end_date=upcoming(22),
            category=EventCategory.HACKATHON,
            is_free=True,
            price="Free",
            provider=PROVIDER_NAME,
        ),
        Event(
            title="Free Webinar: Getting Started with Machine Learning",
            description="Introductory online session covering core ML concepts.",
            url="https://example.com/events/ml-webinar",
            location="Online",
            is_online=True,
            start_date=upcoming(2),
            category=EventCategory.WEBINAR,
            is_free=True,
            price="Free",
            provider=PROVIDER_NAME,
        ),
        Event(
            title="India DevConf 2026",
            description="Two-day developer conference covering cloud, AI and platform engineering.",
            url="https://example.com/events/india-devconf",
            city="Bangalore",
            location="Whitefield, Bangalore",
            start_date=upcoming(35),
            end_date=upcoming(36),
            category=EventCategory.CONFERENCE,
            is_free=False,
            price="From ₹2,499",
            provider=PROVIDER_NAME,
        ),
        Event(
            title="Generative AI Meetup",
            description="Community meetup on generative AI, agents and RAG in production.",
            url="https://example.com/events/genai-meetup",
            city="Mumbai",
            location="Powai, Mumbai",
            start_date=upcoming(9),
            category=EventCategory.AI,
            is_free=True,
            price="Free",
            provider=PROVIDER_NAME,
        ),
    ]


class MockProvider(EventProvider):
    """Returns seed events filtered by the query. No network, no external state."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._events = _build_seed_events()

    async def search(self, query: SearchQuery) -> list[Event]:
        return [event for event in self._events if matches(event, query)]
