"""AIExtractor abstraction + a deterministic MockAIExtractor (Phase 6G / D4).

`AIExtractor` is the seam a real LLM (Gemini/OpenAI) plugs into later. `MockAIExtractor` stands in
now: it reads a page's text and produces an `AIExtraction` with **real provenance on every field** —
the exact snippet a value came from, a reason, and a confidence. Its heuristics are deterministic
(same page → same extraction), so tests and the spike need no network.

The one inviolable rule it models: **never fabricate.** When a field has no supporting snippet it is
returned as `UNKNOWN` (value None), not guessed. Values derived from evidence (e.g. country India
from a detected Indian city) are marked `INFERRED`, never `EXTRACTED`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.city import detect_city
from app.discovery.ai.models import (
    AIExtraction,
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
)
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS


@dataclass(frozen=True)
class ExtractionInput:
    """Raw page content handed to an extractor (no fetching happens inside the extractor)."""

    url: str
    text: str  # visible text or raw HTML
    title: str | None = None


class AIExtractor(ABC):
    name: str = "ai"

    @abstractmethod
    def extract(self, page: ExtractionInput) -> AIExtraction:
        """Return a provenance-bearing AIExtraction. Unknown fields MUST be UNKNOWN, not guessed."""


_ORGANIZED_BY = re.compile(
    r"(?:organi[sz]ed|hosted|presented|brought to you)\s+by[:\s]+([A-Z][^.\n<]{2,60})",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s\"'<>)]+")
_RECURRING = re.compile(
    r"\b(every\s+(?:month|week|day|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"monthly|weekly|bi-?weekly|fortnightly|quarterly|annual(?:ly)?|recurring|each\s+month)\b",
    re.IGNORECASE,
)
_INDIA = re.compile(r"\bindia\b|\bindian\b", re.IGNORECASE)
_STATES = (
    "Karnataka",
    "Maharashtra",
    "Delhi",
    "Telangana",
    "Tamil Nadu",
    "Kerala",
    "Gujarat",
    "West Bengal",
    "Rajasthan",
    "Uttar Pradesh",
    "Haryana",
    "Punjab",
)
_AUDIENCES = (
    "developers",
    "engineers",
    "students",
    "founders",
    "entrepreneurs",
    "designers",
    "data scientists",
    "professionals",
    "researchers",
    "beginners",
    "product managers",
)
_EVENT_TYPES = {
    "meetup": r"\bmeetups?\b",
    "conference": r"\bconferences?\b|\bsummit\b|\bconf\b",
    "hackathon": r"\bhackathons?\b",
    "workshop": r"\bworkshops?\b|\bbootcamp\b|hands-?on",
    "webinar": r"\bwebinars?\b|online session",
    "talk": r"\btech talks?\b|\blightning talks?\b",
}
_PLATFORMS = {
    "meetup": r"meetup\.com|\bmeetup\b",
    "eventbrite": r"eventbrite",
    "luma": r"lu\.ma|luma\.com",
    "commudle": r"commudle",
    "hasgeek": r"hasgeek",
    "devfolio": r"devfolio",
    "townscript": r"townscript",
    "konfhub": r"konfhub",
    "gdg-community": r"community\.dev|gdg",
}
_COMMUNITIES = {
    "GDG": r"\bgdg\b|google developer group",
    "FOSS United": r"foss united|fossunited",
    "PyData": r"pydata",
    "CNCF": r"\bcncf\b|cloud native computing",
    "Hasgeek": r"hasgeek|rootconf|the fifth elephant",
    "IEEE": r"\bieee\b",
    "PyDelhi": r"pydelhi",
    "BangPypers": r"bangpypers",
    "Women Who Code": r"women who code",
    "Kubernetes Community": r"kubernetes community|k8s community",
}
_REG_HINT = re.compile(r"register|rsvp|tickets?|devfolio|eventbrite|lu\.ma|konfhub", re.IGNORECASE)
_CAL_HINT = re.compile(r"\.ics(\b|$)|calendar\.google|/calendar|add to calendar", re.IGNORECASE)


class MockAIExtractor(AIExtractor):
    """Deterministic LLM-extractor stand-in: heuristic, provenance-bearing, never guesses."""

    name = "mock-ai"

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock

    def _field(
        self, value: object, snippet: str, reason: str, confidence: float, *, inferred: bool = False
    ) -> ExtractedField:
        return ExtractedField(
            value=value,
            status=FieldStatus.INFERRED if inferred else FieldStatus.EXTRACTED,
            provenance=Provenance(
                source_snippet=snippet[:200],
                reason=reason,
                confidence=round(confidence, 3),
                method=ExtractionMethod.AI,
                timestamp=self._clock(),
            ),
        )

    def extract(self, page: ExtractionInput) -> AIExtraction:
        title = page.title or ""
        body = f"{title}\n{page.text}"
        low = body.lower()
        ex = AIExtraction(url=page.url, method=ExtractionMethod.AI)

        # technologies (reuse the catalog's 5A taxonomy) — the strongest tech-relevance evidence
        techs = sorted({name for name, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(low)})
        if techs:
            ex.technologies = self._field(
                techs, ", ".join(techs), "matched catalog tech taxonomy", min(1.0, len(techs) / 3)
            )

        # event types
        types = [name for name, pat in _EVENT_TYPES.items() if re.search(pat, low)]
        if types:
            ex.event_types = self._field(types, ", ".join(types), "event-type keywords", 0.8)

        # city / state / country
        city = detect_city(title, page.text)
        if city:
            ex.city = self._field(city, city, "matched known city", 0.85)
        for st in _STATES:
            if re.search(rf"\b{re.escape(st)}\b", body, re.IGNORECASE):
                ex.state = self._field(st, st, "matched Indian state name", 0.8)
                break
        india_hit = _INDIA.search(body)
        if india_hit:
            ex.country = self._field("India", india_hit.group(0), "explicit India mention", 0.95)
        elif city or page.url.lower().rstrip("/").endswith(".in"):
            ex.country = self._field(
                "India",
                city or page.url,
                "inferred from Indian city / .in domain",
                0.6,
                inferred=True,
            )

        # organization / organizer (only from an explicit "organized by …" — else UNKNOWN)
        m = _ORGANIZED_BY.search(body)
        if m:
            org = m.group(1).strip().rstrip(".")
            ex.organization = self._field(org, m.group(0), "explicit 'organized by' phrase", 0.85)
            ex.organizer = self._field(org, m.group(0), "explicit 'organized by' phrase", 0.8)

        # community
        for name, pat in _COMMUNITIES.items():
            hit = re.search(pat, body, re.IGNORECASE)
            if hit:
                ex.community = self._field(name, hit.group(0), "known community name", 0.85)
                if not ex.organization.is_known:
                    ex.organization = self._field(
                        name, hit.group(0), "community treated as organizer", 0.6, inferred=True
                    )
                break

        # event platform
        for name, pat in _PLATFORMS.items():
            hit = re.search(pat, low)
            if hit:
                ex.event_platform = self._field(name, hit.group(0), "platform fingerprint", 0.8)
                break

        # audience
        aud = [a for a in _AUDIENCES if a in low]
        if aud:
            ex.audience = self._field(aud, ", ".join(aud), "audience keywords", 0.7)

        # registration / calendar links
        urls = _URL.findall(body)
        reg = [u for u in urls if _REG_HINT.search(u)]
        cal = [u for u in urls if _CAL_HINT.search(u)]
        if reg:
            ex.registration_links = self._field(reg, reg[0], "URLs with registration hints", 0.75)
        if cal:
            ex.calendar_links = self._field(cal, cal[0], "URLs with calendar hints", 0.75)

        # recurring / frequency
        rec = _RECURRING.search(body)
        if rec:
            ex.recurring = self._field(True, rec.group(0), "recurrence phrase", 0.75)
            ex.event_frequency = self._field(
                _frequency_of(rec.group(0)), rec.group(0), "derived from recurrence phrase", 0.7
            )

        # tech / India relevance (0..1 evidence scores)
        if ex.technologies.is_known:
            n = len(ex.technologies.value)  # type: ignore[arg-type]
            ex.tech_relevance = self._field(
                round(min(1.0, n / 3), 3),
                ", ".join(ex.technologies.value)[:120],  # type: ignore[arg-type]
                "tech-taxonomy density",
                min(1.0, n / 3),
                inferred=True,
            )
        india_score = _india_relevance(bool(india_hit), bool(city), ex.state.is_known)
        if india_score > 0:
            ex.india_relevance = self._field(
                india_score,
                (india_hit.group(0) if india_hit else (city or "")),
                "India / city / state evidence",
                india_score,
                inferred=True,
            )

        return ex


def _frequency_of(phrase: str) -> str:
    p = phrase.lower()
    if "week" in p or "fortnight" in p or "bi-week" in p:
        return "weekly"
    if "month" in p:
        return "monthly"
    if "quarter" in p:
        return "quarterly"
    if "annual" in p or "year" in p:
        return "annual"
    return "recurring"


def _india_relevance(has_india: bool, has_city: bool, has_state: bool) -> float:
    score = 0.0
    if has_india:
        score = max(score, 1.0)
    if has_city:
        score = max(score, 0.8)
    if has_state:
        score = max(score, 0.7)
    return round(score, 3)


def merge_extractions(ai: AIExtraction, seed: dict[str, ExtractedField]) -> AIExtraction:
    """Overlay deterministic `seed` fields onto an AI extraction (deterministic wins → HYBRID).

    Used when D1/D2 already know some fields structurally: those are authoritative and should not
    be second-guessed by AI. Only overrides fields the seed actually knows.
    """
    changed = False
    for name, seed_field in seed.items():
        if seed_field.is_known:
            setattr(ai, name, seed_field)
            changed = True
    if changed:
        ai.method = ExtractionMethod.HYBRID
    return ai
