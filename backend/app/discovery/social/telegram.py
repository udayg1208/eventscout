"""Telegram public-channel extractor (Phase 8D).

Handles ONLY public Telegram channel / invite landing pages (t.me/… , t.me/s/…) — the public web
preview Telegram renders (channel name + description + public post snippets). It NEVER accesses
private groups. The channel becomes a community candidate.
"""

from __future__ import annotations

from datetime import datetime

from app.discovery.social.extractor import FieldBuilder, build_common, og
from app.discovery.social.models import SocialExtraction, SocialPlatform

PLATFORM = SocialPlatform.TELEGRAM


def matches(url: str, html: str) -> bool:
    low = url.lower()
    return "t.me/" in low or "telegram.me/" in low


def extract(url: str, html: str, *, now: datetime) -> SocialExtraction:
    ex = SocialExtraction(url=url, platform=PLATFORM, **build_common(url, html, now=now))
    fb = FieldBuilder(now)
    channel = og(html, "title")
    if channel:
        ex.community = fb.field(channel, channel, "Telegram public channel", 0.75)
        if not ex.title.is_known:
            ex.title = fb.field(channel, channel, "Telegram channel name", 0.6, inferred=True)
    return ex
