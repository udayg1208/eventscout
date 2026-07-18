"""Phase 6G / D4 live demonstration (not a test): AI extraction of pages D1/D2 cannot parse.

Every page here is prose — NO RSS/JSON-LD/ICS/sitemap, NO framework hydration payload — so D1 and
D2 find nothing (shown explicitly per page). D3 would surface these domains via search; D4 then
*understands* them: extracting organization / city / technologies / event type WITH provenance,
while the validator rejects off-topic pages (concerts, shopping, travel, weddings). Fully mocked —
no network, no LLM, no API key.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery import SQLiteDiscoveryInbox  # noqa: E402
from app.discovery.ai import (  # noqa: E402
    AIDiscoveryPipeline,
    Decision,
    InMemoryAIExtractionStore,
    MockAIClassifier,
    MockAIExtractor,
)
from app.discovery.analysis import analyze_frameworks  # noqa: E402
from app.discovery.feeds import detect_feeds  # noqa: E402
from app.discovery.fetch import FetchResult  # noqa: E402

# (url, html, note, mock search rank from D3) — prose pages + off-topic noise.
PAGES = [
    (
        "https://cs.iitb.ac.in/techclub",
        "<html><title>IIT Bombay Tech Club</title><body>The IIT Bombay Tech Club is a student "
        "community. Organized by IIT Bombay CSE. We host Python, AI and Kubernetes workshops and "
        "hackathons every month in Mumbai, Maharashtra, India for students and developers. "
        "RSVP at https://iitb.ac.in/register.</body></html>",
        "university tech club (prose)",
        1,
    ),
    (
        "https://razorpay.com/engineering/events",
        "<html><title>Razorpay Engineering Events</title><body>Razorpay hosts developer tech talks "
        "and DevOps meetups in Bangalore, Karnataka, India. Organized by Razorpay Engineering. "
        "Topics include Go, Kubernetes and React for engineers.</body></html>",
        "company dev-events (prose)",
        2,
    ),
    (
        "https://blog.pydelhi.org/about",
        "<html><title>PyDelhi Community</title><body>PyDelhi is a community user group running "
        "monthly Python meetups and workshops in Delhi, India. Open source enthusiasts welcome. "
        "For developers and beginners.</body></html>",
        "community blog (prose)",
        3,
    ),
    (
        "https://conf.example.org/",
        "<html><title>AI Summit</title><head>"
        '<script type="application/ld+json">{"@type":"Event","name":"AI Summit","location":"Pune"}'
        "</script></head><body>AI conference in Pune, India.</body></html>",
        "STRUCTURED (D1 handles it → AI should defer)",
        None,
    ),
    (
        "https://in.bookmyshow.com/goa/sunburn",
        "<html><title>Sunburn Festival</title><body>Live music concert and DJ night in Goa. "
        "Book concert and movie tickets now!</body></html>",
        "concert (must reject)",
        None,
    ),
    (
        "https://shop.example.in/sale",
        "<html><title>Mega Sale</title><body>Huge shopping discounts and deals. Add to cart and "
        "buy now.</body></html>",
        "shopping (must reject)",
        None,
    ),
    (
        "https://travel.example.in/goa",
        "<html><title>Goa Holidays</title><body>Book hotels and holiday travel packages. Tourism "
        "and sightseeing.</body></html>",
        "travel (must reject)",
        None,
    ),
]


def _kv(field) -> str:
    return f"{field.value}" if field.is_known else "UNKNOWN"


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="d4_"))
    inbox = SQLiteDiscoveryInbox(str(tmp / "candidates.db"))
    store = InMemoryAIExtractionStore()
    pipe = AIDiscoveryPipeline(
        MockAIExtractor(), MockAIClassifier(), inbox, store=store, min_confidence=0.4
    )

    print("=== D4 AI extraction — understanding pages D1/D2 cannot parse (mock, no network) ===\n")
    for url, html, note, rank in PAGES:
        result = FetchResult(url=url, status=200, content_type="text/html", text=html)
        d1 = [d.feed_type.value for d in detect_feeds(result)]
        d2_events = analyze_frameworks(result).embedded_event_count
        outcome = await pipe.process(result, search_rank=rank, search_engine="mock")

        print(f"● {note}\n  {url}")
        print(
            f"  D1 feeds={d1 or '—'}   D2 embedded_events={d2_events}"
            f"   → decision: {outcome.decision.value}"
        )
        if outcome.decision is Decision.AI_ACCEPTED:
            ex = outcome.extraction
            print(
                f"  AI extracted: org={_kv(ex.organization)} | city={_kv(ex.city)} | "
                f"tech={_kv(ex.technologies)} | event_type={_kv(ex.event_types)}"
            )
            reasons = ", ".join(outcome.confidence.reasons)
            print(
                f"  class={outcome.classification.primary}  "
                f"confidence={outcome.confidence.total:.2f}  ({reasons})"
            )
        elif outcome.decision is Decision.AI_REJECTED:
            print(f"  REJECTED: {outcome.reasons[0]}")
        elif outcome.decision is Decision.DETERMINISTIC_SUFFICIENT:
            print("  deterministic extraction sufficient — D1/D2 own this page, AI skipped")
        print()

    print("=== SUMMARY ===")
    print(f"  Discovery Inbox candidates (discovered_by=ai): {await inbox.count()}")
    print(f"  AI extraction audit records (incl. rejects): {await store.count()}")
    print("\n  inbox contents:")
    for c in await inbox.list(limit=20):
        prov = await store.get(c.url)
        conf = c.discovery_confidence
        print(
            f"    [{c.feed_type.value}] {c.domain:20s} class={c.classification or '-':11s} "
            f"conf={conf:.2f} city={c.city or '-':10s} :: {(c.title or '')[:30]}"
        )
        # provenance is never opaque — show one field's source snippet
        if prov and prov.extraction.technologies.is_known:
            p = prov.extraction.technologies.provenance
            print(f"        provenance(technologies): '{p.source_snippet}' — {p.reason}")

    await inbox.close()


if __name__ == "__main__":
    asyncio.run(main())
