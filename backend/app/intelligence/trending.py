"""Trending Engine.

Ranks events by a deterministic blend of the signals available today: source quality,
freshness, popularity (content richness — no engagement data yet), and update frequency
(`version`). Designed so future user-engagement signals plug in via `EngagementSignal`
without changing the engine.

Not available today (documented): cross-provider appearance is lost after write-time
deduplication (one canonical record per event); it becomes a real signal only if ingestion
records duplicate-cluster size (future).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.intelligence.freshness import freshness_score
from app.intelligence.models import IntelligenceConfig, TrendingEvent
from app.models.event import Event
from app.providers.ranking import completeness, score_source
from app.storage.models import StoredEvent

_DEFAULT_CONFIG = IntelligenceConfig()

_WEIGHTS = {"source": 0.35, "freshness": 0.30, "popularity": 0.20, "update_frequency": 0.15}


class EngagementSignal(ABC):
    """Future plug-in: contributes an additive 0..1 boost from user engagement (clicks,
    saves, applications). No implementation today — the engine simply has none."""

    name = "engagement"

    @abstractmethod
    def value(self, event: Event) -> float: ...


class TrendingEngine:
    def __init__(
        self,
        config: IntelligenceConfig = _DEFAULT_CONFIG,
        *,
        signals: list[EngagementSignal] | None = None,
    ) -> None:
        self._config = config
        self._signals = signals or []

    def score(self, stored: StoredEvent, now: datetime) -> tuple[float, dict[str, float]]:
        event = stored.event
        breakdown = {
            "source": score_source(event),
            "freshness": freshness_score(stored, now, self._config),
            "popularity": min(1.0, completeness(event) / 6),
            "update_frequency": min(1.0, (stored.version - 1) / 3),
        }
        score = sum(_WEIGHTS[k] * v for k, v in breakdown.items())
        for signal in self._signals:  # additive future boost (none today)
            boost = signal.value(event)
            breakdown[signal.name] = boost
            score += boost
        return round(score, 4), breakdown

    def top(self, events: list[StoredEvent], now: datetime) -> list[TrendingEvent]:
        """Trending events (upcoming only), best-first, deterministic."""
        scored: list[TrendingEvent] = []
        for stored in events:
            if stored.event.start_date < now.date():
                continue  # trending is forward-looking
            score, breakdown = self.score(stored, now)
            scored.append(TrendingEvent(stored.key, stored.event.title, score, breakdown))
        scored.sort(key=lambda t: (-t.score, t.key))
        return scored[: self._config.trending_top_n]
