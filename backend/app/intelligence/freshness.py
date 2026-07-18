"""Event Freshness Engine.

Computes a 0..1 freshness score per event and the boolean signals the product surfaces:
recently added, recently updated, trending soon, ending soon. Blends discovery recency
(`first_seen_at`), update recency (`version`/`last_seen_at`), and start proximity — all
relative to an explicit `now`, so it is deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.intelligence.models import FreshnessScore, IntelligenceConfig
from app.storage.models import StoredEvent

_DEFAULT_CONFIG = IntelligenceConfig()


def _decay(days: float, half_life: float) -> float:
    """1.0 at 0 days, 0.5 at `half_life`, → 0 as days grow. Clamped at 0 for negatives."""
    return 1.0 / (1.0 + max(0.0, days) / half_life)


def freshness_score(
    stored: StoredEvent, now: datetime, config: IntelligenceConfig = _DEFAULT_CONFIG
) -> float:
    half_life = config.freshness_half_life_days
    discovery_days = (now - stored.first_seen_at).total_seconds() / 86400
    discovery = _decay(discovery_days, half_life)

    start_days = (stored.event.start_date - now.date()).days
    proximity = _decay(start_days, half_life) if start_days >= 0 else 0.0

    updated = 1.0 if stored.version > 1 else 0.0
    return round(0.5 * discovery + 0.4 * proximity + 0.1 * updated, 4)


class FreshnessEngine:
    def __init__(self, config: IntelligenceConfig = _DEFAULT_CONFIG) -> None:
        self._config = config

    def evaluate(self, stored: StoredEvent, now: datetime) -> FreshnessScore:
        c = self._config
        today = now.date()
        start_days = (stored.event.start_date - today).days
        end = stored.event.end_date or stored.event.start_date
        end_days = (end - today).days
        return FreshnessScore(
            key=stored.key,
            score=freshness_score(stored, now, c),
            recently_added=(now - stored.first_seen_at) <= timedelta(days=c.recently_added_days),
            recently_updated=stored.version > 1
            and (now - stored.last_seen_at) <= timedelta(days=c.recently_added_days),
            trending_soon=0 <= start_days <= c.trending_soon_days,
            ending_soon=0 <= end_days <= c.ending_soon_days,
        )
