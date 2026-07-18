"""EventScout Platform — the public orchestration layer (Phase 6A).

One facade, `PlatformService`, unifies Search (4B), Intelligence (4D), User Intelligence
(5B), AI Understanding (5A), the Entity Graph (3F), and the Repository into a single public
surface: homepage, browse, discovery, event details, entity profiles, recommendations,
search, and analytics. It contains **no business logic** — it delegates to the existing
engines and maps every result to a DTO, so internal models never cross the boundary.

Submodules:
  - `dto`        — public response shapes + internal→DTO mappers
  - `filters`    — pure catalog selection/discovery predicates (reuse lifecycle/enrichment)
  - `service`    — `PlatformService`, the single orchestration facade
  - `interfaces` — future surfaces (mobile / public API / GraphQL / partner / AI / calendar / voice)
"""

from app.platform.dto import (
    AIMetadataDTO,
    AnalyticsDTO,
    EntityProfileDTO,
    EventDetailDTO,
    EventDTO,
    HomepageDTO,
    RecommendationDTO,
)
from app.platform.service import PlatformService

__all__ = [
    "PlatformService",
    "EventDTO",
    "AIMetadataDTO",
    "EntityProfileDTO",
    "EventDetailDTO",
    "RecommendationDTO",
    "HomepageDTO",
    "AnalyticsDTO",
]
