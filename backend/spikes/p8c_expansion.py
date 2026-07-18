"""Phase 8C live demonstration: autonomous graph expansion from a seed page.

Uses a StaticFetcher mock organizer site (deterministic, reproducible — swap in HttpxFetcher to hit
the real web) so the whole expansion mechanic is visible: seed → recursive crawl → graph of pages/
domains/feeds/calendars/GitHub/Notion/Discord/Telegram/blogs → Discovery Inbox growth → an
incremental second crawl that skips everything via checkpoints. Shows graph stats, frontier growth,
dedup, crawl budget, and checkpoints. HTML only, no browser, no LLM. Stops at the Discovery Inbox.
"""

from __future__ import annotations

import asyncio
import logging

logging.disable(logging.CRITICAL)

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.expansion import (  # noqa: E402
    CrawlBudgetConfig,
    ExpansionEngine,
    InMemoryCheckpointStore,
    InMemoryExpansionStore,
    ScopeConfig,
)
from app.discovery.fetch import FetchResult, StaticFetcher  # noqa: E402


def r(url, body, ct="text/html", status=200):
    return FetchResult(url=url, status=status, content_type=ct, text=body)


# A mock organizer site: home → events / community / two chapter pages, each rich in sources.
HOME = """<html><head>
<link rel="alternate" type="application/rss+xml" href="/blog/feed.xml">
</head><body>
<h1>GDG India</h1>
<a href="/events">Upcoming Events</a>
<a href="/community">Community</a>
<a href="/chapters/bangalore">Bangalore Chapter</a>
<a href="/chapters/delhi">Delhi Chapter</a>
<a href="https://github.com/gdg-india">GitHub</a>
<a href="https://gdg-india.notion.site/handbook">Notion Handbook</a>
<a href="https://discord.gg/gdgindia">Discord</a>
<a href="https://t.me/gdgindia">Telegram</a>
<a href="https://gdgindia.substack.com">Newsletter</a>
<a href="https://twitter.com/gdgindia">Twitter</a>
</body></html>"""

EVENTS = """<html><body>
<h1>Events</h1> Python, AI and Kubernetes meetups across Bangalore, India.
<a href="https://calendar.google.com/calendar/ical/gdg/public/basic.ics">Add to calendar</a>
<script type="application/ld+json">{"@type":"Event","name":"DevFest Bangalore 2026"}</script>
<a href="/chapters/bangalore">Bangalore</a>
</body></html>"""

COMMUNITY = """<html><body>
<h1>Community</h1> Our GDG chapters and user groups.
<a href="https://www.meetup.com/gdg-bangalore/">Meetup: GDG Bangalore</a>
<a href="/chapters/bangalore">Bangalore chapter</a>
</body></html>"""

BLR = """<html><head>
<link rel="alternate" type="application/rss+xml" href="/chapters/bangalore/feed"></head>
<body><h1>GDG Bangalore</h1> AI and Python events in Bangalore, India.
<a href="https://github.com/gdg-bangalore">Chapter GitHub</a>
<script type="application/ld+json">{"@type":"Event","name":"AI Meetup"}</script></body></html>"""

DELHI = """<html><body><h1>GDG Delhi</h1> DevOps meetups in Delhi, India.
<a href="https://t.me/gdgdelhi">Telegram</a></body></html>"""

MEETUP = """<html><body>GDG Bangalore on Meetup — 4,000 members.
<script type="application/ld+json">{"@type":"Event","name":"Kotlin Night"}</script></body></html>"""

SITE = {
    "https://gdg.org/robots.txt": r("https://gdg.org/robots.txt", "", "text/plain"),
    "https://gdg.org/": r("https://gdg.org/", HOME),
    "https://gdg.org/events": r("https://gdg.org/events", EVENTS),
    "https://gdg.org/community": r("https://gdg.org/community", COMMUNITY),
    "https://gdg.org/chapters/bangalore": r("https://gdg.org/chapters/bangalore", BLR),
    "https://gdg.org/chapters/delhi": r("https://gdg.org/chapters/delhi", DELHI),
    "https://www.meetup.com/robots.txt": r("https://www.meetup.com/robots.txt", "", "text/plain"),
    # both slash variants — normalize_url drops the trailing slash on non-root paths
    "https://www.meetup.com/gdg-bangalore/": r("https://www.meetup.com/gdg-bangalore/", MEETUP),
    "https://www.meetup.com/gdg-bangalore": r("https://www.meetup.com/gdg-bangalore", MEETUP),
}


async def main() -> None:
    print("=== Phase 8C — Autonomous Web Expansion (mock site, deterministic, HTML-only) ===\n")
    inbox = InMemoryDiscoveryInbox()
    checkpoint = InMemoryCheckpointStore()
    store = InMemoryExpansionStore()
    engine = ExpansionEngine(
        StaticFetcher(SITE),
        inbox,
        checkpoint=checkpoint,
        store=store,
        scope_config=ScopeConfig(max_depth=2),
        budget_config=CrawlBudgetConfig(max_pages=25, max_depth=2),
    )

    print("SEED  https://gdg.org/")
    print("PIPELINE  fetch → extract → graph → dedupe → priority → frontier → Discovery Inbox\n")
    rep = await engine.expand(["https://gdg.org/"], max_pages=25)

    print("=== CRAWL ===")
    print(f"  pages fetched={rep.pages_fetched}  skipped={rep.pages_skipped}")
    print(f"  frontier: {rep.frontier}")
    cp_count = await checkpoint.count()
    print(f"  stopped domains: {rep.stopped_domains or '(none)'}   checkpoints={cp_count}")

    print("\n=== DISCOVERED SOURCES ===")
    print(
        f"  feeds={rep.feeds_found}  calendars={rep.calendars_found}  github={rep.github_found}  "
        f"notion={rep.notion_found}  discord={rep.discord_found}  telegram={rep.telegram_found}  "
        f"blogs={rep.blogs_found}"
    )

    print("\n=== DISCOVERY GRAPH ===")
    print(
        f"  nodes={sum(rep.nodes_by_type.values())}  edges={sum(rep.edges_by_type.values())}  "
        f"(added: {rep.nodes_added} nodes / {rep.edges_added} edges)"
    )
    print(f"  nodes by type: {rep.nodes_by_type}")
    print(f"  edges by type: {rep.edges_by_type}")

    print("\n=== DISCOVERY INBOX (all discovered_by=expansion, status=NEW) ===")
    print(f"  candidates inserted={rep.candidates_inserted}  inbox total={await inbox.count()}")
    for c in await inbox.list(limit=12):
        cls = c.classification or c.feed_type.value
        print(f"    [{cls:10s}] {c.domain:18s} {c.url[:46]}")

    print("\n=== INCREMENTAL SECOND CRAWL (checkpoints → skip recently-crawled) ===")
    rep2 = await engine.expand(["https://gdg.org/"], max_pages=25)
    print(
        f"  pages fetched={rep2.pages_fetched}  skipped={rep2.pages_skipped}  "
        f"inbox still {await inbox.count()} (dedup: no new nodes churned)"
    )
    reloaded = await store.load_graph()
    print(
        f"  graph persisted + reloaded: {reloaded.stats()['total_nodes']} nodes, "
        f"{reloaded.stats()['total_edges']} edges"
    )
    print("\n  ✔ stops at the Discovery Inbox — no onboarding, no promotion, no catalog write")


if __name__ == "__main__":
    asyncio.run(main())
