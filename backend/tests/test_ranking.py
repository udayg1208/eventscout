"""Ranking: per-component scores + integration ordering scenarios."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.ranking import (
    WEIGHTS,
    completeness,
    rank,
    score_completeness,
    score_date,
    score_event,
    score_location,
    score_popularity,
    score_query_relevance,
    score_source,
)

TODAY = date(2026, 7, 1)


def _event(
    title,
    *,
    start=TODAY + timedelta(days=10),
    category=EventCategory.MEETUP,
    city=None,
    description=None,
    location=None,
    end_date=None,
    price=None,
    is_free=None,
    is_online=False,
    provider="t",
):
    return Event(
        title=title,
        description=description,
        url="https://example.com/" + title.replace(" ", "-").lower(),
        city=city,
        location=location,
        is_online=is_online,
        start_date=start,
        end_date=end_date,
        category=category,
        is_free=is_free,
        price=price,
        provider=provider,
    )


# --------------------------- weights ---------------------------


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


# --------------------------- score_query_relevance ---------------------------


def test_relevance_keyword_in_title():
    q = SearchQuery(keywords=["python"])
    assert score_query_relevance(_event("Python Summit"), q) == 1.0
    assert score_query_relevance(_event("Java Meetup"), q) == 0.0


def test_relevance_category_match():
    q = SearchQuery(categories=[EventCategory.AI])
    assert score_query_relevance(_event("X", category=EventCategory.AI), q) == 1.0
    assert score_query_relevance(_event("X", category=EventCategory.MEETUP), q) == 0.0


def test_relevance_zero_without_query_signal():
    assert score_query_relevance(_event("Anything"), SearchQuery()) == 0.0


# --------------------------- score_date ---------------------------


def test_date_today_is_one_and_past_is_zero():
    assert score_date(_event("x", start=TODAY), TODAY) == 1.0
    assert score_date(_event("x", start=TODAY - timedelta(days=5)), TODAY) == 0.0


def test_date_half_life_at_30_days():
    assert score_date(_event("x", start=TODAY + timedelta(days=30)), TODAY) == 0.5


# --------------------------- score_location ---------------------------


def test_location_exact_online_and_miss():
    q = SearchQuery(city="Bangalore")
    assert score_location(_event("x", city="Bengaluru"), q) == 1.0  # normalized match
    assert score_location(_event("x", is_online=True), q) == 0.5
    assert score_location(_event("x", city="Delhi"), q) == 0.0
    assert score_location(_event("x", city="Delhi"), SearchQuery()) == 0.0


# --------------------------- score_source ---------------------------


def test_source_quality_lookup():
    assert score_source(_event("x", provider="fossunited")) == 1.0
    assert score_source(_event("x", provider="gdg")) == 0.6
    assert score_source(_event("x", provider="unknown")) == 0.5


# --------------------------- score_popularity / completeness ---------------------------


def test_popularity_rewards_richness():
    rich = _event(
        "x",
        description="d" * 200,
        is_free=True,
        location="Venue",
        end_date=TODAY + timedelta(days=11),
    )
    assert score_popularity(rich) == 1.0
    assert score_popularity(_event("x")) == 0.0


def test_completeness_counts_fields():
    full = _event(
        "x",
        city="Pune",
        description="d",
        location="V",
        end_date=TODAY + timedelta(days=11),
        price="Free",
        is_free=True,
    )
    assert completeness(full) == 6
    assert score_completeness(full) == 1.0
    assert completeness(_event("x")) == 0


def test_score_event_in_unit_range():
    e = _event(
        "Python AI Summit",
        city="Bangalore",
        description="d" * 50,
        is_free=True,
        provider="fossunited",
    )
    s = score_event(e, SearchQuery(keywords=["python"], city="Bangalore"), TODAY)
    assert 0.0 <= s <= 1.0


# --------------------------- integration ordering ---------------------------


def test_ai_relevant_events_rank_first():
    q = SearchQuery(keywords=["machine learning"])
    java = _event("Java Meetup", start=TODAY + timedelta(days=1))  # sooner, irrelevant
    ml = _event("Machine Learning Summit", start=TODAY + timedelta(days=60))  # relevant, distant
    assert rank([java, ml], q, TODAY)[0].title == "Machine Learning Summit"


def test_city_matching_events_prioritized():
    q = SearchQuery(city="Bangalore")
    delhi = _event("A", city="Delhi")
    blr = _event("B", city="Bengaluru")
    assert rank([delhi, blr], q, TODAY)[0].title == "B"


def test_upcoming_ranks_above_distant():
    distant = _event("Distant", start=TODAY + timedelta(days=90))
    soon = _event("Soon", start=TODAY + timedelta(days=2))
    assert rank([distant, soon], SearchQuery(), TODAY)[0].title == "Soon"


def test_rich_ranks_above_sparse():
    same = TODAY + timedelta(days=10)
    rich = _event(
        "Rich",
        start=same,
        description="d" * 200,
        is_free=True,
        location="V",
        end_date=same + timedelta(days=1),
    )
    sparse = _event("Sparse", start=same)
    assert rank([sparse, rich], SearchQuery(), TODAY)[0].title == "Rich"


def test_source_quality_breaks_ties_only_when_relevance_similar():
    same = TODAY + timedelta(days=10)
    # Identical except provider -> higher source quality wins.
    good = _event("Alpha", start=same, provider="fossunited")
    weak = _event("Beta", start=same, provider="gdg")
    assert rank([weak, good], SearchQuery(), TODAY)[0].provider == "fossunited"

    # But relevance dominates: a low-source relevant event beats a high-source irrelevant one.
    q = SearchQuery(keywords=["python"])
    relevant_weak = _event("Python Meetup", start=same, provider="gdg")
    irrelevant_strong = _event("Java Meetup", start=same, provider="fossunited")
    assert rank([irrelevant_strong, relevant_weak], q, TODAY)[0].title == "Python Meetup"
