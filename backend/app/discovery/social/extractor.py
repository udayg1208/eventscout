"""Shared social extraction (Phase 8D) — provenance-bearing, deterministic, HTML-only.

Common field extraction reused by every platform module: JSON-LD Event parsing, OpenGraph/`<title>`
metadata, technology (5A taxonomy), location (`city.detect_city`), date, registration/calendar/feed
links, and related links (reusing D1's link/feed extractors). Every value carries provenance; a
field with no supporting snippet is UNKNOWN. Also the **safety gate** that rejects login walls,
paywalls, and off-topic content — without ever bypassing authentication.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from app.city import detect_city
from app.discovery.links import extract_feed_links, extract_page_links
from app.discovery.social.models import (
    EVENT_FIELDS,
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
)
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

_LDJSON = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
_OG = re.compile(
    r'<meta\b[^>]*\bproperty=["\']og:{prop}["\'][^>]*\bcontent=["\']([^"\']+)["\']'
    r'|<meta\b[^>]*\bcontent=["\']([^"\']+)["\'][^>]*\bproperty=["\']og:{prop}["\']'
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_URL = re.compile(r'https?://[^\s"\'<>)]+')
_DATE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})\b"
)
_REG = re.compile(r"register|rsvp|tickets?|eventbrite|lu\.ma|devfolio|konfhub|luma\.com", re.I)
_CAL = re.compile(r"\.ics(\b|$)|calendar\.google\.com", re.I)

# --- safety: reject anything requiring auth or off-topic ---
_LOGIN_WALL = re.compile(
    r"\bauthwall\b|sign ?in to (continue|view|see)|log ?in to (continue|view|see|read)|"
    r"members? only|please log ?in|create an account to|subscribe to (read|continue)|paywall",
    re.I,
)
_REJECT = re.compile(
    r"\b(casino|betting|gambling|poker|lottery|porn|xxx|adult content|escort|"
    r"\belection\b|political rally|religious service|temple darshan|shopping deals|"
    r"buy now|add to cart|movie tickets?|concert tickets?)\b",
    re.I,
)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub("", fragment)).strip()


def og(html: str, prop: str) -> str | None:
    m = re.search(_OG.pattern.replace("{prop}", re.escape(prop)), html, re.I)
    return (m.group(1) or m.group(2)) if m else None


def title_tag(html: str) -> str | None:
    m = _TITLE.search(html)
    return _text(m.group(1)) if m else None


def _iter_objs(data):
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def jsonld_events(html: str) -> list[dict]:
    events: list[dict] = []
    for block in _LDJSON.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for obj in _iter_objs(data):
            if isinstance(obj, dict) and "event" in str(obj.get("@type", "")).lower():
                events.append(obj)
    return events


def technologies(text: str) -> list[str]:
    low = text.lower()
    return sorted({name for name, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(low)})


class FieldBuilder:
    """Builds ExtractedFields with deterministic provenance stamped at `now`."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def field(self, value, snippet, reason, confidence, *, inferred=False) -> ExtractedField:
        return ExtractedField(
            value=value,
            status=FieldStatus.INFERRED if inferred else FieldStatus.EXTRACTED,
            provenance=Provenance(
                source_snippet=str(snippet)[:200],
                reason=reason,
                confidence=round(confidence, 3),
                method=ExtractionMethod.DETERMINISTIC,
                timestamp=self._now,
            ),
        )


def build_common(url: str, html: str, *, now: datetime) -> dict[str, ExtractedField]:
    """Platform-agnostic fields: title/date/location/tech/registration/calendar/feed/related."""
    fb = FieldBuilder(now)
    out: dict[str, ExtractedField] = {}
    text = _text(html)
    events = jsonld_events(html)

    # title: JSON-LD name → og:title → <title>
    ev = events[0] if events else {}
    name = ev.get("name") if isinstance(ev.get("name"), str) else None
    title = name or og(html, "title") or title_tag(html)
    if title:
        out["title"] = fb.field(title, title, "JSON-LD/og/title", 0.9 if name else 0.7)

    # date: JSON-LD startDate → text regex
    start = ev.get("startDate") if isinstance(ev.get("startDate"), str) else None
    if start:
        out["date"] = fb.field(start, start, "JSON-LD startDate", 0.9)
    else:
        m = _DATE.search(text)
        if m:
            out["date"] = fb.field(
                m.group(0), m.group(0), "date pattern in text", 0.6, inferred=True
            )

    # location: JSON-LD location → detected city
    loc = None
    lo = ev.get("location")
    if isinstance(lo, dict):
        loc = lo.get("name") or (lo.get("address", {}) or {}).get("addressLocality")
    city = detect_city(title or "", text)
    if loc:
        out["location"] = fb.field(loc, loc, "JSON-LD location", 0.85)
    elif city:
        out["location"] = fb.field(city, city, "detected city", 0.7, inferred=True)

    # technologies
    techs = technologies(f"{title or ''} {text}")
    if techs:
        out["technologies"] = fb.field(
            techs, ", ".join(techs), "5A tech taxonomy", min(1.0, len(techs) / 3)
        )

    # registration / calendar / feed / related
    urls = _URL.findall(html)
    reg = [u for u in urls if _REG.search(u)]
    if reg:
        out["registration_url"] = fb.field(reg[0], reg[0], "registration link", 0.75)
    cal = [u for u in urls if _CAL.search(u)]
    if cal:
        out["calendar"] = fb.field(cal[0], cal[0], "calendar link", 0.8)
    feeds = extract_feed_links(html, url) if "<link" in html.lower() else []
    if feeds:
        out["feed"] = fb.field(feeds[0][0], feeds[0][0], "feed <link rel=alternate>", 0.85)
    related = extract_page_links(html, url)[:15] if "<a " in html.lower() else []
    if related:
        out["related_links"] = fb.field(
            related, f"{len(related)} links", "in-page anchors", 0.6, inferred=True
        )
    return out


def safety_check(url: str, html: str, extraction) -> tuple[bool, list[str]]:
    """Reject login-walled / paywalled / off-topic pages. Requires positive event/tech/community
    evidence. Never bypasses auth — a login wall means we DECLINE the page."""
    reasons: list[str] = []
    m = _LOGIN_WALL.search(html)
    if m:
        reasons.append(f"login/paywall: '{m.group(0)}'")
    r = _REJECT.search(html)
    if r:
        reasons.append(f"off-topic: '{r.group(0)}'")
    has_evidence = (
        any(
            extraction.__dict__[f].is_known
            for f in ("technologies", "title", "community")
            if f in EVENT_FIELDS
        )
        or extraction.technologies.is_known
        or extraction.community.is_known
    )
    if not reasons and not has_evidence:
        reasons.append("insufficient evidence — no technology/title/community signal")
    return (not reasons), reasons
