"""Phase 7A live demonstration (not a test): autonomous provider onboarding, fully deterministic.

Seeds a Discovery Inbox with candidates spanning every discovery type (D1 feeds, D2 framework, D3
search, D4 AI) plus edge cases (duplicate, blacklisted, no-evidence), then runs the onboarding
pipeline: Confidence → Sandbox → Review Packet → Promotion Plan → Monitoring. Two candidates get a
simulated human decision. NOTHING is promoted to production — every candidate rests at PROMOTED
(plan staged), MANUAL_REVIEW, or a rejection state. No network, no LLM.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.models import CandidateSource, ConfidenceSignals, FeedType  # noqa: E402
from app.onboarding import OnboardingEngine, OnboardingState, SQLiteOnboardingStore  # noqa: E402

_S = OnboardingState


def cand(key, ft, **kw) -> CandidateSource:
    return CandidateSource(
        key=key,
        url=key,
        domain=kw["domain"],
        feed_type=ft,
        discovered_by=kw.get("disc", "crawl"),
        title=kw.get("title"),
        city=kw.get("city"),
        country=kw.get("country"),
        organization=kw.get("org"),
        classification=kw.get("cls"),
        technology_confidence=kw.get("tech", 0.0),
        india_confidence=kw.get("india", 0.0),
        structured_data_score=kw.get("sds", 0),
        discovery_confidence=kw.get("dc"),
        embedded_event_count=kw.get("emb", 0),
        signals=ConfidenceSignals(
            event_count=kw.get("ec", 0),
            tech_keyword_count=kw.get("tkw", 0),
            has_organizer=kw.get("ho", False),
            has_registration_link=kw.get("hr", False),
        ),
    )


CANDIDATES = [
    cand(
        "https://gdg.community.dev/feed.xml",
        FeedType.RSS,
        domain="community.dev",
        title="GDG Bangalore — AI & Python meetup",
        city="Bangalore",
        country="India",
        org="GDG",
        cls="community",
        tech=1.0,
        india=1.0,
        sds=1,
        ec=14,
        tkw=3,
        ho=True,
        hr=True,
    ),
    cand(
        "https://fossunited.org/cal.ics",
        FeedType.ICS,
        domain="fossunited.org",
        title="FOSS United — open source meetups",
        city="Delhi",
        country="India",
        org="FOSS United",
        cls="community",
        tech=0.67,
        india=1.0,
        sds=1,
        ec=8,
        tkw=2,
        ho=True,
    ),
    cand(
        "https://reactindia.io/",
        FeedType.JSONLD_EVENT,
        domain="reactindia.io",
        title="React India Conference 2026",
        city="Goa",
        country="India",
        cls="conference",
        tech=1.0,
        india=1.0,
        sds=2,
        ec=6,
        tkw=2,
        hr=True,
    ),
    cand(
        "https://lu.ma/bengaluru",
        FeedType.NEXT_DATA,
        domain="lu.ma",
        title="Bengaluru tech events",
        city="Bangalore",
        country="India",
        cls="meetup",
        tech=0.67,
        india=1.0,
        sds=1,
        emb=11,
        tkw=2,
    ),
    cand(
        "https://blog.pydelhi.org/about",
        FeedType.AI_EXTRACTED,
        domain="pydelhi.org",
        disc="ai",
        title="PyDelhi community",
        city="Delhi",
        country="India",
        org="PyDelhi",
        cls="community",
        tech=0.67,
        india=1.0,
        dc=0.68,
        tkw=2,
        ho=True,
    ),
    cand(
        "https://someblog.io/events",
        FeedType.SEARCH_RESULT,
        domain="someblog.io",
        disc="search",
        title="A tech blog with occasional events",
        tech=0.33,
        india=0.0,
    ),
    cand(
        "https://gdg.community.dev/events/x",
        FeedType.JSONLD_EVENT,
        domain="community.dev",
        title="GDG event page (duplicate domain)",
        city="Bangalore",
        country="India",
        tech=1.0,
        india=1.0,
        sds=2,
        ec=3,
    ),
    cand(
        "https://spammy-events.net/x",
        FeedType.RSS,
        domain="spammy-events.net",
        title="events events events",
        tech=1.0,
        india=1.0,
        sds=1,
        ec=20,
    ),
    cand(
        "https://randomcorp.com/about",
        FeedType.SEARCH_RESULT,
        domain="randomcorp.com",
        disc="search",
        title="About our company",
        tech=0.0,
        india=0.0,
    ),
]


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="p7a_"))
    store = SQLiteOnboardingStore(str(tmp / "onboarding.db"))
    inbox = InMemoryDiscoveryInbox()
    for c in CANDIDATES:
        await inbox.upsert(c)

    engine = OnboardingEngine(store, blacklist={"spammy-events.net"})

    print("=== Phase 7A — Autonomous Provider Onboarding (deterministic, no network) ===\n")
    print(f"Discovery Inbox size: {await inbox.count()}")
    print("PIPELINE  Inbox → Confidence → Sandbox → Review/Promotion → Monitoring\n")

    results = await engine.ingest_from_inbox(inbox)
    for c in results:
        conf = f"{c.confidence.total:.2f}" if c.confidence else "  — "
        print(f"  {c.domain:20s} [{c.feed_type:14s}] conf={conf} → {c.state.value}")

    promoted = engine.promotion_plans()
    review = engine.review_queue()
    rejected = [
        c
        for c in engine.candidates()
        if c.state in (_S.REJECTED, _S.BLACKLISTED, _S.DUPLICATE, _S.FAILED_SANDBOX)
    ]

    print(
        f"\n  promoted (plan staged): {len(promoted)}   review queue: {len(review)}   "
        f"rejected: {len(rejected)}"
    )

    # ---- simulated human-in-the-loop on the review queue ----
    print("\n=== HUMAN REVIEW (simulated) ===")
    for c in review:
        approve = c.confidence.total >= 0.55  # reviewer heuristic for the demo
        decision = "APPROVE" if approve else "REJECT"
        await engine.record_review_decision(
            c.key,
            approve=approve,
            reviewer="demo-reviewer",
            notes=f"{decision} at confidence {c.confidence.total:.2f}",
        )
        print(f"  {c.domain:20s} conf={c.confidence.total:.2f} → {decision} → {c.state.value}")

    # ---- a sample review packet + promotion plan (nothing opaque) ----
    if review:
        p = review[0].review_packet
        print(f"\n=== SAMPLE REVIEW PACKET — {p.domain} ===")
        print(f"  confidence={p.confidence:.2f}  recommendation={p.recommendation.value}")
        print(f"  technologies={p.technologies}")
        print(f"  risks={p.risks}")
        print(
            f"  sandbox: passed={p.sandbox.passed} quality={p.sandbox.quality} "
            f"plausible_events={p.sandbox.plausible_events}"
        )
    if promoted:
        plan = promoted[0].promotion_plan
        print(f"\n=== SAMPLE PROMOTION PLAN — {plan.domain} (STAGED, NOT APPLIED) ===")
        print(
            f"  provider_type={plan.provider_type}  refresh={plan.refresh_interval_hours}h  "
            f"volume={plan.expected_volume}  risk={plan.risk_assessment['level']}"
        )
        print(f"  capabilities={plan.capabilities}")
        print(f"  retry_policy={plan.retry_policy}")
        print(f"  note: {plan.notes[0]}")

    # ---- monitoring + analytics ----
    m = engine.monitoring()
    print("\n=== MONITORING ===")
    print(
        f"  total={m.total}  approval_rate={m.approval_rate}  rejection_rate={m.rejection_rate}  "
        f"duplicate_rate={m.duplicate_rate}  sandbox_failure_rate={m.sandbox_failure_rate}"
    )
    print(
        f"  promoted={m.promoted}  manual_review={m.manual_review}  rejected={m.rejected}  "
        f"duplicate={m.duplicate}  blacklisted={m.blacklisted}  failed_sandbox={m.failed_sandbox}"
    )
    print(
        f"  avg_confidence={m.avg_confidence}  avg_quality={m.avg_quality}  "
        f"false_positive_estimate={m.false_positive_estimate}"
    )

    a = engine.analytics(inbox_size=await inbox.count())
    print("\n=== ANALYTICS ===")
    print(
        f"  inbox_size={a.inbox_size}  review_queue={a.review_queue}  "
        f"auto_approvals={a.auto_approvals}  human_approvals={a.human_approvals}"
    )
    print(
        f"  rejections={a.rejections}  promotion_candidates={a.promotion_candidates}  "
        f"average_confidence={a.average_confidence}"
    )
    print(f"  by_state={a.by_state}")
    print(f"  discovery trends by source: {a.by_discovered_by}   by feed type: {a.by_feed_type}")

    print("\n  ✔ nothing promoted to production — everything rests at PROMOTED / REVIEW / REJECTED")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
