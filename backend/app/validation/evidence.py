"""Evidence collection (Phase 10E) — run the real pipeline over a fetched page.

Given a fetched page, reuses 10B (universal event extraction) and 10C (organizer extraction) to
gather verification evidence — events, JSON-LD, organizer, technologies, city, registration, feeds,
calendars — each observed, never invented. This is the heart of "verify through the existing
pipeline": the same extractors that power discovery decide whether a generated seed is real.
"""

from __future__ import annotations

from app.organizers import OrganizerConfidence, OrganizerExtractor
from app.universal import UniversalEventEngine
from app.validation.models import Evidence


class EvidenceCollector:
    def __init__(
        self,
        *,
        universal: UniversalEventEngine | None = None,
        organizer: OrganizerExtractor | None = None,
        organizer_confidence: OrganizerConfidence | None = None,
    ) -> None:
        self._universal = universal or UniversalEventEngine()
        self._organizer = organizer or OrganizerExtractor()
        self._org_conf = organizer_confidence or OrganizerConfidence()

    async def collect(self, url: str, html: str, seed) -> Evidence:
        ev = Evidence(reachable=True, homepage_url=url, pages_fetched=1)

        # 10B — universal event extraction
        report = await self._universal.extract(url, html)
        if report.events:
            top = report.events[0]
            ev.events_found = len(report.events)
            ev.universal_confidence = top.confidence
            ev.city = ev.city or top.get("city")
            ev.registration_url = top.get("registration_url")
            ev.technologies = list(top.get("technologies") or [])
            if "jsonld" in top.sources or "microdata" in top.sources:
                ev.has_jsonld = True
            ev.snippets.append(f"universal: {len(report.events)} event(s); top '{top.title}'")

        # 10C — organizer extraction (from the PAGE only; never seed the name, or every page
        # would "have" the seed's organizer and inflate the evidence)
        prof = self._organizer.extract(url, html)
        if prof.get("name"):
            ev.organizer_name = prof.get("name")
            ev.organizer_confidence = self._org_conf.score(prof).total
            ev.city = ev.city or prof.get("city")
            ev.technologies = sorted({*ev.technologies, *(prof.get("technologies") or [])})
            if prof.get("feeds"):
                ev.feeds = list(prof.get("feeds"))
            if prof.get("calendars"):
                ev.calendars = list(prof.get("calendars"))
            ev.snippets.append(
                f"organizer: {prof.get('name')} (chapter={prof.get('chapter')}, "
                f"city={prof.get('city')})"
            )
        return ev
