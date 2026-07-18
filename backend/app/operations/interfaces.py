"""Future operations seams (Phase 7B) — INTERFACES ONLY, no implementations.

7B ships a deterministic mock canary (no network, no real provider). These abstractions mark where
the real, live-running components plug in later; each raises `NotImplementedError`. Nothing here
runs a provider, hits the network, or mutates onboarding.
"""

from __future__ import annotations

from abc import abstractmethod

from app.operations.learning import CalibrationModel
from app.operations.production import CanaryMetrics, CanarySync
from app.operations.registry import ProductionRegistration


class RealCanarySync(CanarySync):
    """FUTURE: run a real small sync via the ingestion runner + sandbox (Phase 3C) and measure it.

    Reuses the existing runner/sandbox — no provider or catalog code changes — but needs network,
    so it is deferred. 7B evaluates the mock's metrics identically.
    """

    @abstractmethod
    async def run(self, registration: ProductionRegistration) -> CanaryMetrics:  # pragma: no cover
        raise NotImplementedError("real runner-backed canary is deferred (needs network)")


class MetricsCollector:
    """FUTURE: pull live health metrics (latency, quality, duplicate %) from real provider runs."""

    @abstractmethod
    async def collect(self, provider_id: str) -> CanaryMetrics:  # pragma: no cover
        raise NotImplementedError("live metrics collection is a future seam")


class OnboardingCalibrator:
    """FUTURE: feed a learned CalibrationModel back into 7A onboarding confidence.

    7B only *produces* the model (analytics). Wiring it into the onboarding engine so future
    decisions improve automatically is a deliberate, separately-approved integration.
    """

    @abstractmethod
    def apply(self, model: CalibrationModel) -> None:  # pragma: no cover
        raise NotImplementedError("closing the calibration loop into onboarding is deferred")
