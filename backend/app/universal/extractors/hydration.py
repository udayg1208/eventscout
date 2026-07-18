"""Hydration / embedded-JSON extractors (Phase 10B) — reuse D2, go field-level.

Reuses D2's `extract_next_data` / `extract_window_state` / `extract_embedded_json` to pull the JSON
a framework serialized into the page, then walks it for event-shaped objects and maps their keys to
the universal schema with provenance. Covers Next.js (`__NEXT_DATA__`), Nuxt (`window.__NUXT__`),
Astro islands, generic hydration (`__INITIAL_STATE__` / `__APOLLO_STATE__` /
`__PRELOADED_STATE__`), and any `<script type="application/json">` blob. Framework-agnostic: it
keys on the *shape*, not the name.
"""

from __future__ import annotations

import json
import re
from html import unescape

from app.discovery.hydration import (
    extract_embedded_json,
    extract_next_data,
    extract_window_state,
)
from app.universal.models import ExtractedField, ExtractionResult, ExtractionSource, Page, RawEvent
from app.universal.provenance import inferred, known

_NAME_KEYS = ("name", "title", "event_name", "eventName", "summary", "headline")
_DATE_KEYS = (
    "startDate",
    "start_date",
    "start_at",
    "startAt",
    "startDateTime",
    "start_time",
    "start",
    "date",
    "datetime",
)
_END_KEYS = ("endDate", "end_date", "end_at", "endAt", "end")
_URL_KEYS = ("url", "link", "registrationUrl", "registration_url", "rsvpUrl", "permalink", "href")
_DESC_KEYS = ("description", "about", "summary", "excerpt")
_ORG_KEYS = ("organizer", "host", "community", "organization", "organiser")
_VENUE_KEYS = ("venue", "place", "location")
_CITY_KEYS = ("city", "addressLocality", "locality")


def _first(node: dict, keys) -> tuple[str, str] | None:
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip(), k
        if isinstance(v, dict):
            nested = v.get("name") or v.get("url") or v.get("addressLocality")
            if isinstance(nested, str) and nested.strip():
                return nested.strip(), k
    return None


def _looks_event(node: dict) -> bool:
    keys = {k.lower() for k in node}
    t = str(node.get("@type") or node.get("type") or "").lower()
    has_name = any(k.lower() in keys for k in _NAME_KEYS)
    has_date = any(k.lower() in keys for k in _DATE_KEYS)
    return (has_name and has_date) or t.endswith("event")


def _event_dicts(obj) -> list[dict]:
    out: list[dict] = []
    stack, seen = [obj], 0
    while stack and seen < 200_000:
        cur = stack.pop()
        seen += 1
        if isinstance(cur, dict):
            if _looks_event(cur):
                out.append(cur)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def _raw_from_dict(node: dict, source: ExtractionSource, conf: float) -> RawEvent:
    f: dict[str, ExtractedField] = {}
    snip = json.dumps(node)[:200]

    def put(name, pair, reason, c=conf, inf=False):
        if pair:
            f[name] = (inferred if inf else known)(
                pair[0], snippet=snip, reason=f"{reason} ({pair[1]})", confidence=c
            )

    put("title", _first(node, _NAME_KEYS), "hydration name")
    put("start_date", _first(node, _DATE_KEYS), "hydration start date")
    put("end_date", _first(node, _END_KEYS), "hydration end date", conf * 0.9)
    put("description", _first(node, _DESC_KEYS), "hydration description", conf * 0.8)
    put("registration_url", _first(node, _URL_KEYS), "hydration url", conf * 0.8)
    put("organizer", _first(node, _ORG_KEYS), "hydration organizer", conf * 0.85)
    put("venue", _first(node, _VENUE_KEYS), "hydration venue", conf * 0.8)
    put("city", _first(node, _CITY_KEYS), "hydration city", conf * 0.85)
    for key in ("online", "isOnline", "is_online", "virtual"):
        if node.get(key) is True:
            put("mode", ("online", key), "hydration online flag", conf * 0.85, inf=True)
            break
    return RawEvent(source=source, fields=f)


def _results(obj, source: ExtractionSource, conf: float) -> list[RawEvent]:
    return [
        ev
        for node in _event_dicts(obj)
        if (ev := _raw_from_dict(node, source, conf)).fields.get("title")
    ]


class NextDataExtractor:
    source = ExtractionSource.NEXT_DATA

    def extract(self, page: Page) -> ExtractionResult:
        parsed = extract_next_data(page.html)
        events = _results(parsed, self.source, 0.75) if parsed is not None else []
        return ExtractionResult(source=self.source, events=events, note="__NEXT_DATA__")


class NuxtExtractor:
    source = ExtractionSource.NUXT

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for var in ("__NUXT__", "__NUXT_DATA__"):
            state = extract_window_state(page.html, var)
            if state is not None:
                events.extend(_results(state, self.source, 0.7))
        return ExtractionResult(source=self.source, events=events, note="window.__NUXT__")


_ASTRO_ISLAND = re.compile(r"<astro-island\b[^>]*\bprops=(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)


class AstroExtractor:
    source = ExtractionSource.ASTRO

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for _quote, raw in _ASTRO_ISLAND.findall(page.html):
            try:
                data = json.loads(unescape(raw))
            except ValueError:
                continue
            events.extend(_results(data, self.source, 0.65))
        return ExtractionResult(source=self.source, events=events, note="astro-island props")


class HydrationExtractor:
    source = ExtractionSource.HYDRATION

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for var in (
            "__INITIAL_STATE__",
            "__APOLLO_STATE__",
            "__PRELOADED_STATE__",
            "DATA",
            "bootstrap",
        ):
            state = extract_window_state(page.html, var)
            if state is not None:
                events.extend(_results(state, self.source, 0.7))
        return ExtractionResult(source=self.source, events=events, note="window hydration state")


class EmbeddedJsonExtractor:
    source = ExtractionSource.EMBEDDED_JSON

    def extract(self, page: Page) -> ExtractionResult:
        parsed_next = extract_next_data(page.html)  # avoid double-counting __NEXT_DATA__
        events: list[RawEvent] = []
        for blob in extract_embedded_json(page.html):
            if parsed_next is not None and blob == parsed_next:
                continue
            events.extend(_results(blob, self.source, 0.6))
        return ExtractionResult(source=self.source, events=events, note="application/json blobs")
