"""Entity & graph domain models — the Knowledge Graph foundation.

Entities are **canonical, reusable** nodes (one "Google Developer Groups", not a string
on every event); events reference them through typed edges. Each entity *accumulates*
knowledge (event references + aggregates) as the graph is built — it never duplicates
event data (it holds event *keys*, not event bodies).

Storage-independent: these are plain dataclasses. The graph lives behind an abstraction
(`graph.py`) so it can be in-memory today and persisted (SQLite/Postgres) later — no graph
database required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class EntityType(StrEnum):
    ORGANIZATION = "organization"
    COMPANY = "company"
    COMMUNITY = "community"
    SPEAKER = "speaker"
    VENUE = "venue"
    CITY = "city"
    EVENT_SERIES = "event_series"
    EVENT = "event"  # a lightweight node referencing a catalog event by key


class EdgeType(StrEnum):
    ORGANIZED_BY = "organized_by"  # Event   -> Organization
    HOSTED_BY = "hosted_by"  # Event   -> Community
    PART_OF_SERIES = "part_of_series"  # Event   -> EventSeries
    IN_CITY = "in_city"  # Event   -> City
    AT_VENUE = "at_venue"  # Event   -> Venue
    SPEAKS_AT = "speaks_at"  # Speaker -> Event
    HOSTS_SERIES = "hosts_series"  # Organization -> EventSeries (derived)
    ACTIVE_IN = "active_in"  # Community -> City (a chapter)


@dataclass
class Entity:
    """A canonical node that accumulates knowledge across the events it appears in."""

    id: str  # canonical, namespaced, e.g. "community:google-developer-groups"
    type: EntityType
    name: str  # display name
    aliases: set[str] = field(default_factory=set)

    # --- accumulated profile (references + aggregates, never event bodies) ---
    event_keys: set[str] = field(default_factory=set)
    cities: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    first_seen: date | None = None
    last_seen: date | None = None

    @property
    def event_count(self) -> int:
        return len(self.event_keys)

    def observe(
        self, *, event_key: str, city: str | None, category: str | None, start_date: date | None
    ) -> None:
        """Fold one event's facts into this entity's accumulated profile."""
        self.event_keys.add(event_key)
        if city:
            self.cities.add(city)
        if category:
            self.categories.add(category)
        if start_date:
            self.first_seen = (
                start_date if self.first_seen is None else min(self.first_seen, start_date)
            )
            self.last_seen = (
                start_date if self.last_seen is None else max(self.last_seen, start_date)
            )


@dataclass(frozen=True)
class Edge:
    """A directed, typed relationship between two entities."""

    source: str  # entity id
    type: EdgeType
    target: str  # entity id
