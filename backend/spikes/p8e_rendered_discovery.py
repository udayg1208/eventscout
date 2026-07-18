"""Phase 8E live demonstration: AI rendered discovery & hidden-data extraction from HTML fixtures.

The headline scenario: a Next.js events page whose served bytes contain NO event HTML — the 250
events live inside `__NEXT_DATA__`, and the page fetches more from a hidden `/api/events` endpoint.
The engine extracts the hydration blob, counts the events, discovers the hidden API (from JS call
sites — never calling it), reasons about whether the site can become a provider, and drops
candidates into the Discovery Inbox. Also demonstrates Nuxt/Vue `window.__NUXT__` state, an
Apollo/GraphQL-cache page, an ICS-feed-only page, and a marketing page correctly judged non-event.

Fixtures only — no browser, no JS execution, no network, no LLM. Output stops at the Inbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.frameworks import detect_framework  # noqa: E402
from app.discovery.rendered import (  # noqa: E402
    InMemoryRenderedStore,
    MockAIReasoner,
    RenderedDiscoveryEngine,
    RenderedPage,
    collect_hydration,
    discover_endpoints,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def next_js_events_page() -> str:
    """A Next.js page: 250 events in __NEXT_DATA__ + a hidden /api/events the page fetches."""
    events = [
        {
            "title": f"React India Meetup #{i}",
            "start_date": f"2026-08-{(i % 28) + 1:02d}",
            "url": f"/events/react-india-{i}",  # per-event detail URL (must NOT flood endpoints)
        }
        for i in range(250)
    ]
    blob = json.dumps(
        {"props": {"pageProps": {"events": events, "city": "Bangalore, India"}}, "buildId": "x9"}
    )
    return (
        "<!doctype html><html><head><title>Tech Events — India</title></head><body>"
        '<div id="__next"></div>'  # ← the app renders client-side; no event HTML in the bytes
        f'<script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        "<script>"
        'const API = "/api/events?city=bangalore&page=1";'  # the hidden event API
        "fetch(API).then(r => r.json());"
        'fetch("https://api.example.com/graphql", {method:"POST", body:"{ events { id } }"});'
        "// React, Next.js, Python and Kubernetes talks"
        "</script></body></html>"
    )


NUXT_PAGE = (
    "<!doctype html><html><head><title>VueConf India</title></head><body>"
    '<script>window.__NUXT__ = {"data":[{"events":['
    '{"title":"VueConf India 2026","start_at":"2026-09-12","city":"Pune"},'
    '{"title":"Nuxt Nation Meetup","start_at":"2026-09-20"}]}]};</script>'
    '<script>axios.get("/api/v2/events?tech=vue");</script></body></html>'
)

APOLLO_PAGE = (
    "<!doctype html><html><head><title>GraphQL Summit</title></head><body>"
    '<script>window.__APOLLO_STATE__ = {"ROOT_QUERY":{"conferences":['
    '{"__typename":"Event","name":"GraphQL Summit Bangalore","start_date":"2026-10-01"}]}};'
    'const q = fetch("https://summit.dev/graphql");</script></body></html>'
)

ICS_ONLY_PAGE = (
    "<!doctype html><html><head><title>PyData Calendar</title></head><body>"
    "Subscribe to our events calendar."
    '<script>const cal = "https://pydata.org/events.ics"; fetch(cal);</script></body></html>'
)

MARKETING_PAGE = (
    "<!doctype html><html><head><title>Acme Corp</title></head><body>"
    "<h1>We build cloud software.</h1><p>Trusted by teams worldwide. Contact sales.</p>"
    "</body></html>"
)

PAGES = [
    RenderedPage("https://techevents.in/events", next_js_events_page()),
    RenderedPage("https://vueconf.in/", NUXT_PAGE),
    RenderedPage("https://summit.dev/graphql-summit", APOLLO_PAGE),
    RenderedPage("https://pydata.org/calendar", ICS_ONLY_PAGE),
    RenderedPage("https://acme.example/home", MARKETING_PAGE),
]


async def main() -> None:
    print(
        "=== Phase 8E — AI Rendered Discovery & Hidden Data Extraction (fixtures, no network) ==="
    )
    print("PIPELINE  SPA bytes → hydration blobs + hidden APIs → AI reasoning → Discovery Inbox\n")

    reasoner = MockAIReasoner()
    for page in PAGES:
        fw = detect_framework(page.html)
        hydration = collect_hydration(page.html, page.scripts)
        endpoints = discover_endpoints(page.html, page.scripts, base=page.url)
        pc = reasoner.reason(
            page.url, framework=fw.name, hydration=hydration, endpoints=endpoints, html=page.html
        )
        print(f"● {page.url}")
        print(f"    framework : {fw.name or '—'}")
        for h in hydration:
            evt = f"{h.event_count} events" if h.event_count else "no events"
            title = f" e.g. '{h.sample_title}'" if h.sample_title else ""
            print(f"    hydration : {h.source:20s} {evt}{title}")
        for e in endpoints:
            flag = " ★ event API" if e.event_relevant else ""
            print(f"    endpoint  : [{e.kind.value:7s}] {e.url}  (via {e.source}){flag}")
        verdict = "EVENT SOURCE" if pc.is_event_source else "not an event source"
        print(
            f"    VERDICT   : {verdict} | type={pc.recommended_provider_type} | "
            f"conf={pc.confidence}"
        )
        for ev in pc.evidence:
            print(f"                  • {ev}")
        if pc.missing_fields:
            print(f"    missing   : {', '.join(pc.missing_fields)} (needs per-event parse)")
        print()

    print("=== ENGINE RUN → Discovery Inbox ===")
    inbox = InMemoryDiscoveryInbox()
    store = InMemoryRenderedStore()
    engine = RenderedDiscoveryEngine(inbox, store=store, clock=lambda: NOW)
    report = await engine.discover(PAGES)
    print(
        f"  pages={report.pages}  frameworks={report.frameworks}  "
        f"events_found={report.events_found}  hidden_event_apis={report.event_apis}"
    )
    print(
        f"  provider_candidates={report.provider_candidates}  skipped(non-event)={report.skipped}  "
        f"by_type={report.by_provider_type}"
    )
    print(f"  inbox: inserted={report.candidates_inserted}  updated={report.candidates_updated}\n")

    print("=== DISCOVERY INBOX (all discovered_by=rendered, status=NEW — nothing onboarded) ===")
    for c in await inbox.list(limit=30):
        conf = f"{c.discovery_confidence:.2f}" if c.discovery_confidence is not None else " -  "
        evts = f"{c.embedded_event_count:>3}ev" if c.embedded_event_count else "  -  "
        print(
            f"    [{(c.classification or '-'):10s}] {c.feed_type.value:14s} conf={conf} "
            f"{evts}  {c.url}"
        )

    print("\n=== THE HIDDEN-API STORY ===")
    print("  The Next.js page shipped ZERO event HTML — 250 events lived in __NEXT_DATA__, and the")
    print("  page fetched a hidden /api/events endpoint. We extracted the 250 hydrated events AND")
    print(
        "  recorded the API as a JSON_API candidate: that endpoint likely fronts the FULL dataset"
    )
    print(
        "  (thousands), reachable in one call instead of crawling HTML forever. It is recorded as"
    )
    print("  a lead only — never called. A human reviews the inbox before anything is onboarded.")
    print("\n  ✔ HTML/JS/JSON only — no browser, no JS execution, no network; stops at the inbox")


if __name__ == "__main__":
    asyncio.run(main())
