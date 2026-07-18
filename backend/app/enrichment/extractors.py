"""Deterministic extraction functions — the building blocks of enrichment.

Each is a pure function of the event's text (+ category). Topics/technologies come from the
taxonomy regexes; skills/audiences/careers are derived from the detected topics + category;
difficulty from signal words; the summary from a fixed template. No LLM, no network.
"""

from __future__ import annotations

from app.enrichment.models import Difficulty
from app.enrichment.taxonomy import (
    TECHNOLOGIES,
    TOPIC_AUDIENCES,
    TOPIC_CAREERS,
    TOPIC_SKILLS,
    TOPICS,
    difficulty_from_text,
)
from app.models.event import Event


def _text(event: Event) -> str:
    return f"{event.title} {event.description or ''}"


def _dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-duplication (deterministic output)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def extract_topics(event: Event) -> list[str]:
    text = _text(event)
    return [name for name, pattern in TOPICS if pattern.search(text)]


def extract_technologies(event: Event) -> list[str]:
    text = _text(event)
    return [name for name, pattern in TECHNOLOGIES if pattern.search(text)]


def infer_skills(event: Event, topics: list[str]) -> list[str]:
    skills = [skill for topic in topics for skill in TOPIC_SKILLS.get(topic, [])]
    category = event.category.value
    if category in {"conference", "meetup"}:
        skills.append("Networking")
    if category in {"workshop", "hackathon", "webinar"}:
        skills.append("Hands-on Building")
    return _dedupe(skills)


def detect_audiences(event: Event, topics: list[str], difficulty: Difficulty) -> list[str]:
    audiences = [aud for topic in topics for aud in TOPIC_AUDIENCES.get(topic, [])]
    if event.category.value == "hackathon":
        audiences += ["Students", "Developers"]
    if difficulty is Difficulty.BEGINNER:
        audiences.append("Students")
    return _dedupe(audiences) or ["Developers"]


def estimate_difficulty(event: Event) -> Difficulty:
    return difficulty_from_text(_text(event), category=event.category.value)


def career_relevance(topics: list[str]) -> list[str]:
    return _dedupe([career for topic in topics for career in TOPIC_CAREERS.get(topic, [])])


def generate_summary(
    event: Event,
    *,
    topics: list[str],
    technologies: list[str],
    audiences: list[str],
    difficulty: Difficulty,
) -> str:
    parts = [f"A {difficulty.value}-level {event.category.value}"]
    if topics:
        parts.append(" on " + ", ".join(topics[:3]))
    if technologies:
        parts.append(" featuring " + ", ".join(technologies[:3]))
    if audiences:
        parts.append(f", aimed at {', '.join(audiences[:2])}")
    if event.city:
        parts.append(f", in {event.city}")
    return "".join(parts) + "."
