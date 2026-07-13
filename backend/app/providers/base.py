"""The provider interface every event source must implement.

The rest of the app depends only on this abstraction, never on a concrete source.
Adding Confs.tech / Devfolio / Luma later means implementing `search()` and nothing
else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.event import Event
from app.models.search import SearchQuery


class EventProvider(ABC):
    """Abstract event source.

    `search()` is async so that network-bound real providers (httpx) slot in with
    no signature change.
    """

    #: Short, stable identifier stamped onto every Event this provider returns.
    name: str = "base"

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Event]:
        """Return events matching `query`, already normalized to the Event model."""
        raise NotImplementedError
