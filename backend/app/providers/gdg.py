"""Google Developer Groups (GDG) provider — India developer community events.

Source: the Bevy platform JSON API (no key, no auth):
    GET https://gdg.community.dev/api/event/

All fetch/paginate/normalize/cache logic is shared in `bevy.py`. GDG events are
community developer meetups (DevFests, study jams, meetups), so category=MEETUP.
"""

from __future__ import annotations

from app.models.event import Event, EventCategory
from app.providers.bevy import BevyEventProvider, normalize_bevy_event

PROVIDER_NAME = "gdg"
GDG_URL = "https://gdg.community.dev/api/event/"


def normalize_event(entry: dict) -> Event | None:
    return normalize_bevy_event(entry, provider_name=PROVIDER_NAME, category=EventCategory.MEETUP)


class GDGProvider(BevyEventProvider):
    name = PROVIDER_NAME
    base_url = GDG_URL
    cache_key = "gdg:india-upcoming"
    category = EventCategory.MEETUP
