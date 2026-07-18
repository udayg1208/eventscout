"""Shared title -> category helper."""

from __future__ import annotations

import pytest

from app.models.event import EventCategory
from app.providers.categorize import category_from_title


@pytest.mark.parametrize(
    "title, default, expected",
    [
        ("July 2026 Rustacean Meetup", EventCategory.CONFERENCE, EventCategory.MEETUP),
        ("Frappe Framework Workshop", EventCategory.MEETUP, EventCategory.WORKSHOP),
        ("The Fifth Elephant Annual Conference", EventCategory.MEETUP, EventCategory.CONFERENCE),
        ("Global AI Summit", EventCategory.MEETUP, EventCategory.CONFERENCE),
        ("HackDay", EventCategory.MEETUP, EventCategory.MEETUP),  # no keyword -> default
        ("AI Networking Evening", EventCategory.CONFERENCE, EventCategory.CONFERENCE),
    ],
)
def test_category_from_title(title, default, expected):
    assert category_from_title(title, default=default) == expected
