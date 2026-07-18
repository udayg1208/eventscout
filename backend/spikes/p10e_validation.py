"""Phase 10E live demonstration: the Seed Validation Engine (fixtures, no network).

Closes the discovery loop: takes 10D-style Discovery Seeds and verifies each through the real
pipeline (fetch → 10B universal extraction → 10C organizer extraction → evidence → confidence merge
→ decision), upserting only VERIFIED / PARTIALLY_VERIFIED into the existing Discovery Inbox. Shows
an accepted seed, a partial one, a rejected one (reachable but empty), a duplicate (re-validation),
a retry that is scheduled then abandoned. Deterministic; fetcher + searcher are fixtures — no
network, no browser, no LLM; verification only.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.fetch import FetchResult, StaticFetcher  # noqa: E402
from app.ecosystem import ExpansionSeed, RelationshipPath, SeedKind  # noqa: E402
from app.validation import RetryPolicy, SeedValidationEngine  # noqa: E402

NOW = datetime(2026, 7, 16, tzinfo=UTC)


class FixtureSearcher:
    def __init__(self, mapping):
        self._m = mapping

    def search(self, query):
        return list(self._m.get(query, []))


def seed(kind, target, conf=0.6):
    return ExpansionSeed(
        kind=kind,
        target=target,
        target_key=target.lower().replace(" ", "-"),
        source="org:x",
        reason="10D seed",
        confidence=conf,
        search_hint=f"{target} tech community",
        path=RelationshipPath(nodes=["GDG Bangalore", target], relations=["same_chapter"]),
    )


RICH = (
    '<html><head><meta property="og:site_name" content="GDG Chennai">'
    '<script type="application/ld+json">{"@type":"Event","name":"DevFest Chennai 2026",'
    '"startDate":"2026-11-01","location":{"@type":"Place","name":"Chennai",'
    '"address":{"addressLocality":"Chennai"}}}</script></head>'
    "<body><h1>GDG Chennai</h1>Google Developer Group Chennai. DevFest. Python, AI. Chennai."
    '<a href="https://github.com/gdg-chennai">GitHub</a></body></html>'
)
THIN = "<html><body><h1>GDG Pune</h1>Google Developer Group Pune community.</body></html>"
PARKED = "<html><body>This domain is for sale. Contact us to buy.</body></html>"


def _R(url, text):
    return FetchResult(url=url, status=200, content_type="text/html", text=text)


async def main() -> None:
    print("=== Phase 10E — Seed Validation & Autonomous Growth Loop (fixtures, no network) ===\n")
    fetcher = StaticFetcher(
        {
            "https://gdg-chennai.dev/": _R("https://gdg-chennai.dev/", RICH),
            "https://gdg-pune.dev/": _R("https://gdg-pune.dev/", THIN),
            "https://parked.dev/": _R("https://parked.dev/", PARKED),
        }
    )
    searcher = FixtureSearcher(
        {
            "GDG Chennai tech community": ["https://gdg-chennai.dev/"],
            "GDG Pune tech community": ["https://gdg-pune.dev/"],
            "Ghost Org tech community": ["https://parked.dev/"],
            "Nowhere tech community": ["https://does-not-exist.dev/"],
        }
    )
    inbox = InMemoryDiscoveryInbox()
    eng = SeedValidationEngine(
        inbox,
        fetcher,
        searcher=searcher,
        clock=lambda: NOW,
        retry=RetryPolicy(max_retries=2, cooldown_runs=1),
    )

    seeds = [
        seed(SeedKind.CHAPTER_SIBLING, "GDG Chennai"),
        seed(SeedKind.CHAPTER_SIBLING, "GDG Pune"),
        seed(SeedKind.SIMILAR_ORGANIZER, "Ghost Org"),
        seed(SeedKind.CHAPTER_SIBLING, "Nowhere"),
    ]

    print("SEED → PLAN → EVIDENCE → CONFIDENCE → DECISION → INBOX\n")
    report = await eng.validate_batch(seeds)
    for rec in eng.audit_trail():
        e = rec.evidence
        print(f"● {rec.seed_target}  ({rec.seed_kind})")
        print(f"    path     : {' → '.join(rec.verification_path)}")
        print(
            f"    evidence : reachable={e['reachable']} events={e['events_found']} "
            f"organizer={e['organizer_name']} city={e['city']} signals={e['signal_count']}"
        )
        print(
            f"    decision : {rec.decision.upper()}  conf={rec.confidence:.2f}  "
            f"inbox={rec.inbox_outcome or '—'}"
        )
        print()

    print(f"REPORT: {report.as_dict()}\n")

    print("=== DISCOVERY INBOX (discovered_by=validation, status=NEW) ===")
    for c in await inbox.list(limit=10):
        print(
            f"    [{c.classification:16s}] {c.feed_type.value:13s} "
            f"conf={c.discovery_confidence:.2f} {c.url}"
        )

    print("\n=== DUPLICATE (re-validate the verified seed) ===")
    dup = await eng.validate(seeds[0], run=9)
    print(
        f"    GDG Chennai → {dup.decision.value}, inbox_outcome={dup.inbox_outcome}  "
        f"(inbox still {await inbox.count()})"
    )

    print("\n=== RETRY / ABANDONMENT (the unreachable seed) ===")
    key = seeds[3].target_key
    print(f"    after run 1: {eng.retry_state(key).as_dict()}")
    await eng.validate_batch([seeds[3]])
    print(f"    after run 2: {eng.retry_state(key).as_dict()}")

    print(f"\n=== METRICS ===\n    {eng.metrics.snapshot()}")
    print(
        "\n  ✔ generated seeds verified into the existing inbox; nothing onboarded; no network/LLM"
    )


if __name__ == "__main__":
    asyncio.run(main())
