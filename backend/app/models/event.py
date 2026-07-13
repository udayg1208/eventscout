"""The normalized Event model — the single contract every provider maps into.

Confs.tech, Devfolio, Luma, SerpApi, or any future source must produce this exact
shape, so the frontend never needs provider-specific logic.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl


class EventCategory(StrEnum):
    """Controlled vocabulary of professional/tech event types (project scope).

    A string enum so it serializes as its plain value ("workshop") in JSON and can
    be compared directly against the categories in a SearchQuery.
    """

    WORKSHOP = "workshop"
    MEETUP = "meetup"
    CONFERENCE = "conference"
    HACKATHON = "hackathon"
    STARTUP = "startup"
    AI = "ai"
    WEBINAR = "webinar"


class Event(BaseModel):
    """A single normalized event, immutable once created.

    `frozen=True` signals that an Event is a read-only snapshot of what a source
    returned; it also makes events hashable for future cross-provider dedup.
    """

    model_config = ConfigDict(frozen=True)

    # --- Identity / display ---
    title: str
    description: str | None = None
    url: HttpUrl

    # --- Location ---
    city: str | None = None  # machine filter key ("Bangalore"); None if online
    location: str | None = None  # human display string ("Whitefield, Bangalore")
    is_online: bool = False  # physical unless a source says otherwise

    # --- When ---
    start_date: date  # date, not datetime: date-only sources are common
    end_date: date | None = None  # set only for multi-day events

    # --- Classification ---
    category: EventCategory

    # --- Cost ---
    is_free: bool | None = None  # None = source did not say (do not assume paid)
    price: str | None = None  # display string ("₹499", "From ₹1,999")

    # --- Provenance ---
    provider: str  # which source produced this event
