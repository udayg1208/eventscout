"""Atlassian Community Events (ACE) provider — India Atlassian user-group events.

Source: the Bevy platform JSON API (no key, no auth):
    GET https://ace.atlassian.com/api/event/

ACE runs local user groups around Atlassian's developer/IT tooling (Jira, Confluence,
Bitbucket, Forge). All fetch/paginate/normalize/cache logic is shared in `bevy.py`;
these are professional community meetups, so category=MEETUP.
"""

from __future__ import annotations

from app.models.event import Event, EventCategory
from app.providers.bevy import BevyEventProvider, normalize_bevy_event

PROVIDER_NAME = "atlassian"
ATLASSIAN_URL = "https://ace.atlassian.com/api/event/"


def normalize_event(entry: dict) -> Event | None:
    return normalize_bevy_event(entry, provider_name=PROVIDER_NAME, category=EventCategory.MEETUP)


class AtlassianProvider(BevyEventProvider):
    name = PROVIDER_NAME
    base_url = ATLASSIAN_URL
    cache_key = "atlassian:india-upcoming"
    category = EventCategory.MEETUP
