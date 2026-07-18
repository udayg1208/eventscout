"""Deduplication: normalization, similarity, merge choice, and the 8 dedup scenarios."""

from __future__ import annotations

from datetime import date

from app.models.event import Event, EventCategory
from app.providers.dedup import (
    choose_best_event,
    deduplicate,
    event_similarity,
    normalize_title,
    normalize_url,
    title_similarity,
    url_similarity,
)

DAY = date(2026, 9, 1)


def _event(
    title,
    *,
    start=DAY,
    provider="a",
    city=None,
    url=None,
    description=None,
    price=None,
    is_free=None,
    location=None,
):
    return Event(
        title=title,
        url=url or f"https://{provider}.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        description=description,
        price=price,
        is_free=is_free,
        location=location,
        start_date=start,
        category=EventCategory.MEETUP,
        provider=provider,
    )


# --------------------------- normalization ---------------------------


def test_normalize_title_strips_punct_and_case():
    assert normalize_title("Gen-AI Meetup!!!") == "gen ai meetup"
    assert normalize_title("  GenAI   MEETUP ") == "genai meetup"


def test_normalize_url_drops_www_query_slash():
    assert normalize_url("https://www.lu.ma/abc/") == "lu.ma/abc"
    assert normalize_url("https://lu.ma/abc?utm=x#f") == "lu.ma/abc"
    assert normalize_url("https://LU.MA/ABC") == "lu.ma/abc"


# --------------------------- similarity ---------------------------


def test_title_similarity_high_for_variants_low_for_different():
    assert title_similarity("GenAI Meetup", "Gen AI Meetup") >= 0.85
    assert title_similarity("DevOps Meetup", "Machine Learning Bootcamp") < 0.6


def test_url_similarity_equal_and_different():
    assert url_similarity("https://lu.ma/x", "https://lu.ma/x/") == 1.0
    assert url_similarity("https://lu.ma/x", "https://gdg.dev/completely-other") < 0.5


def test_event_similarity_gates():
    base = _event("AI Summit", city="Bangalore")
    assert event_similarity(base, _event("AI Summit", city="Bangalore", provider="b")) >= 0.85
    # different date -> 0
    assert event_similarity(base, _event("AI Summit", start=date(2026, 12, 1))) == 0.0
    # different city -> 0
    assert event_similarity(base, _event("AI Summit", city="Delhi")) == 0.0
    # identical URL -> 1.0 even with a different title
    same_url = "https://lu.ma/xyz"
    assert (
        event_similarity(_event("Title One", url=same_url), _event("Title Two", url=same_url))
        == 1.0
    )


# --------------------------- choose_best_event ---------------------------


def test_choose_best_keeps_richest():
    sparse = _event("PyConf", provider="gdg")
    rich = _event("PyConf", provider="fossunited", description="d", is_free=True, location="V")
    assert choose_best_event([sparse, rich]) is rich
    assert choose_best_event([rich, sparse]) is rich  # order-independent


# --------------------------- the 8 dedup scenarios ---------------------------


def test_punctuation_differences_merge():
    events = [_event("Gen AI Meetup", provider="a"), _event("Gen-AI Meetup!", provider="b")]
    assert len(deduplicate(events)) == 1


def test_case_differences_merge():
    events = [_event("AI Summit", provider="a"), _event("ai summit", provider="b")]
    assert len(deduplicate(events)) == 1


def test_bengaluru_vs_bangalore_merge():
    events = [
        _event("Cloud Meetup", provider="a", city="Bengaluru"),
        _event("Cloud Meetup", provider="b", city="Bangalore"),
    ]
    assert len(deduplicate(events)) == 1


def test_url_differences_still_merge_same_event():
    events = [
        _event("PyData Delhi", provider="a", url="https://a.com/x"),
        _event("PyData Delhi", provider="b", url="https://b.com/y"),
    ]
    assert len(deduplicate(events)) == 1


def test_provider_duplicates_keep_richest():
    events = [
        _event("DevFest", provider="gdg"),
        _event("DevFest", provider="fossunited", description="d", is_free=True),
    ]
    result = deduplicate(events)
    assert len(result) == 1
    assert result[0].provider == "fossunited"


def test_false_positive_protection_distinct_events():
    events = [
        _event("Cloud Security Meetup", provider="a"),
        _event("Frontend Development Workshop", provider="b"),
    ]
    assert len(deduplicate(events)) == 2


def test_same_title_different_cities_not_merged():
    events = [
        _event("AI Meetup", provider="a", city="Bangalore"),
        _event("AI Meetup", provider="b", city="Delhi"),
    ]
    assert len(deduplicate(events)) == 2


def test_same_title_different_dates_not_merged():
    events = [
        _event("AI Meetup", provider="a", start=date(2026, 7, 1)),
        _event("AI Meetup", provider="b", start=date(2026, 8, 1)),
    ]
    assert len(deduplicate(events)) == 2


def test_deterministic_and_preserves_distinct():
    events = [_event("Alpha"), _event("Beta"), _event("Gamma")]
    assert {e.title for e in deduplicate(events)} == {"Alpha", "Beta", "Gamma"}
