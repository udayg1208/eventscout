"""Verification planner + strategies (Phase 10E) — different seed kinds, different proof.

Each seed kind gets an isolated strategy: which URLs to try, what search query to run, the
verification path (steps), and — given the collected evidence — how well that evidence fits the
kind. A chapter is proven by an organizer homepage in the right city; a series by an event page; a
sponsor program by a tech-matching program page; a university unit by the campus site.
Deterministic; produces a plan, never fetches (the engine does that).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.ecosystem import SeedKind
from app.validation.models import Evidence, VerificationPlan

_SIGNAL = {
    "reachable": lambda e: e.reachable,
    "organizer": lambda e: bool(e.organizer_name),
    "events": lambda e: e.events_found > 0,
    "tech": lambda e: bool(e.technologies),
    "city": lambda e: bool(e.city),
    "feeds": lambda e: bool(e.feeds),
    "calendars": lambda e: bool(e.calendars),
    "jsonld": lambda e: e.has_jsonld,
    "registration": lambda e: bool(e.registration_url),
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class VerificationStrategy:
    kind: SeedKind
    steps: tuple[str, ...] = ("search", "homepage", "universal_extraction", "organizer_extraction")
    hosts: tuple[str, ...] = ()
    expected: tuple[str, ...] = ("organizer",)  # content signals (reachability handled separately)

    def search_query(self, seed) -> str:
        return seed.search_hint or seed.target

    def candidate_urls(self, seed) -> list[str]:
        slug = slugify(seed.target)
        return [h.format(slug=slug) for h in self.hosts]

    def evaluate(self, seed, evidence: Evidence) -> tuple[float, list[str]]:
        present = [s for s in self.expected if _SIGNAL[s](evidence)]
        score = len(present) / len(self.expected) if self.expected else 0.0
        reasons = [f"{s}✓" for s in present] + [f"{s}✗" for s in self.expected if s not in present]
        return score, reasons


class ChapterStrategy(VerificationStrategy):
    kind = SeedKind.CHAPTER_SIBLING
    hosts = ("https://gdg.community.dev/{slug}/", "https://www.meetup.com/{slug}/")
    expected = ("organizer", "city")


class SeriesStrategy(VerificationStrategy):
    kind = SeedKind.SERIES_INSTANCE
    steps = ("search", "event_page", "universal_extraction")
    hosts = ("https://{slug}.dev/", "https://www.meetup.com/{slug}/")
    expected = ("events", "city")


class SponsorStrategy(VerificationStrategy):
    kind = SeedKind.SPONSOR_PROGRAM
    steps = ("search", "program_page", "expansion", "universal_extraction")
    hosts = ("https://developers.google.com/community/{slug}", "https://{slug}.dev/")
    expected = ("tech", "organizer")


class UniversityStrategy(VerificationStrategy):
    kind = SeedKind.UNIVERSITY_UNIT
    steps = ("university_website", "departments", "student_clubs", "verification")
    hosts = ("https://{slug}.ac.in/", "https://{slug}.edu/")
    expected = ("organizer",)


class VenueStrategy(VerificationStrategy):
    kind = SeedKind.VENUE_UNIT
    steps = ("venue_page", "universal_extraction", "verification")
    hosts = ("https://{slug}.ac.in/", "https://{slug}.com/")
    expected = ("events",)


class CommunityStrategy(VerificationStrategy):
    """similar-organizer seeds — a community/organizer to confirm."""

    kind = SeedKind.SIMILAR_ORGANIZER
    hosts = ("https://{slug}.dev/", "https://www.meetup.com/{slug}/")
    expected = ("organizer",)


class ConnectedResourceStrategy(VerificationStrategy):
    """connected-resource seeds — the target is often already a host/URL; verify it directly."""

    kind = SeedKind.CONNECTED_RESOURCE
    steps = ("resource_page", "universal_extraction")
    expected = ("organizer",)

    def candidate_urls(self, seed) -> list[str]:
        target = seed.target.strip()
        if "://" in target:
            return [target]
        # a bare host (has a dot, no spaces) → use it directly; otherwise slugify to a guess
        if "." in target and " " not in target and urlsplit(f"https://{target}").netloc:
            return [f"https://{target}"]
        return [f"https://{slugify(target)}.dev/"]


_STRATEGIES: dict[SeedKind, VerificationStrategy] = {
    s.kind: s
    for s in (
        ChapterStrategy(),
        SeriesStrategy(),
        SponsorStrategy(),
        UniversityStrategy(),
        VenueStrategy(),
        CommunityStrategy(),
        ConnectedResourceStrategy(),
    )
}


class VerificationPlanner:
    def strategy_for(self, seed) -> VerificationStrategy:
        return _STRATEGIES.get(seed.kind, VerificationStrategy())

    def plan(self, seed) -> VerificationPlan:
        strat = self.strategy_for(seed)
        return VerificationPlan(
            strategy=seed.kind.value if hasattr(seed.kind, "value") else str(seed.kind),
            search_query=strat.search_query(seed),
            candidate_urls=strat.candidate_urls(seed),
            steps=list(strat.steps),
        )
