"""Organizer confidence (Phase 10C) — explainable, eight signals.

How confident are we that this is a real, active organizer (not a one-off)? Combines
recurring-series presence, structured-metadata quality, external references, an organizer web
presence, calendars, feeds, social presence, and identity consistency — each explained, weights
summing to 1.0. Not ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.organizers.models import OrganizerProfile

WEIGHTS = {
    "recurring": 0.20,
    "structured": 0.16,
    "social_presence": 0.14,
    "external_refs": 0.12,
    "organizer_pages": 0.12,
    "calendars": 0.10,
    "feeds": 0.08,
    "consistency": 0.08,
}


@dataclass
class OrganizerConfidenceScore:
    total: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def _n(profile: OrganizerProfile, name: str) -> int:
    v = profile.get(name)
    if isinstance(v, (list, dict)):
        return len(v)
    return 1 if v else 0


class OrganizerConfidence:
    def score(self, profile: OrganizerProfile, *, event_count: int = 0) -> OrganizerConfidenceScore:
        comp: dict[str, float] = {}
        why: dict[str, str] = {}

        recurring = 1.0 if profile.get("series") else min(1.0, event_count / 3.0)
        comp["recurring"] = recurring
        why["recurring"] = (
            "recurring series" if profile.get("series") else f"{event_count} events seen"
        )

        known = [profile.fields[n] for n in profile.known_fields()]
        comp["structured"] = (sum(f.confidence for f in known) / len(known)) if known else 0.0
        why["structured"] = f"avg provenance over {len(known)} field(s)"

        socials = _n(profile, "social_pages")
        comp["social_presence"] = min(1.0, socials / 3.0)
        why["social_presence"] = f"{socials} social channel(s)"

        comp["external_refs"] = min(1.0, _n(profile, "domains") / 3.0)
        why["external_refs"] = f"{_n(profile, 'domains')} domain(s)"

        comp["organizer_pages"] = 1.0 if profile.get("domains") else 0.0
        why["organizer_pages"] = "has website" if comp["organizer_pages"] else "no website"

        comp["calendars"] = 1.0 if profile.get("calendars") else 0.0
        why["calendars"] = "has calendar" if comp["calendars"] else "none"

        comp["feeds"] = 1.0 if profile.get("feeds") else 0.0
        why["feeds"] = "has feed" if comp["feeds"] else "none"

        has_context = any(
            profile.get(n) for n in ("chapter", "community", "parent_org", "university")
        )
        comp["consistency"] = (
            1.0 if (profile.get("name") and has_context) else (0.5 if profile.get("name") else 0.0)
        )
        why["consistency"] = (
            "named + chapter/university context" if comp["consistency"] == 1.0 else "name only"
        )

        total = round(sum(comp[k] * WEIGHTS[k] for k in WEIGHTS), 4)
        return OrganizerConfidenceScore(total=total, components=comp, reasons=why)
