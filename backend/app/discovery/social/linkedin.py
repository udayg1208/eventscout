"""LinkedIn public-page extractor (Phase 8D).

Handles ONLY public LinkedIn pages — company pages, public event posts, creator posts, public
articles (Pulse). Never a private profile, never behind the auth wall (the shared safety gate
rejects login-walled pages). Organizer/community come from the company slug or `og:site_name`.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.LINKEDIN
_COMPANY = re.compile(r"linkedin\.com/(?:company|school)/([\w.\-]+)", re.I)
_PUBLIC_PATHS = ("/company/", "/school/", "/posts/", "/events/", "/pulse/", "/feed/update")


def matches(url: str, html: str) -> bool:
    low = url.lower()
    return "linkedin.com" in low and any(p in low for p in _PUBLIC_PATHS)


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    m = _COMPANY.search(url)
    org = (m.group(1).replace("-", " ").title() if m else None) or og(html, "site_name")
    if org:
        ex.organizer = fb.field(org, org, "LinkedIn company/site name", 0.8)
        ex.community = fb.field(org, org, "LinkedIn organization", 0.7, inferred=True)
    return ex
