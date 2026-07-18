"""Universal Event Understanding models (Phase 10B).

The engine answers one question about ANY public page — *where is the event information?* —
regardless of framework. Each isolated extractor returns an `ExtractionResult` of `RawEvent`s
(partial, per-field with provenance); the engine merges them into `UniversalEvent`s. Provenance is
reused verbatim from D4 (`ExtractedField` / `Provenance` / `FieldStatus` / `ExtractionMethod`):
every value cites the exact snippet it came from, and UNKNOWN is always preferred over a guess.
Additive; no network, no browser, no LLM. Discovery only — nothing is written to the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Provenance model reused from D4 — never re-implemented.
from app.discovery.ai.models import (  # noqa: F401
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
    unknown,
)


class ExtractionSource(StrEnum):
    JSONLD = "jsonld"
    OPENGRAPH = "opengraph"
    MICRODATA = "microdata"
    NEXT_DATA = "next_data"
    NUXT = "nuxt"
    ASTRO = "astro"
    HYDRATION = "hydration"
    EMBEDDED_JSON = "embedded_json"
    MARKDOWN = "markdown"
    TABLE = "table"
    DEFINITION_LIST = "definition_list"
    FAQ = "faq"
    CALENDAR = "calendar"
    SEMANTIC = "semantic"


class EventType(StrEnum):
    MEETUP = "meetup"
    CONFERENCE = "conference"
    HACKATHON = "hackathon"
    WORKSHOP = "workshop"
    WEBINAR = "webinar"
    TALK = "talk"
    SUMMIT = "summit"
    BOOTCAMP = "bootcamp"
    UNKNOWN = "unknown"


class EventMode(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


# The universal event schema — exactly the phase brief's field list.
FIELD_NAMES: tuple[str, ...] = (
    "title",
    "organizer",
    "description",
    "start_date",
    "end_date",
    "timezone",
    "city",
    "state",
    "country",
    "venue",
    "mode",
    "registration_url",
    "deadline",
    "technologies",
    "audience",
    "event_type",
    "fee",
    "speakers",
    "sponsors",
    "tags",
    "images",
)

# Which sources count as structured (used by the confidence engine + early-stop).
STRUCTURED_SOURCES = frozenset(
    {
        ExtractionSource.JSONLD,
        ExtractionSource.MICRODATA,
        ExtractionSource.NEXT_DATA,
        ExtractionSource.NUXT,
        ExtractionSource.ASTRO,
        ExtractionSource.HYDRATION,
        ExtractionSource.EMBEDDED_JSON,
        ExtractionSource.CALENDAR,
    }
)


@dataclass
class RawEvent:
    """A partial event from one extractor — field → ExtractedField (with provenance)."""

    source: ExtractionSource
    fields: dict[str, ExtractedField] = field(default_factory=dict)

    def value(self, name: str):
        f = self.fields.get(name)
        return f.value if (f and f.is_known) else None

    def title_key(self) -> str | None:
        t = self.value("title")
        return " ".join(str(t).lower().split())[:80] if t else None


@dataclass
class ExtractionResult:
    """What one extractor returns for a page — zero or more RawEvents + a note."""

    source: ExtractionSource
    events: list[RawEvent] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {"source": self.source.value, "events": len(self.events), "note": self.note}


@dataclass
class Page:
    """The input every extractor receives: a URL and its served bytes (HTML/JSON/Markdown/ICS)."""

    url: str
    html: str
    content_type: str = "text/html"


@dataclass
class UniversalEvent:
    source_url: str
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    confidence: float = 0.0
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    valid: bool = True
    reject_reason: str | None = None

    def get(self, name: str):
        f = self.fields.get(name)
        return f.value if (f and f.is_known) else None

    @property
    def title(self) -> str | None:
        return self.get("title")

    def known_fields(self) -> list[str]:
        return [n for n in FIELD_NAMES if n in self.fields and self.fields[n].is_known]

    def as_dict(self) -> dict:
        out: dict = {
            "source_url": self.source_url,
            "confidence": round(self.confidence, 4),
            "confidence_breakdown": {k: round(v, 4) for k, v in self.confidence_breakdown.items()},
            "sources": list(self.sources),
            "valid": self.valid,
            "reject_reason": self.reject_reason,
            "fields": {},
        }
        for name in FIELD_NAMES:
            f = self.fields.get(name)
            if f and f.is_known:
                out["fields"][name] = {
                    "value": f.value,
                    "status": f.status.value,
                    "confidence": round(f.confidence, 3),
                    "reason": f.provenance.reason if f.provenance else None,
                    "snippet": (f.provenance.source_snippet[:120] if f.provenance else None),
                }
        return out


@dataclass
class UniversalReport:
    url: str
    events: list[UniversalEvent] = field(default_factory=list)
    extractors_run: list[str] = field(default_factory=list)
    raw_events: int = 0
    rejected: int = 0
    skipped_unchanged: bool = False

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "events": [e.as_dict() for e in self.events],
            "extractors_run": list(self.extractors_run),
            "raw_events": self.raw_events,
            "rejected": self.rejected,
            "skipped_unchanged": self.skipped_unchanged,
        }
