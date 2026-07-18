"""Source Ranking (Phase 6F / D3) — deterministic scoring of a search-discovered source.

Produces a `DiscoveryScore` from the search metadata alone (title + snippet + url + domain) — we
have NOT crawled the page yet, so this ranks *which discovered pages look most worth inspecting*,
using explainable weighted signals. It is a **search-relevance rank**, not the deferred Confidence
Engine's onboarding verdict (that still requires a real crawl via D1/D2).

Reuses the catalog's own tech taxonomy (5A) and `city.detect_city` so "technology" and "India"
mean the same here as everywhere else. No LLM, no network — pure functions over strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.city import detect_city
from app.discovery.search.parser import ParsedResult
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

# Single source of truth for the weighting (mirrors app/providers/ranking.py's WEIGHTS style).
WEIGHTS = {
    "technology": 0.30,
    "india": 0.20,
    "city": 0.10,
    "meetup": 0.15,
    "conference": 0.10,
    "rss": 0.05,
    "jsonld": 0.05,
    "known_community": 0.15,
}

_MEETUP_TERMS = re.compile(
    r"\b(meetup|user ?group|developer group|community|chapter|gdg|gdsc|society|\bclub\b)\b",
    re.IGNORECASE,
)
_CONFERENCE_TERMS = re.compile(
    r"\b(conference|conf|summit|devfest|symposium|convention|expo|con\d{2,4}|pycon|"
    r"rootconf|unconference)\b",
    re.IGNORECASE,
)
_RSS_HINT = re.compile(r"/(feed|rss|atom)\b|\.(xml|rss)\b", re.IGNORECASE)
_INDIA = re.compile(r"\bindia\b|\bindian\b", re.IGNORECASE)

# Domains/hosts of platforms that emit meetup/community structure or schema.org Event JSON-LD —
# a strong hint the page will be D1/D2-ingestible once crawled.
_MEETUP_DOMAINS = {"meetup.com", "community.dev", "commudle.com", "townscript.com"}
_JSONLD_DOMAINS = {
    "hasgeek.com",
    "eventbrite.com",
    "confengine.com",
    "sessionize.com",
    "meetup.com",
}

# Curated known-community names (matched in text or domain).
_KNOWN_COMMUNITIES = (
    "gdg",
    "google developer",
    "fossunited",
    "foss united",
    "hasgeek",
    "cncf",
    "pydata",
    "pydelhi",
    "bangpypers",
    "ieee",
    "devfolio",
    "reactjs",
    "kubernetes community",
    "pycon",
    "djangocon",
    "rootconf",
    "the fifth elephant",
)

# Off-topic penalties — entertainment / tourism / commerce, which superficially look "event-y".
_PENALTY_TERMS = re.compile(
    r"\b(movie|movies|cinema|film|box office|concert|gig|comedy|stand-?up|nightlife|"
    r"tourism|travel|holiday|vacation|hotel|resort|shopping|sale|discount|coupon|offer|"
    r"fashion|recipe|astrology|matrimony|real estate)\b",
    re.IGNORECASE,
)
_PENALTY_DOMAINS = {
    "bookmyshow.com",
    "insider.in",
    "ticketmaster.com",
    "paytm.com",
    "makemytrip.com",
    "goibibo.com",
    "amazon.in",
    "flipkart.com",
}


@dataclass(frozen=True)
class DiscoveryScore:
    """Explainable, deterministic ranking of a discovered source. `total` ∈ [0, 1]."""

    total: float
    technology: float
    india: float
    has_city: bool
    is_meetup: bool
    is_conference: bool
    rss_hint: bool
    jsonld_hint: bool
    known_community: bool
    penalty: float
    reasons: tuple[str, ...]


def _technology_score(text: str) -> tuple[float, int]:
    names = {name for name, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(text)}
    return min(1.0, len(names) / 3.0), len(names)


def score_source(parsed: ParsedResult) -> DiscoveryScore:
    text = f"{parsed.title} {parsed.snippet}".lower()
    domain = parsed.domain.lower()
    reasons: list[str] = []

    tech, tech_n = _technology_score(text)
    if tech_n:
        reasons.append(f"tech:{tech_n}")

    india = 0.0
    if domain.endswith(".in"):
        india = max(india, 0.7)
        reasons.append("domain.in")
    if _INDIA.search(text):
        india = max(india, 1.0)
        reasons.append("india")
    city = detect_city(parsed.title, parsed.snippet)
    if city:
        india = max(india, 0.8)
        reasons.append(f"city:{city}")

    is_meetup = bool(_MEETUP_TERMS.search(text)) or domain in _MEETUP_DOMAINS
    is_conference = bool(_CONFERENCE_TERMS.search(text))
    rss_hint = bool(_RSS_HINT.search(parsed.url))
    jsonld_hint = domain in _JSONLD_DOMAINS
    known = any(k in text or k in domain for k in _KNOWN_COMMUNITIES)
    if is_meetup:
        reasons.append("meetup")
    if is_conference:
        reasons.append("conference")
    if known:
        reasons.append("known-community")

    penalty = 0.0
    if _PENALTY_TERMS.search(text):
        penalty += 0.4
        reasons.append("penalty:offtopic")
    if domain in _PENALTY_DOMAINS:
        penalty += 0.6
        reasons.append("penalty:domain")
    penalty = min(1.0, penalty)

    raw = (
        WEIGHTS["technology"] * tech
        + WEIGHTS["india"] * india
        + WEIGHTS["city"] * float(city is not None)
        + WEIGHTS["meetup"] * float(is_meetup)
        + WEIGHTS["conference"] * float(is_conference)
        + WEIGHTS["rss"] * float(rss_hint)
        + WEIGHTS["jsonld"] * float(jsonld_hint)
        + WEIGHTS["known_community"] * float(known)
    )
    total = max(0.0, min(1.0, raw - penalty))

    return DiscoveryScore(
        total=round(total, 4),
        technology=round(tech, 4),
        india=round(india, 4),
        has_city=city is not None,
        is_meetup=is_meetup,
        is_conference=is_conference,
        rss_hint=rss_hint,
        jsonld_hint=jsonld_hint,
        known_community=known,
        penalty=round(penalty, 4),
        reasons=tuple(reasons),
    )
