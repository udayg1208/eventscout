"""Calendar & feed extractor (Phase 10B) — ICS (iCalendar) and RSS/Atom.

Public calendars and feeds are first-class event sources. Parses iCalendar `VEVENT` blocks
(SUMMARY/DTSTART/DTEND/LOCATION/URL) directly, and RSS/Atom `<item>`/`<entry>` elements whose title
or description carries an event signal. Deterministic; no feed library, no network.
"""

from __future__ import annotations

import re

from app.universal.extractors.base import enrich_from_text
from app.universal.models import ExtractedField, ExtractionResult, ExtractionSource, Page, RawEvent
from app.universal.provenance import known
from app.universal.text_utils import find_date, strip_tags

_VEVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.IGNORECASE | re.DOTALL)
_ICS_PROP = re.compile(r"^([A-Z\-]+)(?:;[^:]*)?:(.*)$", re.MULTILINE)
_DT = re.compile(r"(\d{4})(\d{2})(\d{2})")

_RSS_ITEM = re.compile(r"<(?:item|entry)\b[^>]*>(.*?)</(?:item|entry)>", re.IGNORECASE | re.DOTALL)


def _xml_tag(name: str):
    return re.compile(rf"<{name}\b[^>]*>(.*?)</{name}>", re.IGNORECASE | re.DOTALL)


_RSS_TITLE = _xml_tag("title")
_RSS_LINK = _xml_tag("link")
_RSS_DESC = _xml_tag("description")
_RSS_DATE = re.compile(
    r"<(?:pubDate|updated|published)\b[^>]*>(.*?)</(?:pubDate|updated|published)>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_SIGNAL = re.compile(
    r"event|meetup|conference|hackathon|workshop|webinar|summit|talk|register", re.IGNORECASE
)


def _ics_date(value: str) -> str | None:
    m = _DT.search(value)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


class CalendarExtractor:
    source = ExtractionSource.CALENDAR

    def extract(self, page: Page) -> ExtractionResult:
        events = self._ics(page) + self._rss(page)
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} calendar/feed items"
        )

    def _ics(self, page: Page) -> list[RawEvent]:
        if "BEGIN:VEVENT" not in page.html.upper():
            return []
        out: list[RawEvent] = []
        for body in _VEVENT.findall(page.html):
            props = {k.upper(): v.strip() for k, v in _ICS_PROP.findall(body)}
            f: dict[str, ExtractedField] = {}
            snip = f"VEVENT SUMMARY={props.get('SUMMARY', '')[:50]}"
            if props.get("SUMMARY"):
                f["title"] = known(
                    props["SUMMARY"][:200], snippet=snip, reason="ICS SUMMARY", confidence=0.85
                )
            if props.get("DTSTART") and _ics_date(props["DTSTART"]):
                f["start_date"] = known(
                    _ics_date(props["DTSTART"]), snippet=snip, reason="ICS DTSTART", confidence=0.85
                )
            if props.get("DTEND") and _ics_date(props["DTEND"]):
                f["end_date"] = known(
                    _ics_date(props["DTEND"]), snippet=snip, reason="ICS DTEND", confidence=0.8
                )
            if props.get("LOCATION"):
                f["venue"] = known(
                    props["LOCATION"][:200], snippet=snip, reason="ICS LOCATION", confidence=0.8
                )
            if props.get("URL"):
                f["registration_url"] = known(
                    props["URL"], snippet=snip, reason="ICS URL", confidence=0.75
                )
            if f.get("title") and f.get("start_date"):
                blob = " ".join(props.get(k, "") for k in ("SUMMARY", "DESCRIPTION", "LOCATION"))
                enrich_from_text(f, blob, base_url=page.url, conf=0.6)
                out.append(RawEvent(self.source, f))
        return out

    def _rss(self, page: Page) -> list[RawEvent]:
        html = page.html
        if "<rss" not in html.lower() and "<feed" not in html.lower():
            return []
        out: list[RawEvent] = []
        for body in _RSS_ITEM.findall(html):
            tm = _RSS_TITLE.search(body)
            title = strip_tags(tm.group(1)) if tm else ""
            dm = _RSS_DESC.search(body)
            desc = strip_tags(dm.group(1)) if dm else ""
            if not title or not _EVENT_SIGNAL.search(title + " " + desc):
                continue
            f: dict[str, ExtractedField] = {
                "title": known(
                    title[:200],
                    snippet=f"<item><title>{title[:50]}",
                    reason="RSS item title",
                    confidence=0.6,
                )
            }
            lm = _RSS_LINK.search(body)
            if lm and strip_tags(lm.group(1)):
                f["registration_url"] = known(
                    strip_tags(lm.group(1)),
                    snippet="RSS <link>",
                    reason="RSS item link",
                    confidence=0.55,
                )
            if desc:
                f["description"] = known(
                    desc[:400],
                    snippet="RSS <description>",
                    reason="RSS item description",
                    confidence=0.5,
                )
            body_text = f"{title} {desc}"
            if not find_date(body_text):
                pm = _RSS_DATE.search(body)
                if pm:
                    body_text += " " + strip_tags(pm.group(1))
            enrich_from_text(f, body_text, base_url=page.url, conf=0.5)
            if f.get("start_date"):
                out.append(RawEvent(self.source, f))
        return out
