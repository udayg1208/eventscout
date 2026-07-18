"""Event Similarity — find related events from enrichment + graph signals.

Combines topic/technology/skill overlap (Jaccard over the enrichment feature set) with same-
category and same-community bonuses (community from the Phase-3F entity graph, if supplied).
Deterministic: ties break by key.
"""

from __future__ import annotations

from app.enrichment.models import EventEnrichment
from app.entities.graph import GraphStore
from app.entities.models import EdgeType
from app.storage.models import StoredEvent

_WEIGHTS = {"features": 0.6, "category": 0.25, "community": 0.15}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


class EventSimilarity:
    def __init__(
        self,
        enrichments: dict[str, EventEnrichment],
        events_by_key: dict[str, StoredEvent],
        *,
        graph: GraphStore | None = None,
    ) -> None:
        self._enrichments = enrichments
        self._events = events_by_key
        self._community = self._community_map(graph) if graph is not None else {}

    def _community_map(self, graph: GraphStore) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for event_node in graph.entities():
            if not event_node.id.startswith("event:"):
                continue
            hosts = graph.neighbors(event_node.id, type=EdgeType.HOSTED_BY, direction="out")
            if hosts:
                mapping[event_node.id.removeprefix("event:")] = hosts[0]
        return mapping

    def _category(self, key: str) -> str | None:
        stored = self._events.get(key)
        return stored.event.category.value if stored else None

    def similar_to(self, key: str, *, limit: int = 10) -> list[tuple[str, float]]:
        target = self._enrichments.get(key)
        if target is None:
            return []
        target_features = target.feature_set()
        target_category = self._category(key)
        target_community = self._community.get(key)

        results: list[tuple[str, float]] = []
        for other_key, other in self._enrichments.items():
            if other_key == key:
                continue
            features = _jaccard(target_features, other.feature_set())
            category = (
                1.0 if target_category and target_category == self._category(other_key) else 0.0
            )
            community = (
                1.0
                if target_community and target_community == self._community.get(other_key)
                else 0.0
            )
            score = (
                _WEIGHTS["features"] * features
                + _WEIGHTS["category"] * category
                + _WEIGHTS["community"] * community
            )
            if score > 0:
                results.append((other_key, round(score, 4)))

        results.sort(key=lambda kv: (-kv[1], kv[0]))
        return results[:limit]
