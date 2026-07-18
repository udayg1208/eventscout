"""Feature extraction — turn an event (or a search query) into namespaced preference features.

Reuses the frozen catalog + the Phase-5A enrichment + the Phase-3F entity graph. Features are
the shared vocabulary between events and user profiles: ``"topic:LLMs"``, ``"city:Bangalore"``,
``"community:Google Developer Groups"``, ``"format:offline"``, ``"budget:free"``, etc.
"""

from __future__ import annotations

from app.city import detect_city, normalize_city
from app.enrichment.models import EventEnrichment
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS
from app.storage.models import StoredEvent


def event_features(
    stored: StoredEvent,
    enrichment: EventEnrichment | None,
    *,
    community: str | None = None,
    organizer: str | None = None,
) -> dict[str, float]:
    """The feature set of one event (all weights 1.0)."""
    event = stored.event
    features: dict[str, float] = {f"category:{event.category.value}": 1.0}
    if event.city:
        features[f"city:{normalize_city(event.city)}"] = 1.0
    features["format:online" if event.is_online else "format:offline"] = 1.0
    if event.is_free is True:
        features["budget:free"] = 1.0
    elif event.is_free is False:
        features["budget:paid"] = 1.0
    if enrichment is not None:
        for topic in enrichment.topics:
            features[f"topic:{topic}"] = 1.0
        for tech in enrichment.technologies:
            features[f"tech:{tech}"] = 1.0
        for audience in enrichment.audiences:
            features[f"audience:{audience}"] = 1.0
        features[f"difficulty:{enrichment.difficulty.value}"] = 1.0
    if community:
        features[f"community:{community}"] = 1.0
    if organizer:
        features[f"organizer:{organizer}"] = 1.0
    return features


def query_features(query: str) -> dict[str, float]:
    """Features inferred from a search query's text (topics/technologies/city)."""
    features: dict[str, float] = {}
    for name, pattern in TOPICS:
        if pattern.search(query):
            features[f"topic:{name}"] = 1.0
    for name, pattern in TECHNOLOGIES:
        if pattern.search(query):
            features[f"tech:{name}"] = 1.0
    city = detect_city(query)
    if city:
        features[f"city:{normalize_city(city)}"] = 1.0
    return features
