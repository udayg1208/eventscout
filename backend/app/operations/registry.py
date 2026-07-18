"""Production registry records (Phase 7B) — additive; does NOT modify the ingestion Registry.

A `ProductionRegistration` is the operations-layer record of a provider that has been promoted from
a `PromotionPlan`: its identity, provider type, capabilities, schedule knobs, current production
state, and a full transition history. This is a *control-plane* record — it never mutates
`app/ingestion/registry.py` or creates a provider implementation. State advances through the
controlled promotion flow (preflight → registered → scheduled → canary → active / rolled_back).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ProductionState(StrEnum):
    PENDING = "pending"
    FAILED_PREFLIGHT = "failed_preflight"
    REGISTERED = "registered"
    SCHEDULED = "scheduled"
    CANARY = "canary"  # every provider starts here — small sync, health-evaluated
    ACTIVE = "active"  # canary healthy → serving in the live ecosystem
    ROLLED_BACK = "rolled_back"  # canary/continuous health failed → withdrawn (history kept)
    RETIRED = "retired"  # gracefully removed later


ACTIVE_STATES = frozenset({ProductionState.CANARY, ProductionState.ACTIVE})


def provider_id_for(domain: str) -> str:
    return "op-" + domain.replace(".", "-").replace("/", "-").strip("-")


@dataclass
class ProductionRegistration:
    provider_id: str
    domain: str
    url: str
    provider_type: str
    capabilities: list[str]
    refresh_interval_hours: int
    expected_volume: str
    risk_level: str
    plan: dict  # the PromotionPlan.as_dict() (provenance — nothing opaque)
    state: ProductionState = ProductionState.PENDING
    canary_syncs: int = 0
    active_syncs: int = 0
    registered_at: datetime | None = None
    updated_at: datetime | None = None
    history: list[dict] = field(default_factory=list)
    version: int = 1

    def record(self, to: ProductionState, reason: str, now: datetime | None) -> dict:
        entry = {
            "from": self.state.value,
            "to": to.value,
            "reason": reason,
            "at": now.isoformat() if now else None,
        }
        self.history.append(entry)
        self.state = to
        self.updated_at = now
        self.version += 1
        return entry

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "domain": self.domain,
            "url": self.url,
            "provider_type": self.provider_type,
            "capabilities": list(self.capabilities),
            "refresh_interval_hours": self.refresh_interval_hours,
            "expected_volume": self.expected_volume,
            "risk_level": self.risk_level,
            "state": self.state.value,
            "canary_syncs": self.canary_syncs,
            "active_syncs": self.active_syncs,
            "history": list(self.history),
            "version": self.version,
            "plan": self.plan,
        }


def registration_from_plan(plan, *, now: datetime) -> ProductionRegistration:
    """Build a REGISTERED-track record from a 7A PromotionPlan (state starts PENDING)."""
    return ProductionRegistration(
        provider_id=provider_id_for(plan.domain),
        domain=plan.domain,
        url=plan.url,
        provider_type=plan.provider_type,
        capabilities=list(plan.capabilities),
        refresh_interval_hours=plan.refresh_interval_hours,
        expected_volume=plan.expected_volume,
        risk_level=plan.risk_assessment.get("level", "unknown"),
        plan=plan.as_dict(),
        registered_at=now,
        updated_at=now,
    )
