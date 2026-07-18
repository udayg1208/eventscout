"""Phase 6G / D4 — AI Discovery tests. Deterministic, no network (MockAIExtractor + fixtures)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.discovery import FeedType, InMemoryDiscoveryInbox, SQLiteDiscoveryInbox
from app.discovery.ai import (
    AIDiscoveryPipeline,
    Decision,
    ExtractionInput,
    FieldStatus,
    InMemoryAIExtractionStore,
    MockAIClassifier,
    MockAIExtractor,
    SourceClass,
    compute_confidence,
    search_score_from_rank,
    validate,
)
from app.discovery.ai.models import ExtractionMethod
from app.discovery.fetch import FetchResult

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def extractor() -> MockAIExtractor:
    return MockAIExtractor(clock=lambda: NOW)


# ---- fixtures: prose pages D1/D2 cannot parse (no feeds/JSON-LD/framework) ----

PROSE_TECH = (
    "<html><title>PyData Bangalore</title><body>"
    "PyData Bangalore is a community meetup. Organized by PyData Bangalore. "
    "We run Python and AI workshops every month in Bangalore, Karnataka, India, for developers "
    "and data scientists. Register at https://pydata.org/register to RSVP."
    "</body></html>"
)
PROSE_NO_CITY = (
    "<html><title>Async Python Deep Dive</title><body>"
    "A hands-on Python and asyncio workshop for engineers. No venue announced yet."
    "</body></html>"
)
CONCERT = (
    "<html><title>Sunburn Festival Goa</title><body>"
    "Live music concert and DJ night. Book concert tickets and movie passes now!"
    "</body></html>"
)
SHOPPING = (
    "<html><title>Big Billion Sale</title><body>"
    "Huge shopping deals and discounts. Add to cart and buy now for the best offers."
    "</body></html>"
)
TRAVEL = (
    "<html><title>Goa Tourism</title><body>"
    "Book hotels and holiday travel packages. Tourism and sightseeing trips."
    "</body></html>"
)
EMPTY = "<html><title>About Us</title><body>We are a company. Contact us for details.</body></html>"
STRUCTURED = (
    "<html><title>Tech Conf</title><head>"
    '<script type="application/ld+json">{"@type":"Event","name":"AI Summit"}</script>'
    "</head><body>AI conference in Bangalore, India.</body></html>"
)


def _in(url, html, title=None):
    return ExtractionInput(url=url, text=html, title=title)


def _fetch(url, html, ct="text/html"):
    return FetchResult(url=url, status=200, content_type=ct, text=html)


# --------------------------- extraction ---------------------------


def test_extraction_populates_fields_with_provenance():
    ex = extractor().extract(_in("https://pydata.org/blr", PROSE_TECH, "PyData Bangalore"))
    assert "Python" in ex.technologies.value
    assert ex.city.value == "Bangalore" and ex.country.value == "India"
    assert ex.state.value == "Karnataka"
    assert ex.community.value == "PyData"
    assert ex.recurring.value is True and ex.event_frequency.value == "monthly"
    assert "developers" in ex.audience.value
    assert ex.registration_links.value  # captured the RSVP URL
    # every KNOWN field carries full provenance
    for name, f in ex.known_fields().items():
        assert f.provenance is not None, name
        assert f.provenance.source_snippet and f.provenance.reason
        assert 0.0 < f.provenance.confidence <= 1.0
        assert f.provenance.method is ExtractionMethod.AI
        assert f.provenance.timestamp == NOW


def test_extraction_never_fabricates_unknown_fields():
    ex = extractor().extract(_in("https://x.org/py", PROSE_NO_CITY, "Async Python Deep Dive"))
    assert ex.technologies.is_known  # Python present
    # no city/community/organizer in the text → UNKNOWN, value None, no provenance (never guessed)
    assert ex.city.status is FieldStatus.UNKNOWN and ex.city.value is None
    assert ex.community.status is FieldStatus.UNKNOWN
    assert ex.organizer.status is FieldStatus.UNKNOWN
    assert ex.city.provenance is None


def test_extraction_partial():
    ex = extractor().extract(_in("https://x.org/py", PROSE_NO_CITY))
    known = ex.known_fields()
    assert "technologies" in known and "event_types" in known
    assert "city" not in known and "organizer" not in known  # genuinely partial


def test_country_is_inferred_not_extracted():
    # India is not stated, but a known Indian city is → country INFERRED (never EXTRACTED)
    html = "<html><body>A Python meetup in Bangalore for developers.</body></html>"
    ex = extractor().extract(_in("https://x.org", html))
    assert ex.country.value == "India"
    assert ex.country.status is FieldStatus.INFERRED


# --------------------------- classification ---------------------------


def test_classification_tech_and_labels():
    ex = extractor().extract(_in("https://pydata.org/blr", PROSE_TECH, "PyData Bangalore"))
    cl = MockAIClassifier().classify(_in("u", PROSE_TECH, "PyData Bangalore"), ex)
    assert cl.primary is SourceClass.TECH and cl.is_tech is True
    labels = {ceil.label for ceil in cl.labels}
    assert SourceClass.COMMUNITY in labels and SourceClass.WORKSHOP in labels
    assert all(0.0 <= ceil.confidence <= 1.0 and ceil.reason for ceil in cl.labels)


def test_classification_non_tech_when_no_tech_signal():
    ex = extractor().extract(_in("https://x.in/goa", CONCERT, "Sunburn"))
    cl = MockAIClassifier().classify(_in("u", CONCERT, "Sunburn"), ex)
    assert cl.is_tech is False
    assert cl.primary is SourceClass.NON_TECH


# --------------------------- validator ---------------------------


def test_validator_rejects_offtopic():
    for html, title in [(CONCERT, "Sunburn"), (SHOPPING, "Sale"), (TRAVEL, "Tourism")]:
        ex = extractor().extract(_in("https://x.in", html, title))
        v = validate(_in("https://x.in", html, title), ex)
        assert v.passed is False and v.rejected_reasons


def test_validator_rejects_insufficient_evidence():
    ex = extractor().extract(_in("https://x.org/about", EMPTY, "About Us"))
    v = validate(_in("https://x.org/about", EMPTY, "About Us"), ex)
    assert v.passed is False
    assert any("insufficient evidence" in r for r in v.rejected_reasons)


def test_validator_passes_tech_and_soft_override():
    ex = extractor().extract(_in("https://pydata.org/blr", PROSE_TECH, "PyData Bangalore"))
    v = validate(_in("u", PROSE_TECH, "PyData Bangalore"), ex)
    assert v.passed is True and v.evidence
    # "festival" (soft reject) is overridden by a strong tech signal
    tech_fest = (
        "<html><body>Python AI festival and hackathon workshop in Pune, India.</body></html>"
    )
    ex2 = extractor().extract(_in("u", tech_fest))
    assert validate(_in("u", tech_fest), ex2).passed is True


# --------------------------- confidence engine ---------------------------


def test_confidence_combines_and_normalizes():
    c = compute_confidence(deterministic=0.9, ai=0.5, structured=1.0)
    assert 0.0 < c.total <= 1.0 and len(c.components) == 3
    # absent families are excluded (not zero): a pure-AI page scores its AI value
    only_ai = compute_confidence(ai=0.8)
    assert only_ai.total == 0.8
    assert compute_confidence().total == 0.0  # nothing available


def test_search_score_from_rank():
    assert search_score_from_rank(1) == 1.0
    assert search_score_from_rank(None) is None
    assert search_score_from_rank(3) < search_score_from_rank(2)


# --------------------------- pipeline: deterministic-first ---------------------------


def test_pipeline_defers_when_structured_present():
    inbox = InMemoryDiscoveryInbox()
    pipe = AIDiscoveryPipeline(extractor(), MockAIClassifier(), inbox, clock=lambda: NOW)
    out = run(pipe.process(_fetch("https://conf.org/", STRUCTURED)))
    assert out.decision is Decision.DETERMINISTIC_SUFFICIENT
    assert out.used_ai is False
    assert run(inbox.count()) == 0  # D1/D2 own it; D4 adds nothing


def test_pipeline_accepts_prose_and_stores_provenance():
    inbox = InMemoryDiscoveryInbox()
    store = InMemoryAIExtractionStore()
    pipe = AIDiscoveryPipeline(
        extractor(), MockAIClassifier(), inbox, store=store, min_confidence=0.4, clock=lambda: NOW
    )
    out = run(pipe.process(_fetch("https://pydata.org/blr", PROSE_TECH), search_rank=2))
    assert out.decision is Decision.AI_ACCEPTED and out.used_ai is True
    cand = run(inbox.get("https://pydata.org/blr"))
    assert cand.feed_type is FeedType.AI_EXTRACTED and cand.discovered_by == "ai"
    assert cand.city == "Bangalore" and cand.country == "India"
    assert cand.classification == "tech"
    assert cand.discovery_confidence is not None and cand.discovery_confidence >= 0.4
    # full provenance audit persisted
    rec = run(store.get("https://pydata.org/blr"))
    assert rec is not None and rec.confidence.total == cand.discovery_confidence


def test_pipeline_rejects_offtopic_no_candidate():
    inbox = InMemoryDiscoveryInbox()
    store = InMemoryAIExtractionStore()
    pipe = AIDiscoveryPipeline(
        extractor(), MockAIClassifier(), inbox, store=store, clock=lambda: NOW
    )
    out = run(pipe.process(_fetch("https://sunburn.in/goa", CONCERT)))
    assert out.decision is Decision.AI_REJECTED
    assert run(inbox.count()) == 0  # rejected → never a candidate
    assert run(store.count()) == 1  # but recorded for audit


def test_pipeline_batch_report_and_sqlite_roundtrip():
    inbox = SQLiteDiscoveryInbox()
    pipe = AIDiscoveryPipeline(
        extractor(), MockAIClassifier(), inbox, min_confidence=0.4, clock=lambda: NOW
    )
    pages = [
        _fetch("https://pydata.org/blr", PROSE_TECH),
        _fetch("https://sunburn.in/goa", CONCERT),
        _fetch("https://shop.in/sale", SHOPPING),
        _fetch("https://conf.org/", STRUCTURED),
    ]
    report = run(pipe.run(pages, ranks={"https://pydata.org/blr": 1}))
    assert report.processed == 4
    assert report.deterministic_sufficient == 1  # STRUCTURED
    assert report.accepted >= 1  # PROSE_TECH
    assert report.rejected >= 2  # concert + shopping
    assert report.inserted == report.accepted

    # SQLite round-trip of the AI provenance fields on the candidate
    got = run(inbox.get("https://pydata.org/blr"))
    assert got.discovered_by == "ai" and got.feed_type is FeedType.AI_EXTRACTED
    assert got.classification == "tech" and got.discovery_confidence is not None
    run(inbox.close())
