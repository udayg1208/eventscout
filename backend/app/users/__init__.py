"""User Intelligence Platform — understand users as well as events.

Additive, deterministic personalization: evolving user profiles learned from weighted
interactions, saved events / collections, attendance history, and explained recommendations
built from event understanding (5A) + entity affinity (3F) + freshness/trending (4D). Stored
separately from the frozen Event model; modifies nothing frozen. Calendar/Gmail/LinkedIn/
WhatsApp/Push/AI-assistant integrations are interfaces only.
"""

from app.users.attendance import AttendanceHistory
from app.users.engine import UserIntelligenceEngine
from app.users.interactions import INTERACTION_WEIGHTS, InteractionLog
from app.users.models import (
    AttendanceRecord,
    AttendanceStatus,
    Interaction,
    InteractionType,
    Recommendation,
    UserProfile,
)
from app.users.profile import InMemoryUserProfileStore, UserProfileStore, apply_features
from app.users.recommend import generate_reasons
from app.users.saved import SavedEventsStore

__all__ = [
    "UserIntelligenceEngine",
    "UserProfile",
    "UserProfileStore",
    "InMemoryUserProfileStore",
    "apply_features",
    "Interaction",
    "InteractionType",
    "INTERACTION_WEIGHTS",
    "InteractionLog",
    "SavedEventsStore",
    "AttendanceHistory",
    "AttendanceStatus",
    "AttendanceRecord",
    "Recommendation",
    "generate_reasons",
]
