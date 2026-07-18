"""Content-based classification: refine generic meetups, preserve specific categories."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.event import Event, EventCategory
from app.providers.classify import classify_category


def _event(title, category=EventCategory.MEETUP, description=None):
    return Event(
        title=title,
        description=description,
        url="https://example.com/e",
        start_date=date(2026, 8, 1),
        category=category,
        provider="t",
    )


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Gemma x Hugging Face Bengaluru Meetup", EventCategory.AI),
        ("GenAI Builders Meetup", EventCategory.AI),
        ("Intro to Machine Learning", EventCategory.AI),
        ("Startup Founders Mixer", EventCategory.STARTUP),
        ("Pitch Night for Early-stage Founders", EventCategory.STARTUP),
        ("Django Hands-on Workshop", EventCategory.WORKSHOP),
        ("Cloud Native Webinar", EventCategory.WEBINAR),
        ("DevFest Bangalore", EventCategory.CONFERENCE),
        ("Rust Bangalore Meetup", EventCategory.MEETUP),  # no signal -> stays
        ("Email Marketing Basics", EventCategory.MEETUP),  # 'email' must NOT trigger AI
        ("Retail Analytics 101", EventCategory.MEETUP),  # 'retail' must NOT trigger AI
    ],
)
def test_generic_meetups_are_refined(title, expected):
    assert classify_category(_event(title)) == expected


@pytest.mark.parametrize(
    "title, category",
    [
        ("AI Hackathon 2026", EventCategory.HACKATHON),  # provider format preserved
        ("Applied AI Conference", EventCategory.CONFERENCE),
        ("Machine Learning Workshop", EventCategory.WORKSHOP),
    ],
)
def test_specific_provider_categories_are_preserved(title, category):
    assert classify_category(_event(title, category=category)) == category


def test_ai_takes_priority_over_startup():
    assert classify_category(_event("AI Startup Founders Meetup")) == EventCategory.AI
