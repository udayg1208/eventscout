"""Public Social & Community Discovery (Phase 8D).

Discovers events announced on **publicly accessible** community platforms — LinkedIn public pages,
GitHub (discussions/releases/orgs/READMEs), Discord/Telegram public landing pages, Notion public
pages, blogs (Medium/Dev.to/Hashnode/Substack/WordPress/Blogger), and forums (Discourse/phpBB/
Flarum/Vanilla). Public content only: no login, no auth bypass, no browser, no LLM. Every field is
provenance-bearing (reusing D4's model); UNKNOWN is always preferred over a guess.

Strictly additive and discovery-only: no changes to Search, the Repository, the Catalog, D1–D4, the
Expansion Engine (8C), Onboarding, Production, the scheduler, the frontend, or the API. Output stops
at the Discovery Inbox (`discovered_by="social"`, `status=NEW`).
"""

from app.discovery.social.engine import SocialDiscoveryEngine, SocialDiscoveryReport
from app.discovery.social.extractor import (
    build_common,
    jsonld_events,
    safety_check,
    technologies,
)
from app.discovery.social.models import (
    EVENT_FIELDS,
    ExtractedField,
    FieldStatus,
    Provenance,
    SocialExtraction,
    SocialPlatform,
    SocialPriority,
)
from app.discovery.social.normalizer import to_candidate
from app.discovery.social.priority import WEIGHTS, score
from app.discovery.social.store import (
    InMemorySocialStore,
    SocialRecord,
    SocialStore,
    SQLiteSocialStore,
)

__all__ = [
    # engine
    "SocialDiscoveryEngine",
    "SocialDiscoveryReport",
    # models
    "SocialPlatform",
    "SocialExtraction",
    "SocialPriority",
    "ExtractedField",
    "Provenance",
    "FieldStatus",
    "EVENT_FIELDS",
    # extraction / scoring
    "build_common",
    "jsonld_events",
    "technologies",
    "safety_check",
    "score",
    "WEIGHTS",
    "to_candidate",
    # store
    "SocialStore",
    "InMemorySocialStore",
    "SQLiteSocialStore",
    "SocialRecord",
]
