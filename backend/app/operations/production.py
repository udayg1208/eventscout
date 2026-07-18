"""Production promotion primitives (Phase 7B) — preflight + canary.

Preflight validates a PromotionPlan before anything is registered — promotion **never bypasses
validation**. The canary system runs a small first sync and evaluates its health; only a healthy
canary earns ACTIVE, otherwise the provider rolls back. The canary *sync* is an injectable seam
(`CanarySync`): 7B ships a deterministic `MockCanarySync` (no network, no real provider); a real
runner-backed canary is the deferred `RealCanarySync` in `interfaces.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.operations.registry import ProductionRegistration


@dataclass
class PreflightResult:
    passed: bool
    checks: dict[str, bool]
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks, "reasons": list(self.reasons)}


def preflight(plan) -> PreflightResult:
    """Validate a PromotionPlan is safe to register. Never bypassed."""
    checks = {
        "has_url": bool(plan.url),
        "has_domain": bool(plan.domain),
        "provider_type_known": plan.provider_type not in ("manual", "", None),
        "refresh_interval_sane": 1 <= plan.refresh_interval_hours <= 168,
        "has_capabilities": bool(plan.capabilities),
        "risk_not_blocking": plan.risk_assessment.get("level") != "blocked",
    }
    reasons = [f"preflight failed: {name}" for name, ok in checks.items() if not ok]
    return PreflightResult(passed=all(checks.values()), checks=checks, reasons=reasons)


# ------------------------------ canary ------------------------------


@dataclass(frozen=True)
class CanaryMetrics:
    """Result of a small canary sync (evidence for the health decision)."""

    fetched: int = 0
    valid: int = 0  # parsed cleanly
    duplicates: int = 0
    new_events: int = 0
    latency_ms: float = 0.0
    failures: int = 0
    fetch_success: bool = True

    @property
    def parse_quality(self) -> float:
        return round(self.valid / self.fetched, 4) if self.fetched else 0.0

    @property
    def duplicate_rate(self) -> float:
        return round(self.duplicates / self.fetched, 4) if self.fetched else 0.0

    @property
    def new_event_rate(self) -> float:
        return round(self.new_events / self.fetched, 4) if self.fetched else 0.0

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "valid": self.valid,
            "duplicates": self.duplicates,
            "new_events": self.new_events,
            "latency_ms": self.latency_ms,
            "failures": self.failures,
            "fetch_success": self.fetch_success,
            "parse_quality": self.parse_quality,
            "duplicate_rate": self.duplicate_rate,
            "new_event_rate": self.new_event_rate,
        }


@dataclass(frozen=True)
class CanaryThresholds:
    min_parse_quality: float = 0.5
    max_duplicate_rate: float = 0.5
    min_new_events: int = 1
    max_failures: int = 1
    max_latency_ms: float = 10_000.0


DEFAULT_CANARY_THRESHOLDS = CanaryThresholds()


@dataclass
class CanaryResult:
    healthy: bool
    metrics: CanaryMetrics
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"healthy": self.healthy, "metrics": self.metrics.as_dict(), "reasons": self.reasons}


def evaluate_canary(
    m: CanaryMetrics, thresholds: CanaryThresholds = DEFAULT_CANARY_THRESHOLDS
) -> CanaryResult:
    """A canary is healthy only if it fetched, parsed well, wasn't all duplicates, and produced
    new events within latency/failure bounds. Any failing check is a reason to roll back."""
    reasons: list[str] = []
    if not m.fetch_success:
        reasons.append("fetch failed")
    if m.parse_quality < thresholds.min_parse_quality:
        reasons.append(f"parse_quality {m.parse_quality:.2f} < {thresholds.min_parse_quality}")
    if m.duplicate_rate > thresholds.max_duplicate_rate:
        reasons.append(f"duplicate_rate {m.duplicate_rate:.2f} > {thresholds.max_duplicate_rate}")
    if m.new_events < thresholds.min_new_events:
        reasons.append(f"new_events {m.new_events} < {thresholds.min_new_events}")
    if m.failures > thresholds.max_failures:
        reasons.append(f"failures {m.failures} > {thresholds.max_failures}")
    if m.latency_ms > thresholds.max_latency_ms:
        reasons.append(f"latency {m.latency_ms:.0f}ms > {thresholds.max_latency_ms:.0f}ms")
    return CanaryResult(healthy=not reasons, metrics=m, reasons=reasons)


class CanarySync(ABC):
    """Runs a small first sync for a provider and reports metrics. No provider impl in 7B."""

    @abstractmethod
    async def run(self, registration: ProductionRegistration) -> CanaryMetrics: ...


class MockCanarySync(CanarySync):
    """Deterministic canary — returns pre-set metrics per provider (tests/spike). No network."""

    def __init__(
        self,
        scenarios: dict[str, CanaryMetrics] | None = None,
        default: CanaryMetrics | None = None,
    ) -> None:
        self._scenarios = scenarios or {}
        self._default = default or CanaryMetrics(
            fetched=6, valid=6, duplicates=1, new_events=5, latency_ms=250.0
        )

    async def run(self, registration: ProductionRegistration) -> CanaryMetrics:
        return self._scenarios.get(registration.provider_id, self._default)
