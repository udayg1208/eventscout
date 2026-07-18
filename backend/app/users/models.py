"""User Intelligence domain models.

Users are understood the way events are: as weighted **preference features** learned from
interactions. Everything is stored separately from the frozen Event model. Deterministic —
interactions carry explicit timestamps; nothing here is random or network-bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class InteractionType(StrEnum):
    SEARCH = "search"
    VIEW = "view"
    CLICK = "click"
    SAVE = "save"
    UNSAVE = "unsave"
    REGISTER = "register"
    ATTEND = "attend"
    IGNORE = "ignore"  # shown but dismissed → negative signal


class AttendanceStatus(StrEnum):
    REGISTERED = "registered"
    ATTENDED = "attended"
    MISSED = "missed"  # registered but the event ended un-attended
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Interaction:
    user_id: str
    type: InteractionType
    at: datetime
    event_key: str | None = None  # for event interactions
    query: str | None = None  # for search interactions


@dataclass
class UserProfile:
    """A user's evolving preferences as weighted, namespaced features
    (``"topic:LLMs"`` → 8.0). Preferred cities/topics/… are the top weights per namespace."""

    user_id: str
    preferences: dict[str, float] = field(default_factory=dict)
    interaction_count: int = 0
    attended_count: int = 0
    updated_at: datetime | None = None

    def weight(self, feature: str) -> float:
        return self.preferences.get(feature, 0.0)

    def top(self, namespace: str, limit: int = 5) -> list[tuple[str, float]]:
        prefix = f"{namespace}:"
        items = [
            (k[len(prefix) :], v)
            for k, v in self.preferences.items()
            if k.startswith(prefix) and v > 0
        ]
        items.sort(key=lambda kv: (-kv[1], kv[0]))
        return items[:limit]

    @property
    def budget_preference(self) -> str:
        free, paid = self.weight("budget:free"), self.weight("budget:paid")
        if free > paid and free > 0:
            return "free"
        if paid > free and paid > 0:
            return "paid"
        return "any"

    @property
    def preferred_format(self) -> str:
        online, offline = self.weight("format:online"), self.weight("format:offline")
        if online > offline and online > 0:
            return "online"
        if offline > online and offline > 0:
            return "offline"
        return "any"


@dataclass(frozen=True)
class AttendanceRecord:
    user_id: str
    event_key: str
    status: AttendanceStatus
    at: datetime


@dataclass(frozen=True)
class Recommendation:
    event_key: str
    score: float
    reasons: list[str]
