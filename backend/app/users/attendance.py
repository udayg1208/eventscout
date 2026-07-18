"""Attendance History — registered / attended / missed / cancelled.

The stored status reflects the user's explicit action (register / attend / cancel); the
*derived* status applies the deterministic event lifecycle — a still-"registered" event that
has ended becomes MISSED. Uses only the event's dates + `now`, so it is reproducible.
"""

from __future__ import annotations

from datetime import datetime

from app.models.event import Event
from app.users.models import AttendanceRecord, AttendanceStatus


class AttendanceHistory:
    def __init__(self) -> None:
        self._status: dict[str, dict[str, AttendanceStatus]] = {}

    def _set(self, user_id: str, event_key: str, status: AttendanceStatus) -> None:
        self._status.setdefault(user_id, {})[event_key] = status

    def register(self, user_id: str, event_key: str) -> None:
        self._set(user_id, event_key, AttendanceStatus.REGISTERED)

    def mark_attended(self, user_id: str, event_key: str) -> None:
        self._set(user_id, event_key, AttendanceStatus.ATTENDED)

    def cancel(self, user_id: str, event_key: str) -> None:
        self._set(user_id, event_key, AttendanceStatus.CANCELLED)

    def raw_status(self, user_id: str, event_key: str) -> AttendanceStatus | None:
        return self._status.get(user_id, {}).get(event_key)

    @staticmethod
    def derive(raw: AttendanceStatus, event: Event, now: datetime) -> AttendanceStatus:
        if raw is AttendanceStatus.REGISTERED:
            end = event.end_date or event.start_date
            if end < now.date():
                return AttendanceStatus.MISSED
        return raw

    def attended_keys(self, user_id: str) -> set[str]:
        return {
            key
            for key, status in self._status.get(user_id, {}).items()
            if status is AttendanceStatus.ATTENDED
        }

    def records(
        self, user_id: str, events_by_key: dict[str, object], now: datetime
    ) -> list[AttendanceRecord]:
        result: list[AttendanceRecord] = []
        for key, raw in self._status.get(user_id, {}).items():
            stored = events_by_key.get(key)
            status = self.derive(raw, stored.event, now) if stored else raw
            result.append(AttendanceRecord(user_id, key, status, now))
        return result
