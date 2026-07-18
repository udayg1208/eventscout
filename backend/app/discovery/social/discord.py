"""Discord public-invite extractor (Phase 8D).

Handles ONLY the PUBLIC invite landing page (discord.gg/… or discord.com/invite/…) — the metadata
Discord itself renders for an invite (server name + description). It NEVER joins a server and NEVER
accesses private channels. The server becomes a community node/candidate to inspect.
"""

from __future__ import annotations

from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.DISCORD


def matches(url: str, html: str) -> bool:
    low = url.lower()
    return "discord.gg/" in low or "discord.com/invite/" in low


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    server = og(html, "title")
    if server:
        ex.community = fb.field(server, server, "Discord server (invite landing)", 0.75)
        if not ex.title.is_known:
            ex.title = fb.field(server, server, "Discord server name", 0.6, inferred=True)
    return ex
