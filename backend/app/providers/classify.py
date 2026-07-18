"""Content-based event classification (search intelligence).

Providers assign a reasonable *format* category, but generic community events land
in `meetup` even when they are clearly AI or startup events — leaving the `ai` and
`startup` categories empty (see GAP_ANALYSIS.md). This refines a generic `meetup`
event into a more specific category using high-precision keyword signals from its
title + description.

Policy (deliberate, to protect existing search):
- Only events labelled `meetup` are refined; provider-assigned specific categories
  (hackathon, conference, workshop, webinar) are preserved.
- Signals read only what the text says — nothing is invented.
"""

from __future__ import annotations

import re

from app.models.event import Event, EventCategory

# High-precision signals, checked in priority order. Topical (ai, startup) first so
# an AI community meetup is surfaced as `ai` rather than a generic meetup.
_SIGNALS: list[tuple[EventCategory, re.Pattern[str]]] = [
    (
        EventCategory.AI,
        re.compile(
            r"\bai\b|\ba\.i\.|artificial intelligence|machine learning|\bml\b|"
            r"deep learning|generative ai|gen ?ai|\bgenai\b|\bllms?\b|"
            r"large language models?|\bgpt\b|chatgpt|neural network|computer vision|"
            r"\bnlp\b|data science|\bmlops\b|hugging ?face|diffusion model|transformers?",
            re.I,
        ),
    ),
    (
        EventCategory.STARTUP,
        re.compile(
            r"\bstart[ -]?ups?\b|\bfounders?\b|\bentrepreneurs?\b|\bvc\b|"
            r"venture capital|\bpitch(es)?\b|demo day|\bincubators?\b|"
            r"\baccelerators?\b|angel investors?|seed funding|fundraising",
            re.I,
        ),
    ),
    (EventCategory.HACKATHON, re.compile(r"\bhack[ae]thons?\b|\bhack[ -]?day\b", re.I)),
    (
        EventCategory.WORKSHOP,
        re.compile(r"\bworkshops?\b|\bhands[ -]on\b|\bbootcamps?\b|\bmasterclass", re.I),
    ),
    (EventCategory.WEBINAR, re.compile(r"\bwebinars?\b", re.I)),
    (
        EventCategory.CONFERENCE,
        re.compile(r"\bconferences?\b|\bsummits?\b|\bdevfest\b|\bconventions?\b", re.I),
    ),
]

# Only the generic default is refined; specific provider categories are trusted.
_REFINABLE = {EventCategory.MEETUP}


def classify_category(event: Event) -> EventCategory:
    """Return a refined category for a generic event, else its existing category."""
    if event.category not in _REFINABLE:
        return event.category
    text = f"{event.title} {event.description or ''}"
    for category, pattern in _SIGNALS:
        if pattern.search(text):
            return category
    return event.category
