"""Shared deterministic parsing helpers (Phase 10B) — no network, no LLM.

Framework-agnostic field parsing used by every extractor and the normalizer: strip HTML to text,
find dates (ISO / "Nov 1, 2026" / "1 November 2026" / "12/11/2026"), registration URLs,
technologies (via the 5A taxonomy), location (via `city.detect_city`), online/offline mode, event
type, and fee. Everything returns the matched snippet alongside the value so callers can build
provenance.
"""

from __future__ import annotations

import re
from html import unescape

from app.city import detect_city
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        start=1,
    )
}
_MONTH_RE = "(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2})?\b")
_MDY = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE
)
_DMY = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\.?,?\s+(\d{{4}})\b", re.IGNORECASE
)
_MY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{4}})\b", re.IGNORECASE)
_NUM = re.compile(r"\b(\d{1,2})[/](\d{1,2})[/](\d{4})\b")

_REG_WORDS = re.compile(r"regist|rsvp|ticket|apply|sign\s*up|book\s*now|join", re.IGNORECASE)
_REG_HOSTS = re.compile(
    r"lu\.ma|eventbrite\.|devfolio\.co|meetup\.com|hopin\.|konfhub\.|commudle\.|townscript\.",
    re.IGNORECASE,
)
_HREF = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

_ONLINE = re.compile(
    r"\bonline\b|\bvirtual\b|\bwebinar\b|\blivestream\b|\bremote\b|zoom|meet\.google", re.IGNORECASE
)
_OFFLINE = re.compile(
    r"\bvenue\b|\bin[- ]person\b|\bon[- ]site\b|\baddress\b|\bhall\b|\bcampus\b|\bauditorium\b",
    re.IGNORECASE,
)

_EVENT_TYPES = [
    ("hackathon", re.compile(r"hackathon|hack\b", re.IGNORECASE)),
    ("conference", re.compile(r"conference|\bconf\b|summit", re.IGNORECASE)),
    ("summit", re.compile(r"\bsummit\b", re.IGNORECASE)),
    ("workshop", re.compile(r"workshop|bootcamp|training", re.IGNORECASE)),
    ("webinar", re.compile(r"webinar|livestream", re.IGNORECASE)),
    ("meetup", re.compile(r"meetup|meet[- ]up", re.IGNORECASE)),
    ("talk", re.compile(r"\btalk\b|\btech talk\b|fireside", re.IGNORECASE)),
]

_FEE_FREE = re.compile(r"\bfree\b|no\s+(?:cost|fee|charge)|free\s+entry", re.IGNORECASE)
_FEE_PAID = re.compile(r"(₹|\bINR\b|\$|\bUSD\b|Rs\.?)\s?[\d,]+", re.IGNORECASE)

_INDIA_STATES = (
    "karnataka",
    "maharashtra",
    "delhi",
    "telangana",
    "tamil nadu",
    "kerala",
    "gujarat",
    "west bengal",
    "rajasthan",
    "uttar pradesh",
    "punjab",
    "haryana",
)
_COUNTRIES = (
    "india",
    "united states",
    "usa",
    "u.s.a",
    "uk",
    "united kingdom",
    "germany",
    "france",
    "singapore",
    "canada",
    "australia",
    "netherlands",
    "japan",
)


def strip_tags(html: str) -> str:
    text = _SCRIPT_STYLE.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", unescape(text)).strip()


def _iso_from_mdy(month_word: str, day: str, year: str) -> str:
    m = _MONTHS.get(month_word[:3].lower())
    return f"{int(year):04d}-{m:02d}-{int(day):02d}" if m else f"{month_word} {day}, {year}"


def find_dates(text: str) -> list[tuple[str, str]]:
    """All parseable dates → (canonical-or-raw, snippet). Canonical is YYYY-MM-DD when possible."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(value: str, snippet: str) -> None:
        if value not in seen:
            seen.add(value)
            found.append((value, snippet))

    for m in _ISO.finditer(text):
        add(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", m.group(0))
    for m in _MDY.finditer(text):
        add(_iso_from_mdy(m.group(1), m.group(2), m.group(3)), m.group(0))
    for m in _DMY.finditer(text):
        add(_iso_from_mdy(m.group(2), m.group(1), m.group(3)), m.group(0))
    for m in _NUM.finditer(text):
        d, mth, y = m.group(1), m.group(2), m.group(3)
        add(f"{int(y):04d}-{int(mth):02d}-{int(d):02d}", m.group(0))
    for m in _MY.finditer(text):
        mm = _MONTHS.get(m.group(1)[:3].lower())
        if mm:
            add(f"{int(m.group(2)):04d}-{mm:02d}", m.group(0))
    return found


def find_date(text: str) -> tuple[str, str] | None:
    dates = find_dates(text)
    return dates[0] if dates else None


def _resolve(href: str, base: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/") and base:
        m = re.match(r"(https?://[^/]+)", base)
        return (m.group(1) + href) if m else href
    return href


def find_registration_url(html: str, base: str = "") -> tuple[str, str] | None:
    """The most registration-like <a> on the page → (absolute url, snippet)."""
    best: tuple[int, str, str] | None = None
    for href, label in _HREF.findall(html):
        text = strip_tags(label)
        score = 0
        if _REG_WORDS.search(text):
            score += 2
        if _REG_HOSTS.search(href):
            score += 3
        if _REG_WORDS.search(href):
            score += 1
        if score and (best is None or score > best[0]):
            best = (score, _resolve(href, base), f'{href} "{text[:40]}"')
    return (best[1], best[2]) if best else None


def detect_technologies(text: str) -> list[str]:
    low = text.lower()
    return sorted({name for name, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(low)})


def detect_mode(text: str) -> tuple[str, str] | None:
    online = _ONLINE.search(text)
    offline = _OFFLINE.search(text)
    if online and offline:
        return ("hybrid", (online.group(0) + " / " + offline.group(0)))
    if online:
        return ("online", online.group(0))
    if offline:
        return ("offline", offline.group(0))
    return None


def detect_event_type(text: str) -> tuple[str, str] | None:
    for name, pat in _EVENT_TYPES:
        m = pat.search(text)
        if m:
            return (name, m.group(0))
    return None


def detect_fee(text: str) -> tuple[str, str] | None:
    m = _FEE_PAID.search(text)
    if m:
        return (m.group(0).strip(), m.group(0))
    m = _FEE_FREE.search(text)
    if m:
        return ("Free", m.group(0))
    return None


def detect_location(text: str) -> tuple[str | None, str | None, str | None, str]:
    """(city, state, country, snippet) — city via detect_city, then India-state/country keywords."""
    city = detect_city(text[:20000])
    low = text.lower()
    state = next((s.title() for s in _INDIA_STATES if s in low), None)
    country = None
    for c in _COUNTRIES:
        if re.search(rf"\b{re.escape(c)}\b", low):
            country = "India" if c == "india" else c.upper() if len(c) <= 3 else c.title()
            break
    if country is None and (city or state):
        country = "India"  # inferred: an Indian city/state implies India
    snippet = city or state or country or ""
    return city, state, country, snippet
