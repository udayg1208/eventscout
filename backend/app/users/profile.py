"""User Profile Engine + Preference Learning + profile store.

A profile evolves automatically: each interaction folds the interacted event's (or query's)
features into the profile, scaled by the interaction's strength. Positive signals raise
preferences; ignore/unsave lower them. No manual retraining — the profile *is* the running
weighted sum.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.users.models import UserProfile


def apply_features(profile: UserProfile, weight: float, features: dict[str, float]) -> None:
    """Fold `features` into the profile, scaled by the interaction `weight` (may be negative)."""
    for feature, feature_weight in features.items():
        profile.preferences[feature] = (
            profile.preferences.get(feature, 0.0) + weight * feature_weight
        )


class UserProfileStore(ABC):
    @abstractmethod
    def get(self, user_id: str) -> UserProfile | None: ...

    @abstractmethod
    def get_or_create(self, user_id: str) -> UserProfile: ...

    @abstractmethod
    def save(self, profile: UserProfile) -> None: ...


class InMemoryUserProfileStore(UserProfileStore):
    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}

    def get(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def get_or_create(self, user_id: str) -> UserProfile:
        profile = self._profiles.get(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self._profiles[user_id] = profile
        return profile

    def save(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile
