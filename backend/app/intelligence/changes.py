"""Event Change Detector.

Compares the previous run's snapshot (key → fingerprint) with the current catalog and
classifies what changed: newly discovered, updated, cancelled (withdrawn), expired, and —
for updated events — venue / cost / date changes. Deterministic: same inputs, same output.
The pipeline persists the new snapshot for the next run's comparison.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.intelligence.models import Change, ChangeSet, ChangeType, EventFingerprint
from app.storage.models import EventStatus, StoredEvent


def fingerprint(stored: StoredEvent) -> EventFingerprint:
    e = stored.event
    return EventFingerprint(
        key=stored.key,
        content_hash=stored.content_hash,
        status=stored.status.value,
        version=stored.version,
        title=e.title,
        location=e.location,
        is_free=e.is_free,
        price=e.price,
        start_date=e.start_date,
        end_date=e.end_date,
    )


def snapshot(events: Iterable[StoredEvent]) -> dict[str, EventFingerprint]:
    return {stored.key: fingerprint(stored) for stored in events}


def detect_changes(
    previous: dict[str, EventFingerprint], current: Iterable[StoredEvent]
) -> ChangeSet:
    """Classify changes between the previous snapshot and the current catalog."""
    changes = ChangeSet()
    for stored in current:
        prev = previous.get(stored.key)
        current_fp = fingerprint(stored)

        if prev is None:
            changes.new.append(Change(stored.key, ChangeType.NEW, current_fp.title))
            continue

        if current_fp.status == EventStatus.WITHDRAWN.value != prev.status:
            changes.cancelled.append(Change(stored.key, ChangeType.CANCELLED, current_fp.title))
            continue
        if current_fp.status == EventStatus.EXPIRED.value != prev.status:
            changes.expired.append(Change(stored.key, ChangeType.EXPIRED, current_fp.title))
            continue

        if current_fp.content_hash != prev.content_hash:
            changes.updated.append(Change(stored.key, ChangeType.UPDATED, current_fp.title))
            if current_fp.location != prev.location:
                changes.venue_changed.append(
                    Change(
                        stored.key,
                        ChangeType.VENUE_CHANGED,
                        f"{prev.location} → {current_fp.location}",
                    )
                )
            if (current_fp.is_free, current_fp.price) != (prev.is_free, prev.price):
                changes.cost_changed.append(
                    Change(
                        stored.key, ChangeType.COST_CHANGED, f"{prev.price} → {current_fp.price}"
                    )
                )
            if (current_fp.start_date, current_fp.end_date) != (prev.start_date, prev.end_date):
                changes.date_changed.append(
                    Change(
                        stored.key,
                        ChangeType.DATE_CHANGED,
                        f"{prev.start_date} → {current_fp.start_date}",
                    )
                )
    return changes
