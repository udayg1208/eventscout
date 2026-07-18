"""Curated ICS source catalog — the config-driven, hierarchical provider list.

Each entry becomes its own `ICSProvider` + plugin (own id, city, category, health,
refresh). This is the file that GROWS: discovery is not automatable at ₹0, so scale comes
from curating source URLs here. Only feeds confirmed reachable (HTTP 200 + VEVENT) are
listed, so provider health stays clean even when a community has no upcoming events yet.

Add a source = add a line. No code change, no architecture change — the registry loops
over this list. Families beyond Meetup (community Google Calendars, Luma calendars,
university clubs) drop in the same way (any public .ics URL).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.event import EventCategory


@dataclass(frozen=True)
class IcsSource:
    id: str
    name: str
    ics_url: str
    city: str | None
    category: EventCategory
    expected_volume: int = 2


def _meetup(slug: str, city: str, *, category: EventCategory = EventCategory.MEETUP) -> IcsSource:
    """A Meetup group's public iCalendar feed (calendar-subscription feature)."""
    return IcsSource(
        id=f"meetup-{slug.casefold()}",
        name=f"Meetup: {slug}",
        ics_url=f"https://www.meetup.com/{slug}/events/ical/",
        city=city,
        category=category,
    )


# Curated, probe-confirmed reachable India tech Meetup groups (grow this list over time).
ICS_SOURCES: list[IcsSource] = [
    _meetup("bangpypers", "Bangalore"),
    _meetup("pydelhi", "Delhi"),
    _meetup("chennaipy", "Chennai"),
    _meetup("awsugblr", "Bangalore"),
    _meetup("flutter-bangalore", "Bangalore"),
    _meetup("Bangalore-Golang-Meetup", "Bangalore"),
    _meetup("DevOps-Bangalore", "Bangalore"),
    _meetup("Bangalore-Kubernetes-Meetup", "Bangalore"),
    _meetup("aws-user-group-hyderabad", "Hyderabad"),
    # --- Phase 3G P0.2 batch (probe-confirmed reachable, research_sources2.py) ---
    _meetup("ReactJS-Bangalore", "Bangalore"),
    _meetup("docker-bangalore", "Bangalore"),
    _meetup("PyData-Mumbai", "Mumbai"),
    _meetup("javascript-meetup-bangalore", "Bangalore"),
    _meetup("PythonPune", "Pune"),
    _meetup("hyderabad-python-meetup-group", "Hyderabad"),
    _meetup("Deep-Learning-Bangalore", "Bangalore"),
    _meetup("Blrdroid", "Bangalore"),
    _meetup("wordpress-bangalore", "Bangalore"),
    _meetup("women-who-code-bangalore", "Bangalore"),
    # --- Phase 11A batch (probe-confirmed reachable + upcoming; probe_ics.py) ---
    _meetup("AWS-User-Group-Pune", "Pune"),
    _meetup("PyData-Bangalore", "Bangalore"),
    _meetup("PyData-Chennai", "Chennai"),
]
