"""Search Query Generator (Phase 6F / D3) — deterministic, template-based. NO LLM.

Expands a `QuerySpec` (cities × technologies × platforms × event-types × universities × companies)
into an ordered, de-duplicated list of search-engine queries. Every query is a pure string
template — no model, no randomness — so the same spec always yields the same queries in the same
order (essential for reproducible discovery and cache-friendly frontier tracking).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Curated, India-focused defaults. Kept modest so the full cross-product stays tractable; callers
# pass a narrower or wider QuerySpec as needed.
DEFAULT_CITIES = ("Bangalore", "Delhi", "Mumbai", "Hyderabad", "Pune")
DEFAULT_TECHNOLOGIES = ("AI", "Python", "Kubernetes", "React", "DevOps")
DEFAULT_PLATFORMS = ("meetup.com", "eventbrite.com")  # generic event platforms → site: search
DEFAULT_COMMUNITY_SITES = ("gdg.community.dev", "fossunited.org", "hasgeek.com", "commudle.com")
DEFAULT_EVENT_TYPES = ("meetup", "conference", "hackathon", "workshop")
DEFAULT_UNIVERSITIES = ("IIT", "NIT", "BITS Pilani")
DEFAULT_COMPANIES = ("Google", "Microsoft", "Razorpay")


@dataclass(frozen=True)
class QuerySpec:
    cities: tuple[str, ...] = DEFAULT_CITIES
    technologies: tuple[str, ...] = DEFAULT_TECHNOLOGIES
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    community_sites: tuple[str, ...] = DEFAULT_COMMUNITY_SITES
    event_types: tuple[str, ...] = DEFAULT_EVENT_TYPES
    universities: tuple[str, ...] = DEFAULT_UNIVERSITIES
    companies: tuple[str, ...] = DEFAULT_COMPANIES
    organizations: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_SPEC = QuerySpec()


def _dedupe_stable(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = " ".join(it.split())  # collapse whitespace for identity
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def build_queries(spec: QuerySpec = DEFAULT_SPEC, *, limit: int | None = None) -> list[str]:
    """Expand `spec` into an ordered, de-duplicated list of deterministic search queries."""
    out: list[str] = []

    # 1. Platform site-search: find groups/events by city × technology (Meetup, Eventbrite).
    for platform in spec.platforms:
        for city in spec.cities:
            for tech in spec.technologies:
                out.append(f"site:{platform} {city} {tech}")

    # 2. Community-platform discovery: enumerate a known community host (GDG/FOSS/Hasgeek/…).
    for site in spec.community_sites:
        out.append(f"site:{site} India")
        for event_type in spec.event_types:
            out.append(f"site:{site} {event_type}")

    # 3. Topical open-web queries (no site:): surface conference/organizer websites directly.
    for tech in spec.technologies:
        for event_type in spec.event_types:
            for city in spec.cities:
                out.append(f"{tech} {event_type} {city} India")

    # 4. University tech clubs / student chapters.
    for university in spec.universities:
        for tech in spec.technologies:
            out.append(f"{university} {tech} club events")

    # 5. Company developer events / tech talks.
    for company in spec.companies:
        out.append(f"{company} tech talks India")
        for city in spec.cities:
            out.append(f"{company} developer events {city}")

    # 6. Explicit organizations (optional, caller-supplied).
    for org in spec.organizations:
        out.append(f"{org} events India")

    queries = _dedupe_stable(out)
    return queries[:limit] if limit is not None else queries
