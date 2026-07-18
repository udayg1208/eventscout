"""Future Hooks — extension-point interfaces only (NO implementation, per the spec).

The Background Intelligence Pipeline calls `IntelligenceHook.on_report` after each run.
Concrete channels (notifications, recommendations, saved searches, email, WhatsApp,
calendar) will implement these interfaces later — nothing here is built now.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.intelligence.models import IntelligenceReport
from app.models.event import Event


class IntelligenceHook(ABC):
    """Notified with each fresh report — the single extension point the engine invokes."""

    @abstractmethod
    async def on_report(self, report: IntelligenceReport) -> None: ...


# --- future channel/consumer interfaces (defined, never implemented in 4D) ---


class NotificationChannel(ABC):
    """A delivery channel (email / push / in-app)."""

    @abstractmethod
    async def notify(self, recipient: str, subject: str, body: str) -> None: ...


class EmailAlert(NotificationChannel):
    """Marker interface for the email delivery channel (future)."""


class WhatsAppAlert(NotificationChannel):
    """Marker interface for the WhatsApp delivery channel (future)."""


class Recommender(ABC):
    """Personalized recommendations from a user profile + candidate events (future)."""

    @abstractmethod
    def recommend(self, user_profile: dict, events: Sequence[Event]) -> list[str]: ...


class SavedSearchMatcher(ABC):
    """Match a new/updated event against a user's saved search (future)."""

    @abstractmethod
    def matches(self, saved_search: dict, event: Event) -> bool: ...


class CalendarReminder(ABC):
    """Produce a calendar reminder for an event a user saved (future)."""

    @abstractmethod
    def build_reminder(self, event: Event) -> dict: ...
