"""Organizer Intelligence engine (Phase 10C) — build & expand the Organizer Graph.

Ingests organizer pages/events, resolves each to a canonical identity (merging aliases),
materialises the ecosystem (chapter parent, university, series, sponsors, calendars, feeds, social
channels), and answers confidence / health / opportunity / similarity queries. `link_similar`
connects organizers into the community & series graphs. Incremental: re-ingesting an alias merges
into the same node. Deterministic; no network, no browser, no LLM; nothing is written to the
catalog.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.organizers.confidence import OrganizerConfidence, OrganizerConfidenceScore
from app.organizers.extract import OrganizerExtractor
from app.organizers.health import classify_health
from app.organizers.identity import canonical_key
from app.organizers.models import (
    Cadence,
    Health,
    Node,
    OrganizerGraph,
    OrganizerProfile,
    RelationType,
)
from app.organizers.prediction import Opportunity, predict_opportunity
from app.organizers.relationships import RelationshipDiscoverer
from app.organizers.series import detect_series, dominant_cadence
from app.organizers.similarity import CommunitySimilarity, SimilarityScore
from app.organizers.store import GraphStore


def _org_id(name: str) -> str:
    return f"org:{canonical_key(name)}"


class OrganizerIntelligenceEngine:
    def __init__(
        self,
        graph: OrganizerGraph | None = None,
        *,
        extractor: OrganizerExtractor | None = None,
        relationships: RelationshipDiscoverer | None = None,
        confidence: OrganizerConfidence | None = None,
        similarity: CommunitySimilarity | None = None,
        store: GraphStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.graph = graph or OrganizerGraph()
        self._extractor = extractor or OrganizerExtractor()
        self._rel = relationships or RelationshipDiscoverer()
        self._conf = confidence or OrganizerConfidence()
        self._sim = similarity or CommunitySimilarity()
        self._store = store
        self._clock = clock
        self._profiles: dict[str, OrganizerProfile] = {}
        self._events: dict[str, list[datetime]] = {}
        self._cadence: dict[str, Cadence] = {}

    # -- ingest -------------------------------------------------------------

    def ingest(self, url: str, html: str, *, hint_name: str | None = None) -> str | None:
        return self._add(self._extractor.extract(url, html, hint_name=hint_name))

    def ingest_organizer(self, name: str, *, text: str = "", url: str = "") -> str | None:
        html = f"<html><body><h1>{name}</h1>{text}</body></html>"
        return self._add(self._extractor.extract(url, html, hint_name=name))

    def _add(self, profile: OrganizerProfile) -> str | None:
        name = profile.get("name")
        if not name:
            return None
        oid = _org_id(name)
        merged = self._merge(self._profiles.get(oid), profile)
        self._profiles[oid] = merged

        attrs: dict = {}
        for k in ("chapter", "city", "university", "community", "technologies"):
            if merged.get(k):
                attrs[k] = merged.get(k)
        self.graph.add_node(
            Node(
                oid,
                merged.node_type,
                name,
                attributes=attrs,
                aliases=set(merged.get("aliases") or [name]),
            )
        )

        series_names = merged.get("series") or []
        joined = " ".join(series_names)
        self._cadence[oid] = dominant_cadence(joined, detect_series(joined))
        self._rel.expand(self.graph, oid, merged)
        return oid

    @staticmethod
    def _merge(prev: OrganizerProfile | None, new: OrganizerProfile) -> OrganizerProfile:
        if prev is None:
            return new
        fields = dict(prev.fields)
        for name, ef in new.fields.items():
            cur = fields.get(name)
            if cur is None or (ef.is_known and ef.confidence > cur.confidence):
                fields[name] = ef
        node_type = new.node_type if new.node_type.value != "organization" else prev.node_type
        return OrganizerProfile(fields=fields, node_type=node_type)

    def record_events(self, org_id: str, dates: list[datetime]) -> None:
        self._events.setdefault(org_id, []).extend(dates)

    # -- queries ------------------------------------------------------------

    def profile(self, org_id: str) -> OrganizerProfile | None:
        return self._profiles.get(org_id)

    def organizer_ids(self) -> list[str]:
        return list(self._profiles.keys())

    def confidence(self, org_id: str) -> OrganizerConfidenceScore:
        return self._conf.score(
            self._profiles[org_id], event_count=len(self._events.get(org_id, []))
        )

    def health(self, org_id: str, now: datetime | None = None) -> Health:
        return classify_health(
            self._events.get(org_id, []),
            self._cadence.get(org_id, Cadence.UNKNOWN),
            now or self._clock(),
        )

    def predict(self, org_id: str, now: datetime | None = None) -> Opportunity:
        return predict_opportunity(
            self._events.get(org_id, []),
            self._cadence.get(org_id, Cadence.UNKNOWN),
            now or self._clock(),
        )

    def similarity(self, a_id: str, b_id: str) -> SimilarityScore:
        return self._sim.score(self._profiles[a_id], self._profiles[b_id])

    def link_similar(self, *, threshold: float = 0.5) -> int:
        """Connect similar organizers into the community/series graphs. Returns edges added."""
        ids = self.organizer_ids()
        added = 0
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                s = self.similarity(a, b)
                if s.total >= threshold:
                    self.graph.add_edge(
                        _edge(a, b, RelationType.SAME_COMMUNITY, f"similarity {s.total:.2f}")
                    )
                    added += 1
                    if s.components.get("same_series", 0) > 0:
                        self.graph.add_edge(_edge(a, b, RelationType.SAME_SERIES, "shared series"))
                        added += 1
        return added

    def community_graph(self) -> OrganizerGraph:
        return self.graph.community_view()

    def series_graph(self) -> OrganizerGraph:
        return self.graph.series_view()

    # -- persistence --------------------------------------------------------

    async def persist(self) -> None:
        if self._store is not None:
            await self._store.save(self.graph)

    async def load_from_store(self) -> bool:
        if self._store is None:
            return False
        g = await self._store.load()
        if g is None:
            return False
        self.graph = g
        return True


def _edge(a: str, b: str, relation: RelationType, reason: str):
    from app.organizers.models import Edge

    return Edge(a, b, relation, reason)
