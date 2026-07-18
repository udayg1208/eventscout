"""Organizer extraction (Phase 10C) — turn a page/event into a provenance-bearing profile.

Reads served bytes (no browser, no network) and extracts the organizer's identity + ecosystem:
name, aliases, parent org, chapter, university, department, community, recurring series, sponsors,
venue, domains, calendars, feeds, and social pages (GitHub/Discord/Telegram/LinkedIn/Notion).
Reuses 10B's text helpers and D1's domain util. Every field carries provenance; anything
unsupported is UNKNOWN.
"""

from __future__ import annotations

import re

from app.discovery.urls import registrable_domain
from app.organizers.chapters import detect_chapter
from app.organizers.models import ExtractedField, NodeType, OrganizerProfile
from app.organizers.series import detect_series
from app.organizers.taxonomy import find_sponsors
from app.organizers.university import detect_university_name, detect_university_units
from app.universal.provenance import inferred, known
from app.universal.text_utils import detect_location, detect_technologies, strip_tags

_OG_SITE = re.compile(
    r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_LD_ORG = re.compile(r'"organizer"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', re.I)
_LD_PARENT = re.compile(r'"parentOrganization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', re.I)
_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_LINK_FEED = re.compile(
    r'<link[^>]+type=["\']application/(?:rss\+xml|atom\+xml)["\'][^>]+href=["\']([^"\']+)["\']',
    re.I,
)
_VENUE = re.compile(
    r"(?:venue|held at|hosted at|location)\s*[:\-]?\s*([A-Z][\w &.,'-]{3,60})", re.I
)
# strip_tags concatenates elements — cut a venue phrase before run-on link/social labels
_VENUE_STOP = re.compile(
    r"\s+(?:GitHub|Discord|Telegram|LinkedIn|Notion|Calendar|RSS|Feed|Register|Sponsored)\b", re.I
)

_SOCIAL = [
    ("github", NodeType.GITHUB_ORG, re.compile(r"github\.com/([^/\"'?#]+)", re.I)),
    ("discord", NodeType.DISCORD, re.compile(r"discord\.(?:gg|com/invite)/[^\"'?#]+", re.I)),
    ("telegram", NodeType.TELEGRAM, re.compile(r"t\.me/[^\"'?#]+", re.I)),
    (
        "linkedin",
        NodeType.LINKEDIN_PAGE,
        re.compile(r"linkedin\.com/(?:company|in)/[^\"'?#]+", re.I),
    ),
    (
        "notion",
        NodeType.NOTION_WORKSPACE,
        re.compile(r"[\w-]+\.notion\.(?:site|so)[^\"'?#]*", re.I),
    ),
]
_CALENDAR = re.compile(r"\.ics\b|/calendar|calendar\.google\.com|lu\.ma/[^\"'?#]+", re.I)
_FEED = re.compile(r"/feed\b|/rss\b|\.rss\b|atom\.xml|feed\.xml|/rss\.xml", re.I)


def _clean(text: str) -> str:
    return " ".join(strip_tags(text).split())[:200]


class OrganizerExtractor:
    def extract(self, url: str, html: str, *, hint_name: str | None = None) -> OrganizerProfile:
        text = strip_tags(html)
        f: dict[str, ExtractedField] = {}

        name, name_snip = self._name(html, hint_name)
        if name:
            f["name"] = known(name, snippet=name_snip, reason="organizer name", confidence=0.8)

        # chapter family + implied parent + node type
        node_type = NodeType.ORGANIZATION
        ch = detect_chapter(f"{name or ''} {text[:2000]}")
        if ch:
            key, full, ntype, snip = ch
            node_type = ntype
            f["chapter"] = known(key, snippet=snip, reason="chapter family", confidence=0.85)
            f["community"] = inferred(
                full, snippet=snip, reason="chapter → community", confidence=0.7
            )
            if name and full.lower() not in name.lower():
                f["parent_org"] = inferred(
                    full, snippet=snip, reason="chapter parent org", confidence=0.6
                )

        # explicit parent from JSON-LD wins
        pm = _LD_PARENT.search(html)
        if pm:
            f["parent_org"] = known(
                pm.group(1),
                snippet=pm.group(0)[:120],
                reason="JSON-LD parentOrganization",
                confidence=0.85,
            )

        # university + campus units
        uni = detect_university_name(f"{name or ''} {text[:2000]}")
        if uni:
            f["university"] = known(
                uni[0], snippet=uni[1], reason="university name", confidence=0.75
            )
            if node_type is NodeType.ORGANIZATION:
                node_type = NodeType.UNIVERSITY_CLUB
        for label, _ntype, snip in detect_university_units(text):
            if label == "department" and "department" not in f:
                f["department"] = known(
                    _clean(snip), snippet=snip, reason="campus unit", confidence=0.6
                )

        # recurring series
        series = detect_series(text)
        if series:
            f["series"] = known(
                [s[0] for s in series],
                snippet=", ".join(s[2] for s in series)[:120],
                reason="recurring series",
                confidence=0.7,
            )

        # sponsors
        sponsors = find_sponsors(text)
        if sponsors:
            f["sponsors"] = known(
                [s[0] for s in sponsors],
                snippet=sponsors[0][1],
                reason="sponsor mention",
                confidence=0.6,
            )

        # venue (stop before link/social labels that strip_tags may have run together)
        vm = _VENUE.search(text)
        if vm:
            venue = _VENUE_STOP.split(vm.group(1))[0].strip(" ,.-")
            if venue:
                f["venue"] = known(
                    _clean(venue), snippet=vm.group(0)[:120], reason="venue phrase", confidence=0.55
                )

        # location + technologies
        city, _state, _country, loc_snip = detect_location(text[:5000])
        if city:
            f["city"] = known(city, snippet=loc_snip, reason="known city", confidence=0.7)
        techs = detect_technologies(f"{name or ''} {text[:5000]}")
        if techs:
            f["technologies"] = known(
                techs, snippet=", ".join(techs)[:120], reason="tech taxonomy", confidence=0.65
            )

        # links → domains / calendars / feeds / social pages
        links = self._classify_links(html, url)
        base_domain = registrable_domain(url) if url else None
        domains = sorted(
            {d for d in ([base_domain] if base_domain else []) + links["domains"] if d}
        )
        if domains:
            f["domains"] = known(
                domains,
                snippet=", ".join(domains)[:120],
                reason="page/link domains",
                confidence=0.7,
            )
        if links["calendars"]:
            f["calendars"] = known(
                links["calendars"],
                snippet=links["calendars"][0][:120],
                reason="calendar link",
                confidence=0.7,
            )
        if links["feeds"]:
            f["feeds"] = known(
                links["feeds"], snippet=links["feeds"][0][:120], reason="feed link", confidence=0.7
            )
        socials = {k: v for k, v in links["social"].items() if v}
        if socials:
            f["social_pages"] = known(
                socials, snippet=str(socials)[:120], reason="social profile links", confidence=0.7
            )

        # aliases: chapter expansion gives an alternate surface form
        aliases = []
        if name:
            aliases.append(name)
        if ch and name and ch[1] not in aliases:
            aliases.append(ch[1])
        if len(aliases) > 1:
            f["aliases"] = inferred(
                sorted(set(aliases)), snippet=name or "", reason="alias/expansion", confidence=0.5
            )

        return OrganizerProfile(fields=f, node_type=node_type)

    # -- helpers -----------------------------------------------------------

    def _name(self, html: str, hint: str | None) -> tuple[str | None, str]:
        if hint:
            return hint.strip(), f"hint: {hint}"
        for pat, why in (
            (_LD_ORG, "JSON-LD organizer.name"),
            (_OG_SITE, "og:site_name"),
            (_OG_TITLE, "og:title"),
            (_H1, "<h1>"),
            (_TITLE, "<title>"),
        ):
            m = pat.search(html)
            if m:
                val = _clean(m.group(1))
                if val:
                    return val, f"{why}: {val}"
        return None, ""

    def _classify_links(self, html: str, base: str) -> dict:
        out = {
            "social": {k: None for k, _n, _p in _SOCIAL},
            "calendars": [],
            "feeds": [],
            "domains": [],
        }
        hrefs = _HREF.findall(html) + _LINK_FEED.findall(html)
        base_dom = registrable_domain(base) if base else None
        for href in hrefs:
            low = href.lower()
            matched = False
            for key, _ntype, pat in _SOCIAL:
                if pat.search(href) and out["social"][key] is None:
                    out["social"][key] = href
                    matched = True
                    break
            if matched:
                continue
            if _CALENDAR.search(low):
                out["calendars"].append(href)
            elif _FEED.search(low):
                out["feeds"].append(href)
            elif href.startswith(("http://", "https://")):
                dom = registrable_domain(href)
                if dom and dom != base_dom:
                    out["domains"].append(dom)
        out["calendars"] = sorted(set(out["calendars"]))[:5]
        out["feeds"] = sorted(set(out["feeds"]))[:5]
        out["domains"] = sorted(set(out["domains"]))[:10]
        return out
