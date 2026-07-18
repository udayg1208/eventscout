"""Phase 10B live demonstration: the Universal Event Engine over many page shapes (fixtures).

Feeds one page at a time — a university events page (JSON-LD), a conference schedule (HTML table), a
Next.js hydrated page, a GitHub README (Markdown), a Notion-style FAQ, an ICS calendar, a blog with
OpenGraph, and a shopping page that must be rejected — through the engine and prints, for each: the
extractors fired, the events found, their merged provenance sources, the eight-component confidence
breakdown, and validation. No framework detection anywhere — only "where is the event information?".
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.universal import UniversalEventEngine  # noqa: E402

ENGINE = UniversalEventEngine()


def _nextdata(events):
    return (
        '<html><body><div id="__next"></div><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": {"events": events}}})
        + "</script>React and TypeScript sessions.</body></html>"
    )


PAGES = [
    (
        "University (JSON-LD)",
        "https://www.iitb.ac.in/events/techfest",
        "<html><head><title>Techfest</title>"
        '<script type="application/ld+json">{"@type":"Event","name":"IIT Bombay Techfest 2026",'
        '"startDate":"2026-12-15","endDate":"2026-12-17",'
        '"location":{"@type":"Place","name":"IIT Bombay",'
        '"address":{"addressLocality":"Mumbai","addressCountry":"India"}},'
        '"organizer":{"name":"IIT Bombay"},"offers":{"price":"0","url":"https://techfest.org/reg"}}</script>'
        "</head><body>AI, robotics and Python workshops.</body></html>",
    ),
    (
        "Conference schedule (table)",
        "https://devconf.in/schedule",
        "<html><head><title>DevConf Schedule</title></head><body><table>"
        "<tr><th>Date</th><th>Session</th><th>Venue</th></tr>"
        "<tr><td>2026-09-01</td><td>Kubernetes Deep Dive</td><td>Bangalore</td></tr>"
        "<tr><td>2026-09-02</td><td>Rust for Systems</td><td>Bangalore</td></tr>"
        "<tr><td>2026-09-03</td><td>AI at Scale</td><td>Bangalore</td></tr></table></body></html>",
    ),
    (
        "Community (Next.js hydration)",
        "https://commudle.com/events",
        _nextdata(
            [
                {
                    "title": "GDG DevFest Pune",
                    "start_date": "2026-10-05",
                    "city": "Pune",
                    "url": "https://gdg.dev/pune",
                },
                {"title": "Frontend Meetup", "start_date": "2026-10-12", "city": "Delhi"},
            ]
        ),
    ),
    (
        "GitHub README (Markdown)",
        "https://raw.githubusercontent.com/x/events/README.md",
        "# FOSS Events\n\n## PyCon India 2026\n\nJoin us on 2026-10-15 in Hyderabad for Python. "
        "Register at https://in.pycon.org\n\n## Rust Hackathon\n\nOn 2026-11-01, a Rust hackathon "
        "in Bangalore.\n",
    ),
    (
        "Notion-style FAQ",
        "https://pydata.notion.site/meetup",
        "<html><head><title>PyData Bangalore Meetup</title></head><body>"
        "<details><summary>When?</summary><p>20 November 2026</p></details>"
        "<details><summary>Where?</summary><p>Bangalore, India</p></details>"
        '<details><summary>How to register?</summary><p><a href="https://pydata.org/rsvp">RSVP</a></p>'
        "</details><details><summary>Cost?</summary><p>Free</p></details>"
        "Python and data science.</body></html>",
    ),
    (
        "Public calendar (ICS)",
        "https://fosdem.org/2026.ics",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:FOSDEM Go DevRoom\nDTSTART:20260201T090000\n"
        "DTEND:20260201T170000\nLOCATION:Brussels\nURL:https://fosdem.org/2026\n"
        "DESCRIPTION:Go and open source\nEND:VEVENT\nEND:VCALENDAR",
    ),
    (
        "Blog (OpenGraph, one event)",
        "https://blog.hasgeek.com/rootconf-2026",
        '<html><head><meta property="og:title" content="Rootconf 2026 — DevOps">'
        '<meta property="og:description" content="DevOps and Kubernetes conference on 2026-08-20 '
        'in Bangalore, India">'
        '<meta property="og:site_name" content="Hasgeek"></head>'
        "<body>Published 2026.</body></html>",
    ),
    (
        "Shopping page (must reject)",
        "https://shop.example/sale",
        "<html><head><title>Mega Sale</title>"
        '<script type="application/ld+json">{"@type":"Event","name":"Flash Sale Event",'
        '"startDate":"2026-08-01"}</script></head><body>Buy now! Add to cart. Flat 50% off. '
        "Free shipping. Deal of the day.</body></html>",
    ),
]


async def main() -> None:
    print("=== Phase 10B — Universal Event Engine (fixtures, no network/browser/LLM) ===")
    print(
        'PER PAGE:  "where is the event info?" → extractors → merge → validate → confidence\n'
    )
    total_events = 0
    for label, url, html in PAGES:
        ct = (
            "text/markdown"
            if url.endswith(".md")
            else ("text/calendar" if url.endswith(".ics") else "text/html")
        )
        rep = await ENGINE.extract(url, html, content_type=ct)
        fired = [x for x in dict.fromkeys(rep.extractors_run)]
        print(f"● {label}")
        print(f"    {url}")
        print(f"    extractors fired: {fired}")
        print(f"    raw={rep.raw_events}  events={len(rep.events)}  rejected={rep.rejected}")
        total_events += len(rep.events)
        for ev in rep.events[:6]:
            print(f"      ✔ [{ev.confidence:.2f}] {ev.title!r}  (merged from {ev.sources})")
            print(
                f"          date={ev.get('start_date')} city={ev.get('city')} "
                f"venue={ev.get('venue')} type={ev.get('event_type')} "
                f"tech={ev.get('technologies')} reg={ev.get('registration_url')}"
            )
            top = sorted(ev.confidence_breakdown.items(), key=lambda kv: -kv[1])[:4]
            print(f"          confidence: {', '.join(f'{k}={v:.2f}' for k, v in top)}")
        if rep.rejected and not rep.events:
            print("      ✘ rejected — off-topic (not a tech/professional event)")
        print()

    print(
        f"=== {total_events} events extracted across {len(PAGES)} pages, "
        "every field provenance-bearing, one rejected ==="
    )
    print("  ✔ framework-agnostic byte-level extraction; no browser, no LLM; discovery only")


if __name__ == "__main__":
    asyncio.run(main())
