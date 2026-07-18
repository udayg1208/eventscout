"""CNCF provider — India cloud-native community events (Kubernetes Community Days,
CNCF community-group meetups, ...).

Source: the Bevy platform JSON API (no key, no auth). Note `community.cncf.io`
301-redirects to the resolved host below.
    GET https://community2.cncf.io/api/event/

Shares all logic with `bevy.py`. CNCF community events are developer community
events, so category=MEETUP (there is no per-event type field to distinguish KCDs).
"""

from __future__ import annotations

from app.models.event import Event, EventCategory
from app.providers.bevy import BevyEventProvider, normalize_bevy_event

PROVIDER_NAME = "cncf"
CNCF_URL = "https://community2.cncf.io/api/event/"


def normalize_event(entry: dict) -> Event | None:
    return normalize_bevy_event(entry, provider_name=PROVIDER_NAME, category=EventCategory.MEETUP)


class CNCFProvider(BevyEventProvider):
    name = PROVIDER_NAME
    base_url = CNCF_URL
    cache_key = "cncf:india-upcoming"
    category = EventCategory.MEETUP
