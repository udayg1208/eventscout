"""Forum extractor (Phase 8D) — public discussions only.

Handles public forum software: Discourse, phpBB, Flarum, Vanilla. Detects by the `<meta generator>`
marker or characteristic URL shapes, and extracts the topic title/date/technology + the forum name
as community. Public discussions only; no auth.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og, title_tag
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.FORUM
_GENERATOR = re.compile(
    r'<meta\b[^>]*\bname=["\']generator["\'][^>]*\bcontent=["\']([^"\']*'
    r"(?:discourse|phpbb|flarum|vanilla)[^\"']*)[\"']",
    re.I,
)
_URL_SHAPES = re.compile(r"/t/[\w-]+/\d+|viewtopic\.php|/d/\d+|/discussion/", re.I)


def matches(url: str, html: str) -> bool:
    return bool(_GENERATOR.search(html)) or bool(_URL_SHAPES.search(url))


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    forum = og(html, "site_name") or og(html, "title")
    if forum:
        ex.community = fb.field(forum, forum, "forum name", 0.7)
    g = _GENERATOR.search(html)
    if g and not ex.title.is_known:
        t = title_tag(html)
        if t:
            ex.title = fb.field(t, t, f"forum topic ({g.group(1)})", 0.6)
    return ex
