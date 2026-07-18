"""Future user-integration interfaces — defined, NOT implemented (per the spec).

Extension points for calendar sync, Gmail, LinkedIn, WhatsApp, push notifications, and an AI
Career Assistant. Nothing here is built in Phase 5B.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models.event import Event
from app.users.models import Recommendation, UserProfile


class CalendarSync(ABC):
    @abstractmethod
    async def add_event(self, user_id: str, event: Event) -> None: ...


class GmailIntegration(ABC):
    @abstractmethod
    async def infer_interests(self, user_id: str) -> dict[str, float]:
        """Enrich a profile from a user's mail (future — with explicit consent)."""


class LinkedInIntegration(ABC):
    @abstractmethod
    async def infer_profile(self, user_id: str) -> dict[str, float]: ...


class WhatsAppNotifier(ABC):
    @abstractmethod
    async def notify(self, user_id: str, message: str) -> None: ...


class PushNotifier(ABC):
    @abstractmethod
    async def push(self, user_id: str, title: str, body: str) -> None: ...


class AICareerAssistant(ABC):
    @abstractmethod
    async def advise(
        self, profile: UserProfile, recommendations: Sequence[Recommendation]
    ) -> str: ...
