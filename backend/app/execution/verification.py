"""Source verification (Phase 10A) — validate every candidate before the Discovery Inbox.

`VerifyingInbox` implements the existing `DiscoveryInbox` ABC and wraps a real inbox, so the engines
upsert through it unchanged. On each upsert it runs five checks — **robots** (legality),
**accessibility** (a real http(s) URL with a host), **event relevance** (the candidate carries tech/
event signal, not noise), **freshness** (a source seen very recently isn't re-processed), and
**duplicate detection** (already-known key) — and only then delegates to the wrapped inbox. Rejected
and duplicate candidates are counted, never inserted. Reuses the existing `RobotsCache`, the
candidate's own confidence signals, and the inbox's `get` for dedup — no new abstraction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from app.discovery.models import CandidateSource, DiscoveryStatus
from app.discovery.robots import RobotsCache
from app.discovery.store import DiscoveryInbox


@dataclass
class VerificationResult:
    passed: bool
    duplicate: bool = False
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "duplicate": self.duplicate,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
        }


def _relevance_score(c: CandidateSource) -> float:
    """A candidate is relevant if it carries any tech/event/structured signal — not just noise."""
    signal = 0.0
    signal = max(signal, c.discovery_confidence or 0.0)
    signal = max(signal, c.technology_confidence, c.professional_confidence)
    if c.signals is not None and c.signals.structured_count() > 0:
        signal = max(signal, 0.5)
    if c.classification:
        signal = max(signal, 0.5)
    if c.embedded_event_count > 0:
        signal = max(signal, 0.6)
    return signal


class SourceVerifier:
    def __init__(
        self,
        *,
        robots: RobotsCache | None = None,
        min_relevance: float = 0.15,
        revisit_hours: float = 24.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._robots = robots
        self._min_relevance = min_relevance
        self._revisit = timedelta(hours=revisit_hours)
        self._clock = clock

    async def verify(
        self, candidate: CandidateSource, existing: CandidateSource | None
    ) -> VerificationResult:
        reasons: list[str] = []
        checks: dict[str, bool] = {}

        # accessibility — a real, fetchable public http(s) URL
        parts = urlsplit(candidate.url)
        accessible = parts.scheme in ("http", "https") and bool(parts.netloc)
        checks["accessibility"] = accessible
        if not accessible:
            reasons.append(f"not a public http(s) url: {candidate.url}")

        # robots — legality (reuses the shared RobotsCache; None → check skipped/allowed)
        allowed = True
        if self._robots is not None and accessible:
            allowed = await self._robots.allowed(candidate.url)
        checks["robots"] = allowed
        if not allowed:
            reasons.append("disallowed by robots.txt")

        # event relevance — carries some tech/event/structured signal
        relevant = _relevance_score(candidate) >= self._min_relevance
        checks["relevance"] = relevant
        if not relevant:
            reasons.append("below event-relevance threshold")

        # freshness + duplicate — a source seen very recently is a duplicate, not new discovery
        duplicate = False
        fresh = True
        if existing is not None:
            last = existing.last_seen_at
            if last is not None and (self._clock() - last) < self._revisit:
                duplicate = True
                fresh = False
                reasons.append("seen within the revisit window (duplicate)")
        checks["freshness"] = fresh
        checks["not_duplicate"] = not duplicate

        passed = accessible and allowed and relevant and not duplicate
        return VerificationResult(
            passed=passed, duplicate=duplicate, reasons=reasons, checks=checks
        )


class VerifyingInbox(DiscoveryInbox):
    """A `DiscoveryInbox` that validates each candidate before delegating to a real inbox."""

    def __init__(
        self,
        inner: DiscoveryInbox,
        verifier: SourceVerifier,
        *,
        on_result: Callable[[CandidateSource, VerificationResult, str], None] | None = None,
    ) -> None:
        self._inner = inner
        self._verifier = verifier
        self._on_result = on_result

    async def upsert(self, candidate: CandidateSource) -> str:
        existing = await self._inner.get(candidate.key)
        result = await self._verifier.verify(candidate, existing)
        if not result.passed:
            outcome = "duplicate" if result.duplicate else "rejected"
            if self._on_result:
                self._on_result(candidate, result, outcome)
            return outcome
        outcome = await self._inner.upsert(candidate)  # "inserted" | "updated"
        if self._on_result:
            self._on_result(candidate, result, outcome)
        return outcome

    # -- transparent delegation --------------------------------------------
    async def get(self, key: str) -> CandidateSource | None:
        return await self._inner.get(key)

    async def list(
        self, *, status: DiscoveryStatus | None = None, limit: int = 100, offset: int = 0
    ):
        return await self._inner.list(status=status, limit=limit, offset=offset)

    async def set_status(self, key: str, status: DiscoveryStatus, reason: str = "") -> bool:
        return await self._inner.set_status(key, status, reason)

    async def count(self, *, status: DiscoveryStatus | None = None) -> int:
        return await self._inner.count(status=status)

    async def close(self) -> None:
        await self._inner.close()
