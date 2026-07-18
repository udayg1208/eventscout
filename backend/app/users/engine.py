"""User Intelligence Engine — the facade that ties the user layer together.

Records interactions (learning the profile automatically), produces explained deterministic
recommendations, and reports per-user analytics. Reads the frozen catalog + Phase-5A
enrichment + Phase-3F entity graph + Phase-4D freshness/trending; writes only into its own
user stores. Nothing frozen is modified.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.enrichment.models import EventEnrichment
from app.entities.builder import GraphBuilder
from app.entities.graph import GraphStore
from app.entities.models import EdgeType
from app.intelligence.freshness import freshness_score
from app.intelligence.trending import TrendingEngine
from app.storage.models import SearchCriteria, StoredEvent
from app.storage.repository import EventRepository
from app.users.analytics import build_user_analytics
from app.users.attendance import AttendanceHistory
from app.users.features import event_features, query_features
from app.users.interactions import INTERACTION_WEIGHTS, InteractionLog
from app.users.models import Interaction, InteractionType, Recommendation, UserProfile
from app.users.profile import InMemoryUserProfileStore, UserProfileStore, apply_features
from app.users.recommend import RECOMMENDATION_WEIGHTS as W
from app.users.recommend import generate_reasons
from app.users.saved import SavedEventsStore

logger = logging.getLogger("users.engine")


class UserIntelligenceEngine:
    def __init__(
        self,
        events_by_key: dict[str, StoredEvent],
        enrichment: dict[str, EventEnrichment],
        graph: GraphStore,
        *,
        profiles: UserProfileStore | None = None,
        saved: SavedEventsStore | None = None,
        attendance: AttendanceHistory | None = None,
        log: InteractionLog | None = None,
    ) -> None:
        self._events = events_by_key
        self._enrichment = enrichment
        self._graph = graph
        self._profiles = profiles or InMemoryUserProfileStore()
        self._saved = saved or SavedEventsStore()
        self._attendance = attendance or AttendanceHistory()
        self._log = log or InteractionLog()
        self._shown: dict[str, set[str]] = {}
        self._community, self._organizer = self._entity_maps()
        self._trending = TrendingEngine()

    # --- projections of the entity graph ---

    def _entity_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        community, organizer = {}, {}
        for node in self._graph.entities():
            if not node.id.startswith("event:"):
                continue
            key = node.id.removeprefix("event:")
            hosts = self._graph.neighbors(node.id, type=EdgeType.HOSTED_BY, direction="out")
            orgs = self._graph.neighbors(node.id, type=EdgeType.ORGANIZED_BY, direction="out")
            if hosts and (entity := self._graph.get_entity(hosts[0])):
                community[key] = entity.name
            if orgs and (entity := self._graph.get_entity(orgs[0])):
                organizer[key] = entity.name
        return community, organizer

    def _features(self, key: str) -> dict[str, float]:
        stored = self._events.get(key)
        if stored is None:
            return {}
        return event_features(
            stored,
            self._enrichment.get(key),
            community=self._community.get(key),
            organizer=self._organizer.get(key),
        )

    # --- interactions (preference learning) ---

    def record_interaction(self, interaction: Interaction) -> UserProfile:
        self._log.record(interaction)
        profile = self._profiles.get_or_create(interaction.user_id)
        weight = INTERACTION_WEIGHTS.get(interaction.type, 0.0)

        if interaction.event_key:
            apply_features(profile, weight, self._features(interaction.event_key))
            self._side_effects(interaction, profile)
        elif interaction.query:
            apply_features(profile, weight, query_features(interaction.query))

        profile.interaction_count += 1
        profile.updated_at = interaction.at
        self._profiles.save(profile)
        return profile

    def _side_effects(self, interaction: Interaction, profile: UserProfile) -> None:
        user, key, t = interaction.user_id, interaction.event_key, interaction.type
        if t is InteractionType.SAVE:
            self._saved.save(user, key)
        elif t is InteractionType.UNSAVE:
            self._saved.unsave(user, key)
        elif t is InteractionType.REGISTER:
            self._attendance.register(user, key)
        elif t is InteractionType.ATTEND:
            self._attendance.mark_attended(user, key)
            profile.attended_count += 1

    # --- recommendations ---

    def recommend(self, user_id: str, *, now: datetime, limit: int = 10) -> list[Recommendation]:
        profile = self._profiles.get(user_id)
        if profile is None:
            return []
        engaged = self._saved.saved(user_id) | self._attendance.attended_keys(user_id)
        candidates = [
            s
            for key, s in self._events.items()
            if key not in engaged and s.event.start_date >= now.date()
        ]
        raw = {s.key: sum(profile.weight(f) for f in self._features(s.key)) for s in candidates}
        max_raw = max((v for v in raw.values() if v > 0), default=0.0)

        recs: list[Recommendation] = []
        for stored in candidates:
            features = self._features(stored.key)
            interest = raw[stored.key] / max_raw if max_raw > 0 and raw[stored.key] > 0 else 0.0
            similarity = self._similarity_to_engaged(stored.key, engaged)
            score = (
                W["interest"] * interest
                + W["freshness"] * freshness_score(stored, now)
                + W["trending"] * self._trending.score(stored, now)[0]
                + W["similarity"] * similarity
            )
            reasons = generate_reasons(profile, features, similar_to_engaged=similarity > 0)
            recs.append(Recommendation(stored.key, round(score, 4), reasons))

        recs.sort(key=lambda r: (-r.score, r.event_key))
        top = recs[:limit]
        self._shown.setdefault(user_id, set()).update(r.event_key for r in top)
        return top

    def _similarity_to_engaged(self, key: str, engaged: set[str]) -> float:
        target = self._enrichment.get(key)
        if target is None or not engaged:
            return 0.0
        target_features = target.feature_set()
        best = 0.0
        for other_key in engaged:
            other = self._enrichment.get(other_key)
            if other is None:
                continue
            other_features = other.feature_set()
            union = target_features | other_features
            if not union:
                continue
            best = max(best, len(target_features & other_features) / len(union))
        return best

    # --- analytics ---

    def analytics(self, user_id: str) -> dict:
        profile = self._profiles.get(user_id)
        if profile is None:
            return {}
        saved = self._saved.saved(user_id)
        attended = self._attendance.attended_keys(user_id)
        return build_user_analytics(
            profile=profile,
            saved=saved,
            attended_keys=attended,
            interaction_counts=self._log.counts_by_type(user_id),
            shown_recs=self._shown.get(user_id, set()),
            engaged_keys=saved | attended,
        )

    @property
    def profiles(self) -> UserProfileStore:
        return self._profiles

    @property
    def saved_store(self) -> SavedEventsStore:
        return self._saved

    @property
    def attendance(self) -> AttendanceHistory:
        return self._attendance

    # --- construction from the live platform ---

    @classmethod
    async def from_repository(cls, repo: EventRepository, **kwargs) -> UserIntelligenceEngine:
        """Build over the active catalog, deriving enrichment + entity graph."""
        from app.enrichment import EnrichmentPipeline

        events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
        events_by_key = {s.key: s for s in events}
        graph = GraphBuilder().build(events)
        pipeline = EnrichmentPipeline()
        pipeline.enrich_events(events, graph=graph)
        return cls(events_by_key, pipeline.store.all(), graph, **kwargs)
