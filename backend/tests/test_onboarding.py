"""Phase 7A — Provider Onboarding Platform tests. Deterministic, no network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.models import CandidateSource, ConfidenceSignals, FeedType
from app.onboarding import (
    WEIGHTS,
    IllegalTransition,
    InMemoryOnboardingStore,
    OnboardingCandidate,
    OnboardingEngine,
    OnboardingState,
    Recommendation,
    SQLiteOnboardingStore,
    allowed_transitions,
    build_monitoring,
    build_promotion_plan,
    build_review_packet,
    can_transition,
    is_terminal,
    score_onboarding,
    simulate_sandbox,
    transition,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
_S = OnboardingState


def run(coro):
    return asyncio.run(coro)


def make(
    key,
    ft,
    *,
    domain="x.org",
    disc="crawl",
    title=None,
    city=None,
    country=None,
    org=None,
    cls=None,
    tech=0.0,
    india=0.0,
    sds=0,
    dc=None,
    emb=0,
    ec=0,
    tkw=0,
    ho=False,
    hr=False,
) -> CandidateSource:
    return CandidateSource(
        key=key,
        url=key,
        domain=domain,
        feed_type=ft,
        discovered_by=disc,
        title=title,
        city=city,
        country=country,
        organization=org,
        classification=cls,
        technology_confidence=tech,
        india_confidence=india,
        structured_data_score=sds,
        discovery_confidence=dc,
        embedded_event_count=emb,
        signals=ConfidenceSignals(
            event_count=ec, tech_keyword_count=tkw, has_organizer=ho, has_registration_link=hr
        ),
    )


# A strong candidate (auto), a mid candidate (review), a no-evidence candidate (failed sandbox).
def strong(key="https://gdg.dev/feed", domain="gdg.dev"):
    return make(
        key,
        FeedType.RSS,
        domain=domain,
        title="GDG Bangalore AI Python meetup",
        city="Bangalore",
        country="India",
        org="GDG",
        cls="community",
        tech=1.0,
        india=1.0,
        sds=1,
        ec=12,
        tkw=3,
        ho=True,
        hr=True,
    )


def mid(key="https://pydelhi.org/", domain="pydelhi.org"):
    return make(
        key,
        FeedType.AI_EXTRACTED,
        domain=domain,
        disc="ai",
        title="PyDelhi Python meetup",
        city="Delhi",
        country="India",
        org="PyDelhi",
        cls="community",
        tech=0.67,
        india=1.0,
        dc=0.62,
        tkw=2,
        ho=True,
    )


def empty(key="https://blog.io/x", domain="blog.io"):
    return make(key, FeedType.SEARCH_RESULT, domain=domain, title="a blog", tech=0.0, india=0.0)


def engine(**kw):
    return OnboardingEngine(InMemoryOnboardingStore(), clock=lambda: NOW, **kw)


# --------------------------- lifecycle ---------------------------


def test_lifecycle_legal_illegal_and_terminal():
    assert can_transition(_S.DISCOVERED, _S.ANALYZED)
    assert can_transition(_S.SCORED, _S.AUTO_APPROVED)
    assert not can_transition(_S.DISCOVERED, _S.PROMOTED)  # cannot skip stages
    assert not can_transition(_S.SCORED, _S.ACTIVE)
    assert is_terminal(_S.REJECTED) and is_terminal(_S.DUPLICATE)
    assert not is_terminal(_S.PROMOTED)  # PROMOTED→MONITORING exists (7B), so not terminal
    assert _S.MONITORING in allowed_transitions(_S.PROMOTED)


def test_transition_mutates_and_audits():
    c = OnboardingCandidate("k", "u", "d", "rss", "crawl", {})
    entry = transition(c, _S.ANALYZED, actor="auto", reason="ok", clock=lambda: NOW)
    assert c.state is _S.ANALYZED and c.version == 2 and c.updated_at == NOW
    assert entry.from_state == "discovered" and entry.to_state == "analyzed"
    try:
        transition(c, _S.PROMOTED, actor="auto", reason="skip", clock=lambda: NOW)
        raise AssertionError("expected IllegalTransition")
    except IllegalTransition:
        pass


# --------------------------- confidence ---------------------------


def test_confidence_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_explainable_and_banded():
    snap = engine()._snapshot(strong())
    sandbox = simulate_sandbox(snap)
    conf = score_onboarding(snap, sandbox)
    assert len(conf.factors) == 8
    # total is exactly the sum of factor contributions (nothing hidden)
    assert abs(conf.total - sum(f.contribution for f in conf.factors)) < 1e-6
    assert conf.band is Recommendation.AUTO_APPROVE
    assert all(f.detail for f in conf.factors)  # every factor explains itself

    weak = score_onboarding(
        engine()._snapshot(empty()), simulate_sandbox(engine()._snapshot(empty()))
    )
    assert weak.band is Recommendation.REJECT


def test_sandbox_pass_and_fail():
    ok = simulate_sandbox(engine()._snapshot(strong()))
    assert ok.passed and ok.plausible_events == 12 and ok.quality > 0
    bad = simulate_sandbox(engine()._snapshot(empty()))
    assert bad.passed is False and bad.plausible_events == 0


# --------------------------- review packet ---------------------------


def test_review_packet_contents():
    snap = engine()._snapshot(mid())
    sandbox = simulate_sandbox(snap)
    conf = score_onboarding(snap, sandbox)
    packet = build_review_packet(snap, conf, sandbox)
    assert packet.url == "https://pydelhi.org/" and packet.domain == "pydelhi.org"
    assert packet.confidence == conf.total and packet.confidence_reasons
    assert packet.extraction_summary["organization"] == "PyDelhi"
    assert packet.sample_events and packet.sandbox.tested
    assert "Python" in packet.technologies
    # AI-extracted source must be flagged as needing verification
    assert any("AI-understood" in r for r in packet.risks)


# --------------------------- promotion plan ---------------------------


def test_promotion_plan_is_blueprint_only():
    snap = engine()._snapshot(strong())
    sandbox = simulate_sandbox(snap)
    plan = build_promotion_plan(snap, score_onboarding(snap, sandbox), sandbox)
    assert plan.provider_type == "rss"
    assert "delta_sync" in plan.capabilities
    assert plan.expected_volume == "medium" and plan.refresh_interval_hours == 12
    assert plan.retry_policy["failure_threshold"] == 3
    assert any("not applied to production" in n for n in plan.notes)


def test_promotion_plan_ai_requires_validation():
    snap = engine()._snapshot(mid())
    sandbox = simulate_sandbox(snap)
    plan = build_promotion_plan(snap, score_onboarding(snap, sandbox), sandbox)
    assert plan.provider_type == "ai_assisted"
    assert "requires_validation" in plan.capabilities


# --------------------------- end-to-end pipeline ---------------------------


def test_pipeline_auto_approve_promotes_with_full_audit():
    eng = engine()
    cand = run(eng.onboard(strong()))
    assert cand.state is _S.PROMOTED and cand.promotion_plan is not None
    trail = [e.to_state for e in run(eng._store.audit_log(cand.key))]
    assert trail == ["analyzed", "sandboxed", "scored", "auto_approved", "approved", "promoted"]


def test_pipeline_review_then_human_decision():
    eng = engine()
    cand = run(eng.onboard(mid()))
    assert cand.state is _S.MANUAL_REVIEW and cand.review_packet is not None
    # human approves → APPROVED → PROMOTED
    out = run(
        eng.record_review_decision(cand.key, approve=True, reviewer="alice", notes="looks good")
    )
    assert out.state is _S.PROMOTED and out.promotion_plan is not None
    assert "looks good" in out.review_notes

    # a second reviewer path: reject
    eng2 = engine()
    c2 = run(eng2.onboard(mid()))
    out2 = run(
        eng2.record_review_decision(c2.key, approve=False, reviewer="bob", notes="off-topic")
    )
    assert out2.state is _S.REJECTED


def test_pipeline_rejections_blacklist_duplicate_sandbox():
    eng = engine(blacklist={"spam.com"})
    black = run(
        eng.onboard(
            make(
                "https://spam.com/x",
                FeedType.RSS,
                domain="spam.com",
                tech=1.0,
                india=1.0,
                sds=2,
                ec=9,
            )
        )
    )
    assert black.state is _S.BLACKLISTED

    run(eng.onboard(strong()))  # gdg.dev promoted
    dup = run(
        eng.onboard(
            make(
                "https://gdg.dev/other",
                FeedType.JSONLD_EVENT,
                domain="gdg.dev",
                city="Bangalore",
                tech=1.0,
                india=1.0,
                sds=2,
                ec=4,
            )
        )
    )
    assert dup.state is _S.DUPLICATE

    failed = run(eng.onboard(empty()))
    assert failed.state is _S.FAILED_SANDBOX


def test_ingest_from_inbox_reads_new_only():
    inbox = InMemoryDiscoveryInbox()
    run(inbox.upsert(strong()))
    run(inbox.upsert(mid()))
    eng = engine()
    results = run(eng.ingest_from_inbox(inbox))
    assert len(results) == 2
    assert {c.state for c in results} == {_S.PROMOTED, _S.MANUAL_REVIEW}


def test_never_reaches_production():
    eng = engine()
    run(eng.onboard(strong()))
    run(eng.onboard(mid()))
    # no candidate is ever auto-driven into MONITORING/ACTIVE (that is Phase 7B)
    assert all(c.state not in (_S.MONITORING, _S.ACTIVE) for c in eng.candidates())
    for c in eng.promotion_plans():
        assert any("not applied" in n for n in c.promotion_plan.notes)


# --------------------------- monitoring + analytics ---------------------------


def test_monitoring_rates_and_stale():
    eng = engine(blacklist={"spam.com"})
    run(eng.onboard(strong()))  # promoted
    run(eng.onboard(mid()))  # manual_review
    run(eng.onboard(empty()))  # failed_sandbox
    m = eng.monitoring()
    assert m.total == 3 and m.promoted == 1 and m.manual_review == 1 and m.failed_sandbox == 1
    assert m.approval_rate == round(1 / 3, 4) and m.rejection_rate == round(1 / 3, 4)
    assert 0 < m.avg_confidence <= 1

    # a review item aged past the staleness window is flagged
    def later():
        return NOW + timedelta(hours=100)

    stale = build_monitoring(eng.candidates(), stale_after_hours=72, clock=later)
    assert stale.stale_review == 1


def test_analytics_breakdowns():
    eng = engine()
    run(eng.onboard(strong()))
    run(eng.onboard(mid()))
    a = eng.analytics(inbox_size=10)
    assert a.inbox_size == 10
    assert a.promotion_candidates == 1 and a.review_queue == 1
    assert a.by_discovered_by.get("crawl") == 1 and a.by_discovered_by.get("ai") == 1
    assert a.by_feed_type.get("rss") == 1 and a.by_feed_type.get("ai_extracted") == 1
    assert 0 < a.average_confidence <= 1


# --------------------------- persistence ---------------------------


def test_sqlite_store_persists_state_and_audit():
    store = SQLiteOnboardingStore()
    eng = OnboardingEngine(store, clock=lambda: NOW)
    run(eng.onboard(strong()))
    assert run(store.count(state=_S.PROMOTED)) == 1
    got = run(store.get("https://gdg.dev/feed"))
    assert got is not None and got.state is _S.PROMOTED
    audit = run(store.audit_log("https://gdg.dev/feed"))
    assert [e.to_state for e in audit][-1] == "promoted"
    run(store.close())
