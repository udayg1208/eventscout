"""Salesforce Trailblazer Community Groups provider — India Salesforce community events.

Source: the Bevy platform JSON API (no key, no auth):
    GET https://trailblazercommunitygroups.com/api/event/

Trailblazer Community Groups are local developer/admin user groups around the Salesforce
platform (Apex, Lightning, Agentforce, admins, architects). Shares all logic with
`bevy.py`; community meetups, so category=MEETUP.
"""

from __future__ import annotations

from app.models.event import Event, EventCategory
from app.providers.bevy import BevyEventProvider, normalize_bevy_event

PROVIDER_NAME = "salesforce"
SALESFORCE_URL = "https://trailblazercommunitygroups.com/api/event/"


def normalize_event(entry: dict) -> Event | None:
    return normalize_bevy_event(entry, provider_name=PROVIDER_NAME, category=EventCategory.MEETUP)


class SalesforceProvider(BevyEventProvider):
    name = PROVIDER_NAME
    base_url = SALESFORCE_URL
    cache_key = "salesforce:india-upcoming"
    category = EventCategory.MEETUP
