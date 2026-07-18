"""Production discovery seed list (Phase 10A) — versioned, curated real entry points.

These are the public homepages / event pages the real pipeline starts from: the crawler expands
their links, the social/rendered engines extract from their pages, and the search engine augments
them. Curated across the categories the platform cares about (universities, developer communities,
conferences, hackathons, OSS foundations, meetup communities, technology companies, public
calendars), India-focused with global anchors. Data only — no logic, no network. Bump
`SEED_LIST_VERSION` when the list changes so a run records exactly which seeds it started from.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SEED_LIST_VERSION = "2026.07.1"


class SeedCategory(StrEnum):
    UNIVERSITY = "university"
    DEV_COMMUNITY = "dev_community"
    CONFERENCE = "conference"
    HACKATHON = "hackathon"
    OSS_FOUNDATION = "oss_foundation"
    MEETUP_COMMUNITY = "meetup_community"
    TECH_COMPANY = "tech_company"
    PUBLIC_CALENDAR = "public_calendar"


@dataclass(frozen=True)
class Seed:
    url: str
    category: SeedCategory
    name: str
    region: str = "India"  # "India" or "Global"

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "category": self.category.value,
            "name": self.name,
            "region": self.region,
        }


C = SeedCategory
# Curated public entry points. Kept to well-known event-bearing sites; the crawler honours each
# site's robots.txt at fetch time, so listing a domain here is a starting hint, not an override.
PRODUCTION_SEEDS: list[Seed] = [
    # universities
    Seed("https://www.iitb.ac.in/en/events", C.UNIVERSITY, "IIT Bombay"),
    Seed("https://www.iitm.ac.in/happenings/events", C.UNIVERSITY, "IIT Madras"),
    Seed("https://www.iith.ac.in/events/", C.UNIVERSITY, "IIT Hyderabad"),
    Seed("https://www.bits-pilani.ac.in/events/", C.UNIVERSITY, "BITS Pilani"),
    # developer communities
    Seed("https://gdg.community.dev/", C.DEV_COMMUNITY, "Google Developer Groups"),
    Seed("https://fossunited.org/", C.DEV_COMMUNITY, "FOSS United"),
    Seed("https://hasgeek.com/", C.DEV_COMMUNITY, "Hasgeek"),
    Seed("https://commudle.com/", C.DEV_COMMUNITY, "Commudle"),
    # conferences
    Seed("https://confs.tech/", C.CONFERENCE, "Confs.tech", region="Global"),
    Seed("https://in.pycon.org/", C.CONFERENCE, "PyCon India"),
    Seed("https://rootconf.in/", C.CONFERENCE, "Rootconf"),
    # hackathons
    Seed("https://devfolio.co/hackathons", C.HACKATHON, "Devfolio"),
    Seed("https://mlh.io/seasons", C.HACKATHON, "Major League Hacking", region="Global"),
    Seed("https://devpost.com/hackathons", C.HACKATHON, "Devpost", region="Global"),
    # OSS foundations
    Seed(
        "https://www.python.org/events/",
        C.OSS_FOUNDATION,
        "Python Software Foundation",
        region="Global",
    ),
    Seed("https://www.cncf.io/events/", C.OSS_FOUNDATION, "CNCF", region="Global"),
    Seed(
        "https://events.linuxfoundation.org/", C.OSS_FOUNDATION, "Linux Foundation", region="Global"
    ),
    Seed(
        "https://www.apache.org/events/current-event.html",
        C.OSS_FOUNDATION,
        "Apache Software Foundation",
        region="Global",
    ),
    # meetup communities
    Seed("https://www.meetup.com/topics/tech/in/", C.MEETUP_COMMUNITY, "Meetup — Tech India"),
    Seed(
        "https://www.meetup.com/topics/python/",
        C.MEETUP_COMMUNITY,
        "Meetup — Python",
        region="Global",
    ),
    # technology companies (public developer-event pages)
    Seed(
        "https://developers.google.com/events", C.TECH_COMPANY, "Google Developers", region="Global"
    ),
    Seed(
        "https://developer.microsoft.com/en-us/reactor/",
        C.TECH_COMPANY,
        "Microsoft Reactor",
        region="Global",
    ),
    Seed("https://aws.amazon.com/events/", C.TECH_COMPANY, "AWS Events", region="Global"),
    # public calendars / feeds
    Seed(
        "https://www.python.org/events/python-events/",
        C.PUBLIC_CALENDAR,
        "Python Events Calendar",
        region="Global",
    ),
    Seed(
        "https://fosdem.org/2026/schedule/", C.PUBLIC_CALENDAR, "FOSDEM Schedule", region="Global"
    ),
]


@dataclass(frozen=True)
class ProductionSeedList:
    version: str = SEED_LIST_VERSION
    seeds: tuple[Seed, ...] = tuple(PRODUCTION_SEEDS)

    def urls(self) -> list[str]:
        return [s.url for s in self.seeds]

    def by_category(self, category: SeedCategory) -> list[Seed]:
        return [s for s in self.seeds if s.category is category]

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.seeds:
            counts[s.category.value] = counts.get(s.category.value, 0) + 1
        return counts

    def sample(self, n: int) -> list[Seed]:
        """First `n` seeds spread across categories (deterministic — no randomness)."""
        out: list[Seed] = []
        seen: set[str] = set()
        for cat in SeedCategory:
            for s in self.by_category(cat):
                if s.url not in seen:
                    out.append(s)
                    seen.add(s.url)
                    break
            if len(out) >= n:
                break
        for s in self.seeds:  # top up if categories didn't fill n
            if len(out) >= n:
                break
            if s.url not in seen:
                out.append(s)
                seen.add(s.url)
        return out[:n]

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "count": len(self.seeds),
            "categories": self.categories(),
            "seeds": [s.as_dict() for s in self.seeds],
        }


DEFAULT_SEEDS = ProductionSeedList()
