"""Phase 10C live demonstration: the Organizer & Community Intelligence Engine (fixtures).

Walks the full flow on fixture pages: discover an organizer → merge its aliases into one identity →
identify the chapter family → find calendars/GitHub/Discord/LinkedIn → expand the ecosystem graph →
score confidence → classify health → predict the next recurring occurrence. Then ingests a sibling
chapter and a university society to show identity resolution and community linking. Deterministic;
no browser, no LLM, no network; the output is an Organizer Graph, not Event objects.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.organizers import OrganizerIntelligenceEngine, RelationType  # noqa: E402

NOW = datetime(2026, 7, 16, tzinfo=UTC)

GDG_BLR = (
    '<html><head><meta property="og:site_name" content="GDG Bangalore">'
    '<link rel="alternate" type="application/rss+xml" href="https://gdgblr.dev/feed.xml"></head>'
    "<body><h1>GDG Bangalore</h1>Google Developer Group Bangalore runs DevFest, Build with AI and "
    "monthly meetups. Python, Kubernetes, AI, Cloud. Sponsored by Google. Venue: Bangalore."
    '<a href="https://github.com/gdg-bangalore">GitHub</a>'
    '<a href="https://discord.gg/gdgblr">Discord</a>'
    '<a href="https://t.me/gdgblr">Telegram</a>'
    '<a href="https://linkedin.com/company/gdg-bangalore">LinkedIn</a>'
    '<a href="https://calendar.google.com/calendar/gdgblr.ics">Calendar</a></body></html>'
)
GDG_BLR_ALIAS = (
    "<html><body><h1>Google Developers Group Bangalore</h1>DevFest 2026, cloud & AI community in "
    "Bangalore. Hosted at Bangalore.</body></html>"
)
GDG_DELHI = (
    "<html><body><h1>GDG Delhi</h1>Google Developer Group Delhi. DevFest. Python. Delhi."
    "</body></html>"
)
IEEE_MUJ = (
    "<html><body><h1>IEEE MUJ</h1>IEEE Student Branch at Manipal University Jaipur. Robotics and "
    "AI. Monthly workshops.</body></html>"
)
IEEE_MUJ_ALIAS = "<html><body><h1>IEEE Student Branch MUJ</h1>MUJ. AI and IoT.</body></html>"


def main() -> None:
    print("=== Phase 10C — Organizer & Community Intelligence Engine (fixtures, no network) ===\n")
    eng = OrganizerIntelligenceEngine(clock=lambda: NOW)

    print("STEP 1 · discover organizer + STEP 2 · merge aliases")
    gid = eng.ingest("https://gdgblr.dev/", GDG_BLR)
    gid_alias = eng.ingest("https://gdgblr.dev/about", GDG_BLR_ALIAS)
    print(f"    'GDG Bangalore'  → {gid}")
    print(
        f"    'Google Developers Group Bangalore' → {gid_alias}   (same node: {gid == gid_alias})"
    )

    prof = eng.profile(gid)
    print("\nSTEP 3 · identify chapter")
    print(
        f"    chapter={prof.get('chapter')}  community={prof.get('community')}  "
        f"parent={prof.get('parent_org')}  type={prof.node_type.value}"
    )

    print("\nSTEP 4-7 · find calendars / GitHub / Discord / LinkedIn")
    print(f"    calendars: {prof.get('calendars')}")
    print(f"    feeds    : {prof.get('feeds')}")
    for platform, url in (prof.get("social_pages") or {}).items():
        print(f"    {platform:9s}: {url}")

    print("\nSTEP 8 · predict recurring series")
    eng.record_events(gid, [NOW - timedelta(days=64), NOW - timedelta(days=33)])
    pred = eng.predict(gid)
    print(f"    series={prof.get('series')}")
    print(f"    confidence={eng.confidence(gid).total}  health={eng.health(gid).value}")
    print(f"    prediction: [{pred.probability}] {pred.reason}")

    print("\nSTEP 9 · expand graph (one organizer → ecosystem subgraph)")
    print(f"    graph: {eng.graph.as_dict()['counts']}")
    for e in eng.graph.edges.values():
        if e.source == gid:
            tgt = eng.graph.nodes.get(e.target)
            print(
                f"      {gid.split(':')[1]:28s} --{e.relation.value:13s}--> "
                f"[{tgt.type.value if tgt else '?'}] {e.target}"
            )

    print("\n--- identity resolution + community linking across organizers ---")
    eng.ingest("https://gdgdelhi.dev/", GDG_DELHI)
    im = eng.ingest("https://ieeemuj.org/", IEEE_MUJ)
    im2 = eng.ingest("https://ieeemuj.org/sb", IEEE_MUJ_ALIAS)
    print(f"    IEEE MUJ aliases merged: {im == im2}")
    print(f"    organizers discovered: {len(eng.organizer_ids())}")
    eng.link_similar(threshold=0.2)
    sims = [
        e
        for e in eng.graph.edges.values()
        if e.relation in (RelationType.SAME_COMMUNITY, RelationType.SAME_SERIES)
    ]
    for e in sims:
        print(f"      {e.source} ~~{e.relation.value}~~ {e.target}  ({e.reason})")
    print(f"\n    community graph: {eng.community_graph().as_dict()['counts']['nodes']} nodes")
    print(f"    series graph   : {eng.series_graph().as_dict()['counts']['nodes']} nodes")

    print("\n  ✔ Organizer Graph, not Event objects; provenance-bearing; no browser/LLM/network")


if __name__ == "__main__":
    main()
