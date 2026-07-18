"""Event Lifecycle Engine + Registration Deadline Monitor.

Every event has a derived lifecycle state that updates automatically as time passes — it is
a pure function of the event's dates + stored status + `now`, computed on demand (nothing is
written back to the frozen Repository). Registration signals are proxied from `start_date`,
since the frozen Event model carries no registration deadline (Phase 5).

    UPCOMING → REGISTRATION_CLOSING → LIVE_TODAY → COMPLETED → ARCHIVED
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.intelligence.models import IntelligenceConfig, LifecycleState
from app.storage.models import EventStatus, StoredEvent

_DEFAULT_CONFIG = IntelligenceConfig()


def lifecycle_state(
    stored: StoredEvent, now: datetime, config: IntelligenceConfig = _DEFAULT_CONFIG
) -> LifecycleState:
    """The current lifecycle state of an event."""
    if stored.status is EventStatus.ARCHIVED:
        return LifecycleState.ARCHIVED

    today = now.date()
    event = stored.event
    end = event.end_date or event.start_date

    if end < today:
        if (today - end).days > config.archive_after_days:
            return LifecycleState.ARCHIVED
        return LifecycleState.COMPLETED
    if event.start_date <= today <= end:
        return LifecycleState.LIVE_TODAY
    if event.start_date <= today + timedelta(days=config.registration_closing_days):
        return LifecycleState.REGISTRATION_CLOSING
    return LifecycleState.UPCOMING


@dataclass(frozen=True)
class RegistrationStatus:
    closing_soon: bool
    closed: bool
    event_started: bool
    event_ended: bool


class RegistrationDeadlineMonitor:
    """Registration/deadline signals, proxied from the event start (no deadline field yet)."""

    def __init__(self, config: IntelligenceConfig = _DEFAULT_CONFIG) -> None:
        self._config = config

    def status(self, stored: StoredEvent, now: datetime) -> RegistrationStatus:
        today = now.date()
        event = stored.event
        end = event.end_date or event.start_date
        started = event.start_date <= today
        closing = (not started) and event.start_date <= today + timedelta(
            days=self._config.registration_closing_days
        )
        return RegistrationStatus(
            closing_soon=closing,
            closed=started,  # once it starts, registration is effectively closed
            event_started=started and today <= end,
            event_ended=end < today,
        )
