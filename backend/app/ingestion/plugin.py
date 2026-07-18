"""Provider Plugin — the production adapter around an existing provider.

A plugin pairs an **unmodified** `EventProvider` with the operational metadata and
declared capabilities the ingestion platform needs. Provider fetch logic is never
touched: `fetch()` simply delegates to the provider's existing "give me everything"
path (`search(SearchQuery())`). Everything the scheduler/runner/analytics need is read
from the plugin's declared fields — never from the provider's identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.models.event import Event
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.storage.provider_state import RetryPolicy


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider *can do and supply*. Consumers adapt to these flags instead of
    branching on provider identity. Honest by default: today's providers yield only
    what the current Event model can carry (no speakers/organizers/schedules yet)."""

    supports_pagination: bool = False
    supports_delta_sync: bool = False
    supports_online_events: bool = False
    supports_pricing: bool = False
    supports_speakers: bool = False
    supports_organizers: bool = False
    supports_schedules: bool = False

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderPlugin:
    """An installable provider: identity + declared capabilities + operational config +
    a delegating fetch. Immutable; the wrapped provider is reused as-is."""

    id: str
    name: str
    version: int
    provider: EventProvider
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)

    # --- operational metadata (declared, never hardcoded in the pipeline) ---
    refresh_interval_seconds: float = 3600.0
    timeout_seconds: float = 30.0
    max_attempts: int = 3  # per-fetch retries
    retry_backoff_seconds: float = 2.0
    failure_threshold: int = 5  # consecutive failures that open the circuit
    circuit_cooldown_seconds: float = 1800.0
    rate_limit_per_minute: float = 60.0
    concurrency_limit: int = 4
    expected_volume: int = 0

    async def fetch(self) -> list[Event]:
        """Fetch everything this provider currently offers. Delegates to the provider's
        untouched search path; the empty query means "no filter — give me all"."""
        return await self.provider.search(SearchQuery())

    def retry_policy(self) -> RetryPolicy:
        """The circuit/scheduling policy the Provider State Store applies for this
        provider — derived from declared metadata, so nothing is hardcoded downstream."""
        return RetryPolicy(
            failure_threshold=self.failure_threshold,
            base_backoff_seconds=self.retry_backoff_seconds,
            circuit_cooldown_seconds=self.circuit_cooldown_seconds,
            refresh_interval_seconds=self.refresh_interval_seconds,
        )

    def capability_record(self) -> dict[str, object]:
        """The capability map persisted into Provider State (open JSON — future features
        add keys, no schema change)."""
        return {**self.capabilities.as_dict(), "expected_volume": self.expected_volume}
