"""Phase 10E — Seed Validation tests. Fixtures only, NO network/browser/LLM."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.fetch import FetchResult, StaticFetcher
from app.discovery.models import DiscoveryStatus, FeedType
from app.ecosystem import ExpansionSeed, RelationshipPath, SeedKind
from app.validation import (
    CONFIDENCE_WEIGHTS,
    CandidateBuilder,
    DecisionEngine,
    Evidence,
    EvidenceCollector,
    InMemoryValidationStore,
    RetryPolicy,
    RetryState,
    SeedValidationEngine,
    SQLiteValidationStore,
    ValidationMetrics,
    VerificationConfidence,
    VerificationConfidenceMerger,
    VerificationDecision,
    VerificationPlanner,
    VerificationResult,
    slugify,
)
from app.validation.models import AuditRecord, VerificationPlan

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def seed(kind=SeedKind.CHAPTER_SIBLING, target="GDG Chennai", hint=None, conf=0.6):
    return ExpansionSeed(
        kind=kind,
        target=target,
        target_key=slugify(target),
        source="org:x",
        reason="r",
        confidence=conf,
        search_hint=hint or f"{target} tech community",
        path=RelationshipPath(nodes=["GDG Bangalore", target]),
    )


class FixtureSearcher:
    def __init__(self, mapping=None):
        self._m = mapping or {}

    def search(self, query):
        return list(self._m.get(query, []))


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


def R(url, text, status=200):
    return FetchResult(url=url, status=status, content_type="text/html", text=text)


def _fetcher():
    return StaticFetcher(
        {
            "https://gdg-chennai.dev/": R("https://gdg-chennai.dev/", RICH),
            "https://www.meetup.com/gdg-chennai/": R("https://www.meetup.com/gdg-chennai/", RICH),
            "https://gdg-pune.dev/": R("https://gdg-pune.dev/", THIN),
            "https://www.meetup.com/gdg-pune/": R("https://www.meetup.com/gdg-pune/", THIN),
            "https://parked.dev/": R("https://parked.dev/", PARKED),
        }
    )


def _searcher():
    return FixtureSearcher(
        {
            "GDG Chennai tech community": ["https://gdg-chennai.dev/"],
            "GDG Pune tech community": ["https://gdg-pune.dev/"],
            "Ghost Org tech community": ["https://parked.dev/"],
            "Nowhere tech community": ["https://does-not-exist.dev/"],
        }
    )


def _engine(inbox=None, **kw):
    return SeedValidationEngine(
        inbox or InMemoryDiscoveryInbox(), _fetcher(), searcher=_searcher(), clock=lambda: NOW, **kw
    )


def evidence(**kw):
    return Evidence(**kw)


def conf(total=0.6):
    return VerificationConfidence(total=total, components={}, reasons={})


# --------------------------------------------------------------------------- models


def test_evidence_signal_count():
    e = Evidence(reachable=True, organizer_name="X", city="Y", events_found=2)
    assert e.signal_count() == 4


def test_evidence_merge():
    a = Evidence(reachable=True, organizer_name="A", technologies=["Python"])
    b = Evidence(has_jsonld=True, technologies=["AI"], city="Delhi", pages_fetched=1)
    a.merge(b)
    assert a.reachable and a.has_jsonld and a.city == "Delhi"
    assert a.technologies == ["AI", "Python"] and a.pages_fetched == 1


def test_evidence_as_dict():
    d = Evidence(reachable=True, events_found=1).as_dict()
    assert d["reachable"] and d["signal_count"] == 2


def test_verification_result_accepted():
    for d in (VerificationDecision.VERIFIED, VerificationDecision.PARTIALLY_VERIFIED):
        r = VerificationResult(
            "t", "chapter_sibling", d, conf(), Evidence(), VerificationPlan("x", "q")
        )
        assert r.accepted
    for d in (VerificationDecision.REJECTED, VerificationDecision.INSUFFICIENT_EVIDENCE):
        r = VerificationResult("t", "k", d, conf(), Evidence(), VerificationPlan("x", "q"))
        assert not r.accepted


def test_verification_result_as_dict():
    r = VerificationResult(
        "GDG X",
        "chapter_sibling",
        VerificationDecision.VERIFIED,
        conf(0.7),
        Evidence(reachable=True),
        VerificationPlan("chapter", "q"),
        timestamp=NOW,
    )
    d = r.as_dict()
    assert d["decision"] == "verified" and d["seed_target"] == "GDG X" and d["timestamp"]


def test_plan_as_dict():
    p = VerificationPlan("chapter", "GDG X", ["https://x/"], ["search", "homepage"])
    assert p.as_dict()["steps"] == ["search", "homepage"]


def test_retry_state_as_dict():
    assert RetryState("k", attempts=2).as_dict()["attempts"] == 2


def test_audit_record_as_dict():
    a = AuditRecord("t", "k", "verified", 0.6, {}, ["r"], ["search"], "inserted", NOW.isoformat())
    assert a.as_dict()["decision"] == "verified"


def test_validation_report_as_dict():
    from app.validation.models import ValidationReport

    assert ValidationReport(verified=2, total=5).as_dict()["verified"] == 2


# --------------------------------------------------------------------------- planner


def test_planner_strategy_for_each_kind():
    pl = VerificationPlanner()
    for kind in SeedKind:
        assert pl.strategy_for(seed(kind=kind, target="X")) is not None


def test_planner_plan_chapter():
    p = VerificationPlanner().plan(seed(SeedKind.CHAPTER_SIBLING, "GDG Chennai"))
    assert p.strategy == "chapter_sibling"
    assert any("gdg-chennai" in u for u in p.candidate_urls)
    assert "universal_extraction" in p.steps


def test_planner_search_query_from_hint():
    p = VerificationPlanner().plan(seed(target="GDG Delhi", hint="find gdg delhi"))
    assert p.search_query == "find gdg delhi"


def test_planner_series_steps():
    p = VerificationPlanner().plan(seed(SeedKind.SERIES_INSTANCE, "DevFest Pune"))
    assert "event_page" in p.steps


def test_planner_university_steps():
    p = VerificationPlanner().plan(seed(SeedKind.UNIVERSITY_UNIT, "ACM IIT Delhi"))
    assert "student_clubs" in p.steps


def test_planner_connected_uses_target_url():
    p = VerificationPlanner().plan(seed(SeedKind.CONNECTED_RESOURCE, "github.com/gdgx"))
    assert p.candidate_urls == ["https://github.com/gdgx"]


def test_slugify():
    assert slugify("GDG Chennai!") == "gdg-chennai"


def test_strategy_evaluate_content_signals():
    pl = VerificationPlanner()
    strat = pl.strategy_for(seed(SeedKind.CHAPTER_SIBLING))
    full = Evidence(reachable=True, organizer_name="X", city="Y")
    score, reasons = strat.evaluate(seed(), full)
    assert score == 1.0  # organizer + city both present
    empty = Evidence(reachable=True)
    assert strat.evaluate(seed(), empty)[0] == 0.0  # reachable is NOT a content signal


def test_strategy_reachable_not_a_content_signal():
    strat = VerificationPlanner().strategy_for(seed(SeedKind.CHAPTER_SIBLING))
    assert "reachable" not in strat.expected


# --------------------------------------------------------------------------- evidence


def test_evidence_collect_rich_page():
    e = run(EvidenceCollector().collect("https://gdg-chennai.dev/", RICH, seed()))
    assert e.reachable and e.events_found >= 1 and e.has_jsonld
    assert e.organizer_name == "GDG Chennai" and e.city == "Chennai"
    assert "Python" in e.technologies


def test_evidence_collect_thin_page():
    e = run(EvidenceCollector().collect("https://gdg-pune.dev/", THIN, seed(target="GDG Pune")))
    assert e.reachable and e.organizer_name == "GDG Pune"
    assert e.events_found == 0


def test_evidence_collect_parked_no_organizer():
    # the seed name must NOT leak into evidence — a parked page has no organizer
    e = run(EvidenceCollector().collect("https://parked.dev/", PARKED, seed(target="Ghost Org")))
    assert e.reachable and e.organizer_name is None and e.events_found == 0
    assert e.signal_count() == 1  # reachable only


# --------------------------------------------------------------------------- confidence


def test_confidence_weights_sum_to_one():
    assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_total_is_weighted_sum():
    e = Evidence(
        reachable=True, universal_confidence=0.8, organizer_confidence=0.7, pages_fetched=1
    )
    cs = VerificationConfidenceMerger().merge(seed_confidence=0.6, evidence=e)
    recomputed = sum(cs.components[k] * CONFIDENCE_WEIGHTS[k] for k in CONFIDENCE_WEIGHTS)
    assert abs(cs.total - recomputed) < 1e-3
    assert cs.reasons


def test_confidence_discovery_zero_when_unreachable():
    cs = VerificationConfidenceMerger().merge(
        seed_confidence=0.6, evidence=Evidence(reachable=False)
    )
    assert cs.components["discovery"] == 0.0


def test_confidence_uses_all_four_signals():
    cs = VerificationConfidenceMerger().merge(
        seed_confidence=0.5, evidence=Evidence(reachable=True)
    )
    assert set(cs.components) == {"seed", "discovery", "universal", "organizer"}


# --------------------------------------------------------------------------- decision


def _decide(ev, total, score):
    return DecisionEngine().decide(ev, conf(total), score)[0]


def test_decision_verified():
    ev = Evidence(
        reachable=True,
        events_found=2,
        organizer_name="X",
        city="Y",
        technologies=["Py"],
        has_jsonld=True,
    )
    assert _decide(ev, 0.6, 1.0) is VerificationDecision.VERIFIED


def test_decision_partial():
    ev = Evidence(reachable=True, organizer_name="X")
    assert _decide(ev, 0.4, 0.5) is VerificationDecision.PARTIALLY_VERIFIED


def test_decision_rejected_reachable_but_empty():
    ev = Evidence(reachable=True)  # reachable, zero content
    assert _decide(ev, 0.2, 0.0) is VerificationDecision.REJECTED


def test_decision_insufficient_unreachable():
    assert (
        _decide(Evidence(reachable=False), 0.1, 0.0) is VerificationDecision.INSUFFICIENT_EVIDENCE
    )


def test_decision_verified_requires_strong_confidence():
    ev = Evidence(reachable=True, organizer_name="X", city="Y")  # 2 content but low conf/no events
    assert _decide(ev, 0.3, 1.0) is VerificationDecision.PARTIALLY_VERIFIED


def test_decision_never_invents_low_evidence():
    # a single weak signal is partial at most, never verified
    assert (
        _decide(Evidence(reachable=True, city="X"), 0.9, 0.9) is not VerificationDecision.VERIFIED
    )


# --------------------------------------------------------------------------- retry


def test_retry_eligible_new_seed():
    assert RetryPolicy().eligible(None, 0)


def test_retry_eligible_respects_next_run():
    st = RetryState("k", next_run=5)
    assert not RetryPolicy().eligible(st, 3)
    assert RetryPolicy().eligible(st, 5)


def test_retry_abandoned_not_eligible():
    assert not RetryPolicy().eligible(RetryState("k", abandoned=True), 99)


def test_retry_terminal_no_retry():
    p = RetryPolicy()
    for d in (VerificationDecision.VERIFIED, VerificationDecision.REJECTED):
        will, _ = p.on_decision(RetryState("k"), d, 0)
        assert not will


def test_retry_insufficient_schedules():
    will, st = RetryPolicy(cooldown_runs=2).on_decision(
        RetryState("k"), VerificationDecision.INSUFFICIENT_EVIDENCE, 1
    )
    assert will and st.attempts == 1 and st.next_run == 3


def test_retry_abandons_after_max():
    p = RetryPolicy(max_retries=2)
    st = RetryState("k")
    p.on_decision(st, VerificationDecision.INSUFFICIENT_EVIDENCE, 1)
    will, st = p.on_decision(st, VerificationDecision.INSUFFICIENT_EVIDENCE, 2)
    assert not will and st.abandoned


# --------------------------------------------------------------------------- inbox builder


def _result(decision=VerificationDecision.VERIFIED, **ev):
    e = Evidence(reachable=True, homepage_url="https://gdg-chennai.dev/", **ev)
    return VerificationResult(
        "GDG Chennai",
        "chapter_sibling",
        decision,
        conf(0.7),
        e,
        VerificationPlan("chapter", "q"),
        timestamp=NOW,
    )


def test_builder_candidate_fields():
    c = CandidateBuilder().build(
        _result(
            organizer_name="GDG Chennai", city="Chennai", technologies=["Python"], events_found=1
        ),
        now=NOW,
    )
    assert c.url == "https://gdg-chennai.dev/"
    assert c.discovered_by == "validation" and c.status is DiscoveryStatus.NEW
    assert c.classification == "chapter_sibling"
    assert c.city == "Chennai" and c.organization == "GDG Chennai"
    assert c.discovery_confidence == 0.7


def test_builder_feed_type_from_evidence():
    assert CandidateBuilder().build(_result(calendars=["c"]), now=NOW).feed_type is FeedType.ICS
    assert CandidateBuilder().build(_result(feeds=["f"]), now=NOW).feed_type is FeedType.RSS
    assert (
        CandidateBuilder().build(_result(has_jsonld=True), now=NOW).feed_type
        is FeedType.AI_EXTRACTED
    )
    assert CandidateBuilder().build(_result(), now=NOW).feed_type is FeedType.SEARCH_RESULT


# --------------------------------------------------------------------------- metrics


def test_metrics_record_and_rates():
    m = ValidationMetrics()
    for d, outcome in [
        (VerificationDecision.VERIFIED, "inserted"),
        (VerificationDecision.PARTIALLY_VERIFIED, "inserted"),
        (VerificationDecision.REJECTED, None),
        (VerificationDecision.INSUFFICIENT_EVIDENCE, None),
    ]:
        r = _result(d)
        r.inbox_outcome = outcome
        m.record(r)
    snap = m.snapshot()
    assert snap["total"] == 4
    assert snap["verification_rate"] == 0.5  # (1 verified + 1 partial) / 4
    assert snap["acceptance_rate"] == 0.5
    assert snap["rejection_rate"] == 0.25


def test_metrics_duplicate_rate():
    m = ValidationMetrics()
    r1, r2 = _result(), _result()
    r1.inbox_outcome, r2.inbox_outcome = "inserted", "updated"
    m.record(r1)
    m.record(r2)
    assert m.snapshot()["duplicate_rate"] == 0.5  # 1 updated / 2 accepted


def test_metrics_averages():
    m = ValidationMetrics()
    r = _result(organizer_name="X", city="Y")
    m.record(r)
    snap = m.snapshot()
    assert snap["avg_evidence_count"] == 3  # reachable + organizer + city
    assert snap["avg_confidence"] == 0.7


# --------------------------------------------------------------------------- store


def test_inmemory_store_audit_and_retry():
    store = InMemoryValidationStore()
    rec = AuditRecord("t", "k", "verified", 0.6, {}, [], [], None, NOW.isoformat())
    run(store.save_audit(rec))
    run(store.save_retry(RetryState("k", attempts=1)))
    assert len(run(store.load_audit())) == 1
    assert run(store.load_retries())["k"].attempts == 1


def test_sqlite_store_roundtrip():
    store = SQLiteValidationStore(":memory:")
    try:
        run(
            store.save_audit(
                AuditRecord(
                    "GDG X",
                    "chapter_sibling",
                    "verified",
                    0.6,
                    {"reachable": True},
                    ["r"],
                    ["search"],
                    "inserted",
                    NOW.isoformat(),
                )
            )
        )
        run(store.save_retry(RetryState("gdg-x", attempts=2, abandoned=True)))
        audit = run(store.load_audit())
        assert len(audit) == 1 and audit[0].decision == "verified"
        retries = run(store.load_retries())
        assert retries["gdg-x"].abandoned
        assert run(store.count_audit()) == 1
    finally:
        run(store.close())


def test_sqlite_store_empty():
    store = SQLiteValidationStore(":memory:")
    try:
        assert run(store.load_audit()) == []
        assert run(store.load_retries()) == {}
    finally:
        run(store.close())


# --------------------------------------------------------------------------- engine


def test_engine_verified_reaches_inbox():
    inbox = InMemoryDiscoveryInbox()
    result = run(_engine(inbox).validate(seed(SeedKind.CHAPTER_SIBLING, "GDG Chennai")))
    assert result.decision is VerificationDecision.VERIFIED
    assert result.inbox_outcome == "inserted"
    assert run(inbox.count()) == 1
    c = run(inbox.get(result.candidate_key))
    assert c.discovered_by == "validation" and c.status is DiscoveryStatus.NEW


def test_engine_partial_reaches_inbox():
    inbox = InMemoryDiscoveryInbox()
    result = run(_engine(inbox).validate(seed(SeedKind.CHAPTER_SIBLING, "GDG Pune")))
    assert result.decision is VerificationDecision.PARTIALLY_VERIFIED
    assert run(inbox.count()) == 1


def test_engine_rejected_not_in_inbox():
    inbox = InMemoryDiscoveryInbox()
    result = run(_engine(inbox).validate(seed(SeedKind.SIMILAR_ORGANIZER, "Ghost Org")))
    assert result.decision is VerificationDecision.REJECTED
    assert result.inbox_outcome is None and run(inbox.count()) == 0


def test_engine_insufficient_not_in_inbox():
    inbox = InMemoryDiscoveryInbox()
    result = run(_engine(inbox).validate(seed(SeedKind.CHAPTER_SIBLING, "Nowhere")))
    assert result.decision is VerificationDecision.INSUFFICIENT_EVIDENCE
    assert run(inbox.count()) == 0


def test_engine_duplicate_on_revalidate():
    inbox = InMemoryDiscoveryInbox()
    eng = _engine(inbox)
    run(eng.validate(seed(target="GDG Chennai")))
    again = run(eng.validate(seed(target="GDG Chennai")))
    assert again.inbox_outcome == "updated"  # already in inbox → duplicate
    assert run(inbox.count()) == 1


def test_engine_uses_candidate_urls_without_searcher():
    # no searcher — the strategy's URL templates must still resolve
    inbox = InMemoryDiscoveryInbox()
    eng = SeedValidationEngine(inbox, _fetcher(), clock=lambda: NOW)
    result = run(eng.validate(seed(SeedKind.CHAPTER_SIBLING, "GDG Chennai")))
    assert result.decision is VerificationDecision.VERIFIED


def test_engine_batch_report():
    seeds = [
        seed(SeedKind.CHAPTER_SIBLING, "GDG Chennai"),
        seed(SeedKind.CHAPTER_SIBLING, "GDG Pune"),
        seed(SeedKind.SIMILAR_ORGANIZER, "Ghost Org"),
        seed(SeedKind.CHAPTER_SIBLING, "Nowhere"),
    ]
    report = run(_engine().validate_batch(seeds))
    assert report.total == 4
    assert report.verified == 1 and report.partial == 1
    assert report.rejected == 1 and report.insufficient == 1
    assert report.accepted_to_inbox == 2 and report.retries_scheduled == 1


def test_engine_audit_trail_records_every_decision():
    eng = _engine()
    run(
        eng.validate_batch(
            [seed(target="GDG Chennai"), seed(target="Ghost Org", kind=SeedKind.SIMILAR_ORGANIZER)]
        )
    )
    assert len(eng.audit_trail()) == 2
    assert eng.audit_trail()[0].verification_path  # steps recorded


def test_engine_retry_and_abandon():
    eng = _engine(retry=RetryPolicy(max_retries=2, cooldown_runs=1))
    s = seed(SeedKind.CHAPTER_SIBLING, "Nowhere")
    run(eng.validate_batch([s]))  # run 1 → insufficient, attempts 1
    st = eng.retry_state(s.target_key)
    assert st.attempts == 1 and not st.abandoned
    run(eng.validate_batch([s]))  # run 2 → attempts 2 → abandoned
    assert eng.retry_state(s.target_key).abandoned


def test_engine_cooldown_skips():
    eng = _engine(retry=RetryPolicy(max_retries=5, cooldown_runs=3))
    s = seed(SeedKind.CHAPTER_SIBLING, "Nowhere")
    run(eng.validate_batch([s]))  # run 1 → insufficient, next_run=4
    report2 = run(eng.validate_batch([s]))  # run 2 → within cooldown → skipped
    assert report2.skipped_cooldown == 1


def test_engine_metrics_populated():
    eng = _engine()
    run(eng.validate_batch([seed(target="GDG Chennai"), seed(target="GDG Pune")]))
    snap = eng.metrics.snapshot()
    assert snap["total"] == 2 and snap["acceptance_rate"] == 1.0


def test_engine_max_urls_limits_fetches():
    inbox = InMemoryDiscoveryInbox()
    eng = SeedValidationEngine(
        inbox, _fetcher(), searcher=_searcher(), max_urls=0, clock=lambda: NOW
    )
    result = run(eng.validate(seed(target="GDG Chennai")))
    assert result.decision is VerificationDecision.INSUFFICIENT_EVIDENCE  # fetched nothing


def test_engine_persists_to_store():
    store = SQLiteValidationStore(":memory:")
    try:
        eng = _engine(store=store)
        run(eng.validate(seed(target="GDG Chennai")))
        assert run(store.count_audit()) == 1
        assert run(store.load_retries())
    finally:
        run(store.close())


def test_engine_skips_failed_fetch():
    inbox = InMemoryDiscoveryInbox()
    fetcher = StaticFetcher({"https://x.dev/": R("https://x.dev/", "", status=404)})
    searcher = FixtureSearcher({"X tech community": ["https://x.dev/"]})
    eng = SeedValidationEngine(inbox, fetcher, searcher=searcher, clock=lambda: NOW)
    result = run(eng.validate(seed(target="X")))
    assert result.decision is VerificationDecision.INSUFFICIENT_EVIDENCE


# --------------------------------------------------------------------------- additional coverage


def test_evidence_merge_snippets_capped():
    a = Evidence(snippets=["a"] * 10)
    a.merge(Evidence(snippets=["b"] * 10))
    assert len(a.snippets) <= 12


def test_confidence_as_dict():
    cs = VerificationConfidence(0.6, {"seed": 0.5}, {"seed": "r"})
    assert cs.as_dict()["total"] == 0.6 and cs.as_dict()["components"]["seed"] == 0.5


def test_planner_sponsor_hosts():
    p = VerificationPlanner().plan(seed(SeedKind.SPONSOR_PROGRAM, "Build with AI"))
    assert any("build-with-ai" in u for u in p.candidate_urls)


def test_planner_venue_steps():
    p = VerificationPlanner().plan(seed(SeedKind.VENUE_UNIT, "IIT Bombay"))
    assert "venue_page" in p.steps


def test_planner_community_hosts():
    p = VerificationPlanner().plan(seed(SeedKind.SIMILAR_ORGANIZER, "PyLadies Delhi"))
    assert any("pyladies-delhi" in u for u in p.candidate_urls)


def test_planner_search_query_default_to_target():
    s = ExpansionSeed(
        kind=SeedKind.CHAPTER_SIBLING,
        target="GDG X",
        target_key="gdg-x",
        source="o",
        reason="r",
        confidence=0.5,
        search_hint=None,
        path=RelationshipPath(nodes=["A", "GDG X"]),
    )
    assert VerificationPlanner().plan(s).search_query == "GDG X"


def test_planner_connected_slug_when_not_url():
    p = VerificationPlanner().plan(seed(SeedKind.CONNECTED_RESOURCE, "Some Resource"))
    assert p.candidate_urls[0].startswith("https://some-resource")


def test_strategy_series_evaluate():
    strat = VerificationPlanner().strategy_for(seed(SeedKind.SERIES_INSTANCE))
    ev = Evidence(reachable=True, events_found=2, city="Delhi")
    assert strat.evaluate(seed(), ev)[0] == 1.0


def test_strategy_sponsor_evaluate():
    strat = VerificationPlanner().strategy_for(seed(SeedKind.SPONSOR_PROGRAM))
    ev = Evidence(reachable=True, technologies=["AI"], organizer_name="Google")
    assert strat.evaluate(seed(), ev)[0] == 1.0


def test_strategy_evaluate_partial_score():
    strat = VerificationPlanner().strategy_for(seed(SeedKind.CHAPTER_SIBLING))
    ev = Evidence(reachable=True, organizer_name="X")  # organizer yes, city no
    assert strat.evaluate(seed(), ev)[0] == 0.5


def test_evidence_collect_merges_feeds_from_organizer():
    html = (
        '<html><head><meta property="og:site_name" content="GDG X">'
        '<link rel="alternate" type="application/rss+xml" href="https://x.dev/feed.xml">'
        "</head><body>Python meetup. Bangalore.</body></html>"
    )
    e = run(EvidenceCollector().collect("https://x.dev/", html, seed(target="GDG X")))
    assert e.feeds and e.organizer_name == "GDG X"


def test_evidence_collect_events_only():
    html = (
        '<html><body><script type="application/ld+json">{"@type":"Event",'
        '"name":"AI Conf","startDate":"2026-05-01"}</script></body></html>'
    )
    e = run(EvidenceCollector().collect("https://x.dev/e", html, seed()))
    assert e.events_found >= 1 and e.has_jsonld


def test_confidence_discovery_boost_multipage():
    single = VerificationConfidenceMerger().merge(
        seed_confidence=0.5, evidence=Evidence(reachable=True, pages_fetched=1)
    )
    multi = VerificationConfidenceMerger().merge(
        seed_confidence=0.5, evidence=Evidence(reachable=True, pages_fetched=2)
    )
    assert multi.components["discovery"] > single.components["discovery"]


def test_confidence_clips_seed():
    cs = VerificationConfidenceMerger().merge(
        seed_confidence=5.0, evidence=Evidence(reachable=True)
    )
    assert cs.components["seed"] == 1.0


def test_decision_verified_needs_core():
    # 2 content signals but neither event nor organizer → not verified
    ev = Evidence(reachable=True, city="X", technologies=["Py"])
    assert _decide(ev, 0.6, 1.0) is not VerificationDecision.VERIFIED


def test_decision_partial_reason_present():
    _, reasons = DecisionEngine().decide(
        Evidence(reachable=True, organizer_name="X"), conf(0.4), 0.5
    )
    assert reasons and "content signal" in reasons[0]


def test_decision_rejected_reason():
    _, reasons = DecisionEngine().decide(Evidence(reachable=True), conf(0.2), 0.0)
    assert "no relevant evidence" in reasons[0]


def test_retry_last_decision_recorded():
    st = RetryState("k")
    RetryPolicy().on_decision(st, VerificationDecision.VERIFIED, 0)
    assert st.last_decision == "verified"


def test_retry_partial_is_terminal():
    will, _ = RetryPolicy().on_decision(RetryState("k"), VerificationDecision.PARTIALLY_VERIFIED, 0)
    assert not will


def test_retry_cooldown_zero_immediate():
    will, st = RetryPolicy(cooldown_runs=0).on_decision(
        RetryState("k"), VerificationDecision.INSUFFICIENT_EVIDENCE, 3
    )
    assert will and st.next_run == 3


def test_builder_key_fallback_without_url():
    r = VerificationResult(
        "GDG X",
        "chapter_sibling",
        VerificationDecision.VERIFIED,
        conf(0.6),
        Evidence(reachable=True),
        VerificationPlan("chapter", "q"),
        timestamp=NOW,
    )
    c = CandidateBuilder().build(r, now=NOW)
    assert c.key == "validation:GDG X"


def test_builder_technology_and_india_confidence():
    c = CandidateBuilder().build(
        _result(technologies=["Python", "AI", "Cloud"], city="Delhi"), now=NOW
    )
    assert c.technology_confidence == 1.0 and c.india_confidence == 0.8


def test_builder_structured_score():
    c = CandidateBuilder().build(_result(events_found=1, has_jsonld=True), now=NOW)
    assert c.structured_data_score >= 1


def test_metrics_rejection_only():
    m = ValidationMetrics()
    r = _result(VerificationDecision.REJECTED)
    m.record(r)
    assert m.snapshot()["rejection_rate"] == 1.0 and m.snapshot()["acceptance_rate"] == 0.0


def test_metrics_empty_snapshot():
    assert ValidationMetrics().snapshot()["total"] == 0


def test_store_retry_upsert_overwrites():
    store = InMemoryValidationStore()
    run(store.save_retry(RetryState("k", attempts=1)))
    run(store.save_retry(RetryState("k", attempts=3)))
    assert run(store.load_retries())["k"].attempts == 3


def test_store_sqlite_audit_order():
    store = SQLiteValidationStore(":memory:")
    try:
        for i in range(3):
            run(
                store.save_audit(AuditRecord(f"t{i}", "k", "verified", 0.5, {}, [], [], None, "ts"))
            )
        audit = run(store.load_audit())
        assert [a.seed_target for a in audit] == ["t0", "t1", "t2"]
    finally:
        run(store.close())


def test_engine_validate_returns_plan_and_reasons():
    result = run(_engine().validate(seed(target="GDG Chennai")))
    assert result.plan.steps and any("strategy:" in r for r in result.reasons)


def test_engine_candidate_key_set_on_accept():
    result = run(_engine().validate(seed(target="GDG Chennai")))
    assert result.candidate_key is not None


def test_engine_no_searcher_no_templates_insufficient():
    inbox = InMemoryDiscoveryInbox()
    eng = SeedValidationEngine(inbox, StaticFetcher({}), clock=lambda: NOW)
    result = run(eng.validate(seed(target="Nonexistent Org")))
    assert result.decision is VerificationDecision.INSUFFICIENT_EVIDENCE


def test_engine_two_seeds_same_url_dedup():
    # two different seeds whose only resolving URL is the same page → inbox dedups by url key
    inbox = InMemoryDiscoveryInbox()
    fetcher = StaticFetcher({"https://shared.dev/": R("https://shared.dev/", RICH)})
    searcher = FixtureSearcher({"q1": ["https://shared.dev/"], "q2": ["https://shared.dev/"]})
    eng = SeedValidationEngine(inbox, fetcher, searcher=searcher, clock=lambda: NOW)
    run(eng.validate(seed(SeedKind.SIMILAR_ORGANIZER, "Org One", hint="q1")))
    r2 = run(eng.validate(seed(SeedKind.SIMILAR_ORGANIZER, "Org Two", hint="q2")))
    assert r2.inbox_outcome == "updated" and run(inbox.count()) == 1


def test_engine_batch_eligible_after_cooldown():
    eng = _engine(retry=RetryPolicy(max_retries=5, cooldown_runs=1))
    s = seed(SeedKind.CHAPTER_SIBLING, "Nowhere")
    run(eng.validate_batch([s]))  # run 1 → insufficient, next_run=2
    run(eng.validate_batch([]))  # run 2 (bump counter)
    report = run(eng.validate_batch([s]))  # run 3 ≥ next_run → eligible
    assert report.total == 1


def test_engine_audit_stored_per_validate():
    eng = _engine()
    run(eng.validate(seed(target="GDG Chennai")))
    run(eng.validate(seed(target="GDG Pune")))
    assert len(eng.audit) == 2


def test_engine_metrics_reject_and_accept():
    eng = _engine()
    run(
        eng.validate_batch(
            [
                seed(target="GDG Chennai"),
                seed(SeedKind.SIMILAR_ORGANIZER, "Ghost Org"),
            ]
        )
    )
    snap = eng.metrics.snapshot()
    assert snap["by_decision"]["verified"] == 1 and snap["by_decision"]["rejected"] == 1
