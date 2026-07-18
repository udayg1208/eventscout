"""Snowflake User Groups provider — India Snowflake data-community events.

Source: the Bevy platform JSON API (no key, no auth):
    GET https://usergroups.snowflake.com/api/event/

Snowflake User Groups are local data-engineering / analytics community meetups. Shares
all logic with `bevy.py`; category=MEETUP.
"""

from __future__ import annotations

from app.models.event import Event, EventCategory
from app.providers.bevy import BevyEventProvider, normalize_bevy_event

PROVIDER_NAME = "snowflake"
SNOWFLAKE_URL = "https://usergroups.snowflake.com/api/event/"


def normalize_event(entry: dict) -> Event | None:
    return normalize_bevy_event(entry, provider_name=PROVIDER_NAME, category=EventCategory.MEETUP)


class SnowflakeProvider(BevyEventProvider):
    name = PROVIDER_NAME
    base_url = SNOWFLAKE_URL
    cache_key = "snowflake:india-upcoming"
    category = EventCategory.MEETUP
