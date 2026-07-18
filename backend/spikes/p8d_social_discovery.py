"""Phase 8D live demonstration: public social & community discovery from HTML fixtures.

Feeds public-page HTML fixtures (LinkedIn company announcement → GitHub Discussion → Notion meetup
page → Telegram public channel → Discord invite → a blog + a forum, plus login-walled / off-topic
pages that must be rejected) through the Social Discovery Engine and prints extracted events (with
provenance), priority scores, and the Discovery Inbox growth. Public content only — no login, no
browser, no network, no LLM. Output stops at the Discovery Inbox.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.social import (  # noqa: E402
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

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
_PLATFORMS = [linkedin, github, discord, telegram, notion, blog, forum]


def _og(t, extra=""):
    return f'<meta property="og:title" content="{t}">{extra}'


PAGES = [
    (
        "https://www.linkedin.com/company/gdg-bangalore/posts/devfest-2026",
        "<html><head>"
        + _og("GDG Bangalore")
        + '<meta property="og:site_name" content="GDG Bangalore">'
        '</head><body><script type="application/ld+json">{"@type":"Event",'
        '"name":"DevFest Bangalore 2026","startDate":"2026-11-01",'
        '"location":{"name":"Bangalore"}}</script>'
        "AI, Python and Kubernetes talks. Register: https://lu.ma/devfest-blr</body></html>",
    ),
    (
        "https://github.com/gdg-india/devfest/discussions/42",
        "<html><head>" + _og("gdg-india/devfest") + "</head><body>"
        "DevFest 2026 hackathon — Go, React and DevOps tracks. RSVP inside.</body></html>",
    ),
    (
        "https://pydelhi.notion.site/meetups",
        "<html><head>"
        + _og("PyDelhi Meetups")
        + "</head><body>Monthly Python workshops and hackathons in Delhi, India. Next: 2026-08-15."
        '<a href="https://calendar.google.com/calendar/ical/pydelhi/public/basic.ics">Calendar</a></body></html>',
    ),
    (
        "https://t.me/gdgindia",
        "<html><head>"
        + _og("GDG India")
        + '<meta property="og:description" content="AI & cloud community events across India">'
        "</head><body>public channel preview</body></html>",
    ),
    (
        "https://discord.gg/fossunited",
        "<html><head>"
        + _og("FOSS United — India")
        + "</head><body>Open source community. Rust and Linux.</body></html>",
    ),
    (
        "https://rootconf.substack.com/p/rootconf-2026",
        '<html><head><meta name="author" content="Hasgeek">'
        + _og("Rootconf 2026 — DevOps")
        + "</head><body>DevOps and Kubernetes conference, Bangalore India. Published Feb 2, 2026."
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml"></body></html>',
    ),
    # rejected examples
    (
        "https://www.linkedin.com/feed/update/private-post",
        "<html><body>Sign in to view this event and 2,300 others.</body></html>",
    ),
    (
        "https://discord.gg/bet-now",
        "<html><head>"
        + _og("Betting Lounge")
        + "</head><body>Online casino and betting.</body></html>",
    ),
]


def _kv(f):
    return f"{f.value}" if f.is_known else "UNKNOWN"


async def main() -> None:
    print("=== Phase 8D — Public Social & Community Discovery (fixtures, no network) ===\n")
    print("PIPELINE  public HTML → platform extractor → safety gate → priority → Discovery Inbox\n")

    inbox = InMemoryDiscoveryInbox()
    store = InMemorySocialStore()
    engine = SocialDiscoveryEngine(inbox, store=store)

    for url, html in PAGES:
        mod = next((m for m in _PLATFORMS if m.matches(url, html)), None)
        if mod is None:
            print(f"● UNMATCHED  {url}")
            continue
        ex = mod.extract(url, html, now=NOW)
        passed, reasons = safety_check(url, html, ex)
        print(f"● {mod.PLATFORM.value:9s} {url[:52]}")
        if not passed:
            print(f"    REJECTED: {reasons[0]}")
            continue
        pri = score(ex)
        print(
            f"    title={_kv(ex.title)} | date={_kv(ex.date)} | city={_kv(ex.location)} | "
            f"org={_kv(ex.organizer) if ex.organizer.is_known else _kv(ex.community)}"
        )
        print(
            f"    tech={ex.technologies.value if ex.technologies.is_known else '—'}  "
            f"priority={pri.total:.2f}"
        )

    print("\n=== ENGINE RUN (discover all, upsert to inbox) ===")
    report = await engine.discover(PAGES)
    print(
        f"  processed={report.processed}  matched={report.matched}  unmatched={report.unmatched}  "
        f"rejected={report.rejected}"
    )
    print(f"  by platform: {report.by_platform}")
    print(f"  extracted events={report.extracted_events}  inserted={report.inserted}")
    for r in report.rejections:
        print(f"    REJECTED [{r['platform']}]: {r['reasons'][0]}")

    print("\n=== DISCOVERY INBOX (all discovered_by=social, status=NEW) ===")
    for c in await inbox.list(limit=20):
        print(
            f"    [{c.classification:9s}] {c.domain:16s} conf={c.discovery_confidence:.2f} "
            f"city={c.city or '-':10s} :: {(c.title or '')[:32]}"
        )

    print("\n=== PROVENANCE SAMPLE ===")
    rec = await store.get("https://www.linkedin.com/company/gdg-bangalore/posts/devfest-2026")
    for name in ("title", "date", "location", "registration_url"):
        f = rec.extraction["fields"][name]
        if f["provenance"]:
            p = f["provenance"]
            print(f"    {name:16s} = {f['value']!r}  ({p['reason']} @{p['confidence']})")

    print("\n  ✔ public content only — no login, no browser; stops at the Discovery Inbox")


if __name__ == "__main__":
    asyncio.run(main())
