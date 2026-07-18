"""Blog-platform extractor (Phase 8D).

Handles public blog posts on Medium, Dev.to, Hashnode, Substack, WordPress, and Blogger — extracting
title/date/technology and the author/publication as organizer, plus the platform RSS feed. Public
content only.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.BLOG
_HOSTS = re.compile(
    r"medium\.com|dev\.to|\.hashnode\.dev|substack\.com|wordpress\.com|blogspot\.|blogger\.com",
    re.I,
)
_AUTHOR = re.compile(r'<meta\b[^>]*\bname=["\']author["\'][^>]*\bcontent=["\']([^"\']+)["\']', re.I)


def matches(url: str, html: str) -> bool:
    return bool(_HOSTS.search(url))


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    m = _AUTHOR.search(html)
    author = (m.group(1) if m else None) or og(html, "site_name")
    if author:
        ex.organizer = fb.field(author, author, "blog author / publication", 0.7)
    return ex
