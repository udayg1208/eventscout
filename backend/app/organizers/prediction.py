"""Opportunity prediction (Phase 10C) — will this organizer host again soon?

Deterministic recurrence reasoning (no ML): from the event history + cadence, project the next
expected date and rate the probability of an upcoming announcement. E.g. "hosts monthly, last event
34 days ago → due now → high probability of an upcoming announcement". Explained, never a black
box.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.organizers.health import _period_days
from app.organizers.models import Cadence


@dataclass
class Opportunity:
    probability: str  # "high" | "medium" | "low" | "none"
    expected_next: datetime | None
    reason: str

    def as_dict(self) -> dict:
        return {
            "probability": self.probability,
            "expected_next": self.expected_next.date().isoformat() if self.expected_next else None,
            "reason": self.reason,
        }


def predict_opportunity(
    event_dates: list[datetime], cadence: Cadence, now: datetime
) -> Opportunity:
    dates = sorted(event_dates)
    if not dates:
        return Opportunity("none", None, "no event history yet — cannot project")
    last = dates[-1]
    period = _period_days(dates, cadence)
    expected_next = last + timedelta(days=period)

    if now < last:
        return Opportunity("low", expected_next, "an event is already scheduled ahead")
    elapsed = (now - last).days
    cad = cadence.value if cadence is not Cadence.UNKNOWN else f"~{int(period)}d"

    if elapsed < period * 0.75:
        return Opportunity(
            "low",
            expected_next,
            f"hosted {elapsed}d ago; next {cad} occurrence expected around {expected_next.date()}",
        )
    if elapsed <= period * 2:
        return Opportunity(
            "high",
            expected_next,
            f"usually hosts {cad}; last event {elapsed}d ago → due now → "
            "high probability of an upcoming announcement",
        )
    return Opportunity(
        "medium",
        expected_next,
        f"overdue ({elapsed}d since last {cad} event) — may resume but trending dormant",
    )
