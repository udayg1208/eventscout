"""City normalization + its effect on filtering."""

from __future__ import annotations

from datetime import date

import pytest

from app.city import detect_city, normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.filtering import matches


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Bengaluru", "Bangalore"),
        ("bengaluru", "Bangalore"),
        ("Bombay", "Mumbai"),
        ("New Delhi", "Delhi"),
        ("Gurugram", "Gurgaon"),
        ("Bangalore", "Bangalore"),
        ("  Bengaluru  ", "Bangalore"),
        ("Unknownville", "Unknownville"),  # unknown -> unchanged
        (None, None),
    ],
)
def test_normalize_city(raw, expected):
    assert normalize_city(raw) == expected


def _event(city: str) -> Event:
    return Event(
        title="X",
        url="https://example.com/x",
        city=city,
        start_date=date(2026, 8, 1),
        category=EventCategory.CONFERENCE,
        provider="t",
    )


def test_filter_matches_across_city_aliases():
    # Event spelled "Bengaluru" must match a "Bangalore" query and vice versa.
    assert matches(_event("Bengaluru"), SearchQuery(city="Bangalore")) is True
    assert matches(_event("Bangalore"), SearchQuery(city="Bengaluru")) is True
    assert matches(_event("Mumbai"), SearchQuery(city="Bangalore")) is False


@pytest.mark.parametrize(
    "texts, expected",
    [
        (("Bangalore",), "Bangalore"),
        (("Held in New Delhi",), "Delhi"),  # longest alias wins
        (("FOSS United Bengaluru",), "Bangalore"),  # normalized
        (("Coimbatore Institute of Technology",), None),  # not a known city
        (("Asap room", None), None),
        ((), None),
    ],
)
def test_detect_city(texts, expected):
    assert detect_city(*texts) == expected
