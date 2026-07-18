"""Phase 6F / D3 live demonstration (not a test): search-based source discovery, fully mocked.

Uses a MockSearchProvider over an in-memory corpus that stands in for real search results across
Meetup, GDG, IEEE branches, university clubs, company dev-event pages, and conference websites —
plus off-topic noise (movies/tourism/shopping) that ranking must reject. NO network, NO API keys.

Prints the whole pipeline: queries generated → results found → ranked → deduplicated → inserted
into the Discovery Inbox, then a second run proving the frontier prevents rediscovery.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery import SQLiteDiscoveryInbox  # noqa: E402
from app.discovery.search import (  # noqa: E402
    MockPage,
    MockSearchProvider,
    QuerySpec,
    SearchDiscoveryEngine,
    build_queries,
    score_source,
)
from app.discovery.search.parser import parse_results  # noqa: E402

# A stand-in "web" — what a real search engine might surface for our queries.
CORPUS = [
    # Meetup groups
    MockPage(
        "https://www.meetup.com/bangpypers/",
        "BangPypers - Bangalore Python User Group",
        "Monthly Python meetup in Bangalore, India.",
        ("bangalore", "python", "meetup"),
    ),
    MockPage(
        "https://www.meetup.com/reactjs-bangalore/",
        "ReactJS Bangalore",
        "React developers meetup in Bangalore, India.",
        ("bangalore", "react", "meetup"),
    ),
    MockPage(
        "https://www.meetup.com/kubernetes-delhi/",
        "Kubernetes Delhi",
        "Cloud native and Kubernetes meetup, Delhi India.",
        ("delhi", "kubernetes", "meetup"),
    ),
    # GDG / FOSS / Hasgeek community platforms
    MockPage(
        "https://gdg.community.dev/gdg-cloud-bangalore/",
        "GDG Cloud Bangalore",
        "Google Developer Group - AI and cloud events, Bangalore India.",
        ("bangalore", "ai", "gdg", "india"),
    ),
    MockPage(
        "https://gdg.community.dev/gdg-delhi/",
        "GDG Delhi",
        "Google Developer Group Delhi - Android, AI, web.",
        ("delhi", "ai", "gdg", "india"),
    ),
    MockPage(
        "https://fossunited.org/c/bangalore",
        "FOSS United Bangalore",
        "Open source community meetup, Bangalore India.",
        ("bangalore", "fossunited", "opensource", "meetup"),
    ),
    MockPage(
        "https://hasgeek.com/rootconf",
        "Rootconf - DevOps Conference",
        "Rootconf DevOps and infrastructure conference, India.",
        ("devops", "conference", "india", "rootconf"),
    ),
    # IEEE / universities
    MockPage(
        "https://ieee.nitk.ac.in/",
        "IEEE NITK Student Branch",
        "IEEE student branch AI workshops and tech events.",
        ("ieee", "ai", "workshop"),
    ),
    MockPage(
        "https://www.iitb.ac.in/tech-club",
        "IIT Bombay Tech Club",
        "AI and Python workshops at IIT Bombay, India.",
        ("iit", "ai", "python", "workshop"),
    ),
    MockPage(
        "https://www.bits-pilani.ac.in/apogee",
        "BITS Pilani APOGEE",
        "Annual technical festival, workshops and conference.",
        ("bits", "workshop", "conference"),
    ),
    # Company developer events
    MockPage(
        "https://developers.google.com/events/india",
        "Google Developer Events India",
        "Developer tech talks and events across India.",
        ("google", "india", "developer"),
    ),
    MockPage(
        "https://razorpay.com/events/",
        "Razorpay Engineering Events",
        "Engineering tech talks and developer meetups, Bangalore India.",
        ("razorpay", "bangalore", "developer", "india"),
    ),
    # Conference websites
    MockPage(
        "https://reactindia.io/",
        "React India Conference",
        "India's largest React and JavaScript conference.",
        ("react", "conference", "india"),
    ),
    MockPage(
        "https://in.pycon.org/",
        "PyCon India",
        "The annual Python conference for India.",
        ("python", "conference", "india", "pycon"),
    ),
    # ---- off-topic noise (should be penalized below threshold) ----
    MockPage(
        "https://in.bookmyshow.com/bangalore/movies",
        "Movies in Bangalore | BookMyShow",
        "Book movie tickets, concerts and comedy shows.",
        ("bangalore", "movies", "concert"),
    ),
    MockPage(
        "https://www.makemytrip.com/bangalore",
        "Bangalore Tourism and Hotels",
        "Travel, tourism and hotel deals in Bangalore.",
        ("bangalore", "tourism", "travel"),
    ),
    MockPage(
        "https://www.flipkart.com/sale",
        "Big Billion Sale | Flipkart",
        "Shopping deals and discounts.",
        ("shopping", "sale", "discount"),
    ),
]

SPEC = QuerySpec(
    cities=("Bangalore", "Delhi"),
    technologies=("Python", "AI", "React", "Kubernetes"),
    platforms=("meetup.com",),
    community_sites=("gdg.community.dev", "fossunited.org", "hasgeek.com"),
    event_types=("meetup", "conference"),
    universities=("IIT", "NIT", "BITS Pilani"),
    companies=("Google", "Razorpay"),
)


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="d3_"))
    inbox = SQLiteDiscoveryInbox(str(tmp / "candidates.db"))
    provider = MockSearchProvider(CORPUS)
    engine = SearchDiscoveryEngine(provider, inbox, min_score=0.3)

    queries = build_queries(SPEC)
    print("=== D3 search-based source discovery (MOCK search, no network) ===\n")
    print(f"GENERATE  {len(queries)} deterministic queries. Sample:")
    for q in queries[:8]:
        print(f"    {q}")
    print("    ...")

    # Show the raw SEARCH → PARSE → RANK stages for one representative query.
    demo_q = "site:meetup.com Bangalore Python"
    demo_hits = await provider.search(demo_q, limit=10)
    print(f"\nSEARCH    '{demo_q}' → {len(demo_hits)} raw results")
    for p in parse_results(demo_hits, demo_q):
        s = score_source(p)
        print(f"    rank {p.rank}  score {s.total:.2f}  {p.domain:16s} {p.title[:40]}")

    print("\nPIPELINE  Generate → Search → Parse → Rank → Deduplicate → Discovery Inbox")
    report = await engine.run(SPEC)
    print(f"    queries ............... {report.queries}")
    print(f"    results found ......... {report.results_found}  (parsed rows, all queries)")
    print(f"    unique after dedup .... {report.unique_results}")
    print(f"    duplicates removed .... {report.duplicates_removed}")
    print(f"    below threshold ....... {report.below_threshold}  (off-topic / weak → rejected)")
    print(f"    accepted (new) ........ {report.accepted}")
    print(f"    inserted into inbox ... {report.inserted}")
    print(f"    discovered domains .... {len(report.discovered_domains)}")
    for d in report.discovered_domains:
        print(f"        {d}")
    print(f"    final inbox size ...... {await inbox.count()}")

    print("\n=== DISCOVERED CANDIDATE SAMPLE (all discovered_by=search, status=NEW) ===")
    for c in await inbox.list(limit=20):
        print(
            f"    [{c.feed_type.value}] {c.domain:16s} "
            f"tech={c.technology_confidence:.2f} india={c.india_confidence:.2f} "
            f"pro={c.professional_confidence:.2f} rank={c.search_rank} :: {(c.title or '')[:34]}"
        )

    print("\n=== RUN 2 — frontier seeded from inbox (expect 0 new: never rediscover) ===")
    report2 = await engine.run(SPEC)
    print(
        f"    inserted={report2.inserted}  skipped_known={report2.skipped_known}  "
        f"inbox still {await inbox.count()} candidates (duplicates prevented across runs)"
    )
    print(f"    frontier: {report2.frontier}")

    await inbox.close()


if __name__ == "__main__":
    asyncio.run(main())
