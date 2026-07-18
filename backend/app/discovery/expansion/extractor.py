"""Link Extractor (Phase 8C) — pull every kind of source out of one page's HTML.

Reuses D1's `extract_page_links` (anchors) and `extract_feed_links` (RSS/Atom/JSON feeds), then
classifies every URL on the page into calendars, GitHub/GitLab orgs, Notion, Discord invites,
Telegram channels, and blog platforms (Medium/Substack/WordPress/Blogger). Also reads the page's
`<link rel=canonical>`. HTML only — no browser, no JavaScript execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.discovery.links import extract_feed_links, extract_page_links
from app.discovery.models import FeedType
from app.discovery.urls import normalize_url, registrable_domain

_URL = re.compile(r'https?://[^\s"\'<>)]+', re.IGNORECASE)
_CANONICAL = re.compile(
    r'<link\b[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\']([^"\']+)["\']'
    r'|<link\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*\brel=["\']canonical["\']',
    re.IGNORECASE,
)

_CAL = re.compile(
    r"\.ics(\b|$)|calendar\.google\.com|outlook\.(office|live)\.com|/calendar/ical", re.I
)
_GITHUB = re.compile(r"^https?://github\.com/([A-Za-z0-9][\w.-]{0,38})", re.I)
_GITLAB = re.compile(r"^https?://gitlab\.com/([A-Za-z0-9][\w.-]{0,38})", re.I)
_NOTION = re.compile(r"notion\.(site|so)", re.I)
_DISCORD = re.compile(r"discord\.(gg|com/invite)/", re.I)
_TELEGRAM = re.compile(r"^https?://(t\.me|telegram\.me)/", re.I)
_BLOG = re.compile(r"(medium\.com|substack\.com|wordpress\.com|blogspot\.|blogger\.com)", re.I)

# github/gitlab path segments that are NOT organizations
_VCS_STOP = {
    "features",
    "about",
    "login",
    "join",
    "pricing",
    "marketplace",
    "explore",
    "sponsors",
    "topics",
    "search",
    "settings",
    "notifications",
    "orgs",
    "apps",
}


@dataclass
class Extraction:
    page_links: list[str] = field(default_factory=list)
    feeds: list[tuple[str, FeedType]] = field(default_factory=list)
    calendars: list[str] = field(default_factory=list)
    github: list[str] = field(default_factory=list)
    gitlab: list[str] = field(default_factory=list)
    notion: list[str] = field(default_factory=list)
    discord: list[str] = field(default_factory=list)
    telegram: list[str] = field(default_factory=list)
    blogs: list[str] = field(default_factory=list)
    canonical: str | None = None


def _dedupe(items):
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _canonical(html: str, base: str) -> str | None:
    m = _CANONICAL.search(html)
    if not m:
        return None
    return normalize_url(m.group(1) or m.group(2), base=base)


def _vcs_org(url: str, pattern: re.Pattern) -> str | None:
    m = pattern.match(url)
    if not m or m.group(1).lower() in _VCS_STOP:
        return None
    host = "github.com" if "github" in pattern.pattern else "gitlab.com"
    return f"https://{host}/{m.group(1)}"


def extract(result) -> Extraction:
    html = result.text
    base = result.url
    low = html.lower()

    page_links = extract_page_links(html, base) if "<a " in low else []
    feeds = extract_feed_links(html, base) if "<link" in low else []

    # every URL mentioned on the page (anchors + raw), normalized
    raw = [normalize_url(u, base=base) for u in _URL.findall(html)]
    all_urls = _dedupe([u for u in ([*page_links, *raw]) if u])

    ex = Extraction(page_links=page_links, feeds=feeds, canonical=_canonical(html, base))
    ex.calendars = _dedupe(u for u in all_urls if _CAL.search(u))
    ex.github = _dedupe(filter(None, (_vcs_org(u, _GITHUB) for u in all_urls)))
    ex.gitlab = _dedupe(filter(None, (_vcs_org(u, _GITLAB) for u in all_urls)))
    ex.notion = _dedupe(u for u in all_urls if _NOTION.search(urlsplit(u).netloc))
    ex.discord = _dedupe(u for u in all_urls if _DISCORD.search(u))
    ex.telegram = _dedupe(u for u in all_urls if _TELEGRAM.match(u))
    ex.blogs = _dedupe(u for u in all_urls if _BLOG.search(registrable_domain(u)))
    return ex
