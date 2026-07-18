"""Organizer health (Phase 10C) — active / dormant / inactive / seasonal / new.

Classifies an organizer from its event history + expected cadence, deterministically (no ML). New:
just appeared. Active: hosted within ~1.5 cadence periods. Seasonal: sparse-but-regular (annual/
quarterly) and between occurrences. Dormant: overdue by a few periods. Inactive: long silent.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median

from app.organizers.models import Cadence, Health, cadence_days


def _period_days(dates: list[datetime], cadence: Cadence) -> float:
    base = cadence_days(cadence)
    if base:
        return float(base)
    if len(dates) >= 2:
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if gaps:
            return float(median(gaps))
    return 45.0  # default ~monthly-ish when unknown


def classify_health(event_dates: list[datetime], cadence: Cadence, now: datetime) -> Health:
    dates = sorted(d for d in event_dates)
    if not dates:
        return Health.NEW
    last = dates[-1]
    days_since = (now - last).days
    period = _period_days(dates, cadence)
    n = len(dates)

    if days_since < 0:  # a future event is scheduled → active
        return Health.ACTIVE
    if n == 1:
        return Health.NEW if days_since <= period * 2 else Health.INACTIVE
    if days_since <= period * 1.5:
        return Health.ACTIVE
    if cadence in (Cadence.ANNUAL, Cadence.QUARTERLY) and days_since <= period * 2:
        return Health.SEASONAL
    if days_since <= period * 3:
        return Health.DORMANT
    return Health.INACTIVE
