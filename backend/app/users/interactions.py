"""Interaction weights + the interaction log.

Interactions are weighted by strength (attending an event says far more than viewing it;
ignoring/unsaving are negative signals). The log keeps the raw history for analytics.
"""

from __future__ import annotations

from collections import Counter

from app.users.models import Interaction, InteractionType

# Strength of each signal (attend ≫ save ≫ click ≫ view; ignore/unsave are negative).
INTERACTION_WEIGHTS: dict[InteractionType, float] = {
    InteractionType.ATTEND: 5.0,
    InteractionType.REGISTER: 3.0,
    InteractionType.SAVE: 3.0,
    InteractionType.CLICK: 1.5,
    InteractionType.VIEW: 1.0,
    InteractionType.SEARCH: 1.0,
    InteractionType.IGNORE: -1.0,
    InteractionType.UNSAVE: -2.0,
}


class InteractionLog:
    """In-memory history of interactions (storage-independent; persistable later)."""

    def __init__(self) -> None:
        self._by_user: dict[str, list[Interaction]] = {}

    def record(self, interaction: Interaction) -> None:
        self._by_user.setdefault(interaction.user_id, []).append(interaction)

    def for_user(self, user_id: str) -> list[Interaction]:
        return list(self._by_user.get(user_id, []))

    def counts_by_type(self, user_id: str) -> dict[str, int]:
        counter: Counter[str] = Counter(i.type.value for i in self._by_user.get(user_id, []))
        return dict(counter)
