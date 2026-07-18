"""Pure ingestion stages — shared by the Sandbox and the Runner.

Each stage is deterministic and storage-free, so the same normalize / classify /
validate / dedup / quality logic runs identically whether previewing a provider in the
sandbox or ingesting it into production. All reuse the frozen provider intelligence
(`normalize_city`, `classify_category`, `deduplicate`) verbatim — nothing is rewritten.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.city import normalize_city
from app.models.event import Event
from app.providers.classify import classify_category
from app.providers.dedup import deduplicate
from app.providers.ranking import completeness

_MAX_COMPLETENESS = 6
# Optional fields whose absence we track as data sparsity (not a rejection).
_TRACKED_FIELDS = ("description", "city", "location", "price", "end_date", "is_free")


def normalize(events: list[Event]) -> list[Event]:
    """Canonicalize the city at the ingestion boundary (Bengaluru -> Bangalore)."""
    out: list[Event] = []
    for event in events:
        canonical = normalize_city(event.city)
        out.append(
            event.model_copy(update={"city": canonical}) if canonical != event.city else event
        )
    return out


def classify(events: list[Event]) -> list[Event]:
    """Refine each event's category with the deterministic content classifier."""
    out: list[Event] = []
    for event in events:
        category = classify_category(event)
        out.append(
            event.model_copy(update={"category": category}) if category != event.category else event
        )
    return out


@dataclass
class ValidationOutcome:
    valid: list[Event] = field(default_factory=list)
    invalid: list[tuple[Event, str]] = field(default_factory=list)  # (event, reason)
    missing_fields: dict[str, int] = field(default_factory=dict)


def validate_events(events: list[Event], *, today: date) -> ValidationOutcome:
    """Quality-gate already-structurally-valid events. Rejects only genuine
    disqualifiers (empty title, already ended); tracks field sparsity separately so a
    provider that simply omits optional fields is reported, not rejected."""
    outcome = ValidationOutcome()
    missing: Counter[str] = Counter()
    for event in events:
        reasons: list[str] = []
        if not event.title.strip():
            reasons.append("empty title")
        if (event.end_date or event.start_date) < today:
            reasons.append("already ended")
        for name in _TRACKED_FIELDS:
            if getattr(event, name) is None:
                missing[name] += 1
        if event.city is None and not event.is_online:
            missing["city (offline)"] += 1
        if reasons:
            outcome.invalid.append((event, "; ".join(reasons)))
        else:
            outcome.valid.append(event)
    outcome.missing_fields = dict(missing)
    return outcome


def self_dedupe(events: list[Event]) -> tuple[list[Event], int]:
    """Collapse duplicates within a single batch. Returns (survivors, removed_count)."""
    survivors = deduplicate(events)
    return survivors, len(events) - len(survivors)


def quality_score(valid: list[Event], *, fetched: int, duplicates: int) -> float:
    """A 0..1 signal blending completeness, validity rate, and uniqueness."""
    if fetched == 0:
        return 0.0
    avg_completeness = (
        sum(completeness(e) for e in valid) / (len(valid) * _MAX_COMPLETENESS) if valid else 0.0
    )
    validity_rate = len(valid) / fetched
    uniqueness = 1.0 - duplicates / fetched
    return round(0.5 * avg_completeness + 0.3 * validity_rate + 0.2 * uniqueness, 3)


def event_preview(event: Event) -> dict[str, object]:
    """A compact, serializable view of a normalized event for preview reports."""
    return {
        "title": event.title,
        "category": event.category.value,
        "city": event.city,
        "start_date": event.start_date.isoformat(),
        "is_online": event.is_online,
        "provider": event.provider,
        "url": str(event.url),
    }
