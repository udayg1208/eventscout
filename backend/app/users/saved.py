"""Saved Events Engine — save / unsave / collections / favorites.

Stored separately from the Event (only event keys are kept). Storage-independent (in-memory
today, persistable later).
"""

from __future__ import annotations

from collections import defaultdict

_DEFAULT = "default"
_FAVORITES = "favorites"


class SavedEventsStore:
    def __init__(self) -> None:
        # user -> collection -> set of event keys
        self._collections: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def save(self, user_id: str, event_key: str, *, collection: str = _DEFAULT) -> None:
        self._collections[user_id][collection].add(event_key)

    def unsave(self, user_id: str, event_key: str, *, collection: str | None = None) -> None:
        collections = self._collections.get(user_id, {})
        targets = [collection] if collection else list(collections)
        for name in targets:
            collections.get(name, set()).discard(event_key)

    def favorite(self, user_id: str, event_key: str) -> None:
        self.save(user_id, event_key, collection=_FAVORITES)

    def saved(self, user_id: str) -> set[str]:
        """Every saved key across all collections."""
        return (
            set().union(*self._collections.get(user_id, {}).values())
            if user_id in self._collections
            else set()
        )

    def favorites(self, user_id: str) -> set[str]:
        return set(self._collections.get(user_id, {}).get(_FAVORITES, set()))

    def collections(self, user_id: str) -> dict[str, set[str]]:
        return {name: set(keys) for name, keys in self._collections.get(user_id, {}).items()}
