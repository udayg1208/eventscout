"""Phase 8D — Public Social Discovery tests. Fixtures only, NO network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.social import (
    WEIGHTS,
    InMemorySocialStore,
    SocialDiscoveryEngine,
    blog,
    discord,
    forum,
    github,
    linkedin,
    notion,
    safety_check,
    score,
    telegram,
)
from app.discovery.social.models import FieldStatus, SocialPlatform

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def og(title, extra=""):
    return f'<meta property="og:title" content="{title}">{extra}'


LINKEDIN = (
    "<html><head>"
    + og("GDG Bangalore")
    + '<meta property="og:site_name" content="GDG Bangalore"></head><body>'
    '<script type="application/ld+json">{"@type":"Event","name":"DevFest Bangalore 2026",'
    '"startDate":"2026-11-01","location":{"name":"Bangalore"}}</script>'
    "AI and Python meetup. Register at https://lu.ma/devfest</body></html>"
)
GITHUB = (
    "<html><head>"
    + og("gdg-india/events")
    + "</head><body>Kubernetes and Go hackathon.</body></html>"
)
NOTION = (
    "<html><head>" + og("PyDelhi Workshops") + "</head><body>"
    "Upcoming Python workshops and hackathons in Delhi, India. Schedule 2026-08-15.</body></html>"
)
TELEGRAM = "<html><head>" + og("GDG India") + "</head><body>channel preview</body></html>"
DISCORD = (
    "<html><head>"
    + og("FOSS United Community")
    + "</head><body>open source community</body></html>"
)
BLOG = (
    '<html><head><meta name="author" content="Jane Dev">'
    + og("Building with Rust in India")
    + "</head><body>Rust meetup writeup. Published Jan 5, 2026.</body></html>"
)
FORUM = (
    '<html><head><meta name="generator" content="Discourse 3.1">'
    + og("Django India Forum")
    + "</head><title>DjangoCon India meetup</title><body>Python event thread.</body></html>"
)


# --------------------------- per-platform extraction ---------------------------


def test_linkedin_public_extract():
    assert linkedin.matches("https://www.linkedin.com/company/gdg/posts/x", LINKEDIN)
    ex = linkedin.extract("https://www.linkedin.com/company/gdg/posts/x", LINKEDIN, now=NOW)
    assert ex.platform is SocialPlatform.LINKEDIN
    assert ex.title.value == "DevFest Bangalore 2026" and ex.date.value == "2026-11-01"
    assert ex.location.value == "Bangalore" and "Python" in ex.technologies.value
    assert ex.registration_url.value == "https://lu.ma/devfest"
    assert ex.organizer.is_known


def test_github_extract_org():
    assert github.matches("https://github.com/gdg-india/events/discussions/5", GITHUB)
    ex = github.extract("https://github.com/gdg-india/events/discussions/5", GITHUB, now=NOW)
    assert ex.organizer.value == "gdg-india" and "Kubernetes" in ex.technologies.value


def test_discord_public_invite_only():
    assert discord.matches("https://discord.gg/fossunited", DISCORD)
    ex = discord.extract("https://discord.gg/fossunited", DISCORD, now=NOW)
    assert ex.community.value == "FOSS United Community"


def test_telegram_public_channel():
    assert telegram.matches("https://t.me/gdgindia", TELEGRAM)
    ex = telegram.extract("https://t.me/gdgindia", TELEGRAM, now=NOW)
    assert ex.community.value == "GDG India"


def test_notion_public_page():
    assert notion.matches("https://pydelhi.notion.site/workshops", NOTION)
    ex = notion.extract("https://pydelhi.notion.site/workshops", NOTION, now=NOW)
    assert ex.title.is_known and ex.location.value == "Delhi"


def test_blog_author_and_tech():
    assert blog.matches("https://janedev.substack.com/p/rust", BLOG)
    ex = blog.extract("https://janedev.substack.com/p/rust", BLOG, now=NOW)
    assert ex.organizer.value == "Jane Dev" and "Rust" in ex.technologies.value


def test_forum_detects_via_generator():
    assert forum.matches("https://forum.djangoindia.org/t/meetup/12", FORUM)
    ex = forum.extract("https://forum.djangoindia.org/t/meetup/12", FORUM, now=NOW)
    assert ex.community.value == "Django India Forum"


# --------------------------- provenance ---------------------------


def test_provenance_present_and_never_fabricated():
    ex = linkedin.extract("https://www.linkedin.com/company/gdg/posts/x", LINKEDIN, now=NOW)
    # every KNOWN field carries provenance stamped at NOW
    for name, f in ex.known_fields().items():
        assert f.provenance is not None, name
        assert f.provenance.source_snippet and f.provenance.timestamp == NOW
        assert 0.0 < f.provenance.confidence <= 1.0
    # a field with no evidence stays UNKNOWN, not guessed
    bare = github.extract(
        "https://github.com/features", "<html><body>Features</body></html>", now=NOW
    )
    assert bare.date.status is FieldStatus.UNKNOWN and bare.date.value is None
    assert bare.organizer.status is FieldStatus.UNKNOWN  # 'features' is not an org


# --------------------------- scoring ---------------------------


def test_scoring_explainable_and_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    ex = linkedin.extract("https://www.linkedin.com/company/gdg/posts/x", LINKEDIN, now=NOW)
    p = score(ex)
    # total is the weighted sum of factors (within rounding of the reported values)
    assert abs(p.total - sum(WEIGHTS[k] * v for k, v in p.factors.items())) < 1e-3
    assert p.factors["organizer_reputation"] == 1.0  # GDG is a known org
    assert p.factors["structured_data"] == 1.0  # JSON-LD present
    assert p.reasons


# --------------------------- safety ---------------------------


def test_safety_rejects_login_wall_and_offtopic():
    ex = linkedin.extract("https://x", "<html><body>tech</body></html>", now=NOW)
    walled = "<html><body>Please log in to continue viewing.</body></html>"
    ok, reasons = safety_check("https://linkedin.com/x", walled, ex)
    assert ok is False and any("login" in r for r in reasons)
    gambling = "<html><body>Best online casino betting tonight.</body></html>"
    ok2, reasons2 = safety_check("https://x", gambling, ex)
    assert ok2 is False and any("off-topic" in r for r in reasons2)


# --------------------------- engine (end-to-end) ---------------------------


def test_engine_discovers_public_pages_and_rejects_walls():
    inbox = InMemoryDiscoveryInbox()
    store = InMemorySocialStore()
    pages = [
        ("https://www.linkedin.com/company/gdg/posts/x", LINKEDIN),
        ("https://github.com/gdg-india/events", GITHUB),
        ("https://pydelhi.notion.site/workshops", NOTION),
        ("https://t.me/gdgindia", TELEGRAM),
        ("https://discord.gg/fossunited", DISCORD),
        ("https://janedev.substack.com/p/rust", BLOG),
        # rejected: login wall + gambling
        (
            "https://www.linkedin.com/feed/update/x",
            "<html><body>Sign in to view this post.</body></html>",
        ),
        (
            "https://discord.gg/casino",
            "<html><head>"
            + og("Casino Night")
            + "</head><body>online casino betting</body></html>",
        ),
        # unmatched (not a supported platform)
        ("https://random.example.com/x", "<html>nothing here</html>"),
    ]
    report = run(SocialDiscoveryEngine(inbox, store=store, clock=lambda: NOW).discover(pages))

    assert report.processed == 9 and report.matched == 8 and report.unmatched == 1
    assert report.rejected == 2 and report.inserted == 6
    assert report.by_platform.get("linkedin") == 2  # one accepted, one login-walled
    # everything in the inbox is social-sourced, status NEW
    stored = run(inbox.list(limit=20))
    assert len(stored) == 6 and all(c.discovered_by == "social" for c in stored)
    assert {c.classification for c in stored} >= {"linkedin", "github", "notion", "discord"}
    # the LinkedIn structured event scores highest
    linkedin_cand = next(c for c in stored if c.classification == "linkedin")
    assert linkedin_cand.city == "Bangalore" and linkedin_cand.discovery_confidence >= 0.7
    # provenance persisted
    rec = run(store.get("https://www.linkedin.com/company/gdg/posts/x"))
    assert (
        rec is not None and rec.extraction["fields"]["title"]["value"] == "DevFest Bangalore 2026"
    )
