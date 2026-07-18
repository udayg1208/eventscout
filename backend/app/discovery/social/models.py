"""Public Social & Community Discovery models (Phase 8D).

Discovers events announced on **publicly accessible** community platforms (LinkedIn public pages,
GitHub, Discord/Telegram public landing pages, Notion public pages, blogs, forums). Public content
only — no login, no auth bypass, no browser, no LLM. Reuses D4's provenance model
(`ExtractedField`/`Provenance`), so every field is grounded in a source snippet and `UNKNOWN` is
always preferred over a guess. Output stops at the Discovery Inbox (`discovered_by="social"`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Reuse D4's provenance-first field model (import, never modify).
from app.discovery.ai.models import (
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
    unknown,
)

__all__ = [
    "SocialPlatform",
    "SocialExtraction",
    "SocialPriority",
    "ExtractedField",
    "Provenance",
    "FieldStatus",
    "ExtractionMethod",
    "unknown",
    "EVENT_FIELDS",
]


class SocialPlatform(StrEnum):
    LINKEDIN = "linkedin"
    GITHUB = "github"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    NOTION = "notion"
    BLOG = "blog"
    FORUM = "forum"


# The event fields each platform extractor fills (exactly the phase brief's list).
EVENT_FIELDS = (
    "title",
    "date",
    "location",
    "organizer",
    "registration_url",
    "technologies",
    "community",
    "calendar",
    "feed",
    "related_links",
)


@dataclass
class SocialExtraction:
    """Provenance-bearing understanding of one public social page."""

    url: str
    platform: SocialPlatform
    title: ExtractedField = field(default_factory=unknown)
    date: ExtractedField = field(default_factory=unknown)
    location: ExtractedField = field(default_factory=unknown)
    organizer: ExtractedField = field(default_factory=unknown)
    registration_url: ExtractedField = field(default_factory=unknown)
    technologies: ExtractedField = field(default_factory=unknown)  # list[str]
    community: ExtractedField = field(default_factory=unknown)
    calendar: ExtractedField = field(default_factory=unknown)
    feed: ExtractedField = field(default_factory=unknown)
    related_links: ExtractedField = field(default_factory=unknown)  # list[str]
    method: ExtractionMethod = ExtractionMethod.DETERMINISTIC

    def fields(self) -> dict[str, ExtractedField]:
        return {name: getattr(self, name) for name in EVENT_FIELDS}

    def known_fields(self) -> dict[str, ExtractedField]:
        return {n: f for n, f in self.fields().items() if f.is_known}

    def mean_confidence(self) -> float:
        known = [f.confidence for f in self.known_fields().values()]
        return round(sum(known) / len(known), 4) if known else 0.0

    def as_dict(self) -> dict:
        def enc(f: ExtractedField) -> dict:
            prov = None
            if f.provenance is not None:
                prov = {
                    "source_snippet": f.provenance.source_snippet,
                    "reason": f.provenance.reason,
                    "confidence": f.provenance.confidence,
                    "method": f.provenance.method.value,
                }
            return {"value": f.value, "status": f.status.value, "provenance": prov}

        return {
            "url": self.url,
            "platform": self.platform.value,
            "method": self.method.value,
            "fields": {n: enc(f) for n, f in self.fields().items()},
        }


@dataclass
class SocialPriority:
    """Explainable source-priority score (0..1) — no magic numbers."""

    total: float
    factors: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"total": self.total, "factors": self.factors, "reasons": list(self.reasons)}
