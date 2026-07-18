"""GitHub public-content extractor (Phase 8D).

Handles public GitHub pages — Discussions, Releases, Organizations, READMEs, event/community
repositories — and extracts event announcements from their title/body. Organizer/community are the
GitHub org. Public content only (no auth).
"""

from __future__ import annotations

import re
from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.GITHUB
_ORG = re.compile(r"github\.com/([\w.\-]+)", re.I)
_KINDS = ("/discussions", "/releases", "/orgs/", "/blob/", "readme", "wiki")
_NON_ORG = {"features", "about", "login", "marketplace", "explore", "topics", "sponsors", "orgs"}


def matches(url: str, html: str) -> bool:
    return "github.com" in url.lower()


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    m = _ORG.search(url)
    if m and m.group(1).lower() not in _NON_ORG:
        org = m.group(1)
        ex.organizer = fb.field(org, f"github.com/{org}", "GitHub organization", 0.8)
        ex.community = fb.field(org, f"github.com/{org}", "GitHub community", 0.7, inferred=True)
    elif og(html, "site_name"):
        ex.organizer = fb.field(og(html, "site_name"), og(html, "site_name"), "og:site_name", 0.6)
    return ex
