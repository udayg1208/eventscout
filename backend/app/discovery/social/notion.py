"""Notion public-page extractor (Phase 8D).

Handles PUBLIC Notion pages (notion.site / notion.so) — extracting workshops, hackathons, meetups,
schedules, and calendars from the page's public HTML. Public content only; no auth. Event-type
hints are surfaced into the title's provenance when present.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og, title_tag
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.NOTION
_EVENT_KIND = re.compile(r"\b(workshops?|hackathons?|meetups?|schedules?|bootcamps?)\b", re.I)


def matches(url: str, html: str) -> bool:
    low = url.lower()
    return "notion.site" in low or "notion.so" in low


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    if not ex.title.is_known:
        t = og(html, "title") or title_tag(html)
        if t:
            ex.title = fb.field(t, t, "Notion page title", 0.6)
    kind = _EVENT_KIND.search(html)
    if kind and not ex.community.is_known:
        ex.community = fb.field(
            og(html, "site_name") or "Notion",
            kind.group(0),
            f"Notion {kind.group(0)} page",
            0.6,
            inferred=True,
        )
    return ex
