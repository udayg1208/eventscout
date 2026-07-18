"""Onboarding Engine (Phase 7A) — orchestrates the lifecycle.

    Discovery Inbox candidate → DISCOVERED → ANALYZED → SANDBOXED → SCORED
                                     │
                     ┌───────────────┼────────────────┐
                 AUTO_APPROVED    MANUAL_REVIEW      REJECTED / DUPLICATE /
                     │            (ReviewPacket)     BLACKLISTED / FAILED_SANDBOX
                 APPROVED
                     │
                 PROMOTED  (PromotionPlan staged — NOT applied; 7A stops here)

The engine keeps the authoritative working set in memory and persists every candidate + audit
entry to the store. It never touches the catalog, registry, scheduler, ingestion, or providers, and
never drives a candidate past PROMOTED (that is production, i.e. Phase 7B).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.discovery.models import CandidateSource, DiscoveryStatus
from app.discovery.store import DiscoveryInbox
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS
from app.onboarding.analytics import build_analytics
from app.onboarding.confidence import DEFAULT_THRESHOLDS, Thresholds, score_onboarding
from app.onboarding.lifecycle import transition
from app.onboarding.models import (
    OnboardingAnalytics,
    OnboardingCandidate,
    OnboardingState,
    Recommendation,
    SandboxOutcome,
)
from app.onboarding.monitor import build_monitoring
from app.onboarding.promotion import build_promotion_plan
from app.onboarding.review import build_review_packet
from app.onboarding.store import OnboardingStore

_S = OnboardingState
_NON_REJECT = frozenset(
    {
        _S.ANALYZED,
        _S.SANDBOXED,
        _S.SCORED,
        _S.AUTO_APPROVED,
        _S.MANUAL_REVIEW,
        _S.APPROVED,
        _S.PROMOTED,
        _S.MONITORING,
        _S.ACTIVE,
    }
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def simulate_sandbox(snapshot: dict) -> SandboxOutcome:
    """Deterministic dry-run over discovered evidence — NO network, NO provider instance.

    Passes when there is plausible ingestible signal (event evidence, structured data, or strong
    tech+India relevance); fails when a source shows no ingestible potential at all.
    """
    plausible = max(snapshot.get("event_count", 0), snapshot.get("embedded_event_count", 0))
    structured = snapshot.get("structured_data_score", 0)
    tech = float(snapshot.get("technology_confidence", 0.0))
    india = float(snapshot.get("india_confidence", 0.0))
    quality = _clamp(
        0.25 * min(1.0, structured / 4.0)
        + 0.35 * min(1.0, plausible / 10.0)
        + 0.25 * tech
        + 0.15 * india
    )
    passed = plausible > 0 or structured > 0 or (tech >= 0.34 and india >= 0.5)
    notes = [
        f"plausible_events={plausible}",
        f"structured_score={structured}",
        "no network / no provider — evidence-based dry-run",
    ]
    if not passed:
        notes.append("no ingestible evidence → FAILED_SANDBOX")
    return SandboxOutcome(
        tested=True,
        passed=passed,
        plausible_events=plausible,
        structured_score=structured,
        quality=round(quality, 3),
        notes=notes,
    )


class OnboardingEngine:
    def __init__(
        self,
        store: OnboardingStore,
        *,
        thresholds: Thresholds = DEFAULT_THRESHOLDS,
        blacklist: set[str] | None = None,
        known_domains: set[str] | None = None,
        stale_after_hours: float = 72.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._thresholds = thresholds
        self._blacklist = set(blacklist or ())
        self._known = set(
            known_domains or ()
        )  # domains of existing providers (data, not registry access)
        self._stale_after = stale_after_hours
        self._clock = clock
        self._candidates: dict[str, OnboardingCandidate] = {}

    # ------------------------------ snapshot + transitions ------------------------------

    def _snapshot(self, s: CandidateSource) -> dict:
        sig = s.signals
        text = f"{s.title or ''} {s.organization or ''}".lower()
        techs = sorted({n for n, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(text)})
        return {
            "url": s.url,
            "domain": s.domain,
            "feed_type": s.feed_type.value,
            "discovered_by": s.discovered_by,
            "title": s.title,
            "city": s.city,
            "country": s.country,
            "organization": s.organization,
            "classification": s.classification,
            "technology_confidence": s.technology_confidence,
            "india_confidence": s.india_confidence,
            "professional_confidence": s.professional_confidence,
            "structured_data_score": s.structured_data_score,
            "discovery_confidence": s.discovery_confidence,
            "event_count": sig.event_count,
            "embedded_event_count": s.embedded_event_count,
            "tech_keyword_count": sig.tech_keyword_count,
            "has_organizer": sig.has_organizer,
            "has_registration_link": sig.has_registration_link,
            "technologies": techs,
        }

    async def _advance(
        self, cand: OnboardingCandidate, to: OnboardingState, actor: str, reason: str
    ) -> None:
        entry = transition(cand, to, actor=actor, reason=reason, clock=self._clock)
        await self._store.append_audit(entry)
        await self._store.save(cand)

    def _onboarded_domains(self) -> set[str]:
        return {c.domain for c in self._candidates.values() if c.state in _NON_REJECT}

    # ------------------------------ the pipeline ------------------------------

    async def onboard(self, source: CandidateSource) -> OnboardingCandidate:
        now = self._clock()
        snap = self._snapshot(source)
        cand = OnboardingCandidate(
            key=source.key,
            url=source.url,
            domain=source.domain,
            feed_type=source.feed_type.value,
            discovered_by=source.discovered_by,
            source_snapshot=snap,
            state=_S.DISCOVERED,
            created_at=now,
            updated_at=now,
        )
        self._candidates[cand.key] = cand
        await self._store.save(cand)

        if cand.domain in self._blacklist:
            await self._advance(cand, _S.BLACKLISTED, "system", "domain is blacklisted")
            return cand
        if cand.domain in self._known or cand.domain in self._onboarded_domains():
            await self._advance(
                cand, _S.DUPLICATE, "system", "domain already onboarded / known provider"
            )
            return cand

        await self._advance(cand, _S.ANALYZED, "auto", "discovery evidence extracted")

        sandbox = simulate_sandbox(snap)
        cand.sandbox = sandbox
        await self._advance(cand, _S.SANDBOXED, "auto", f"sandbox quality={sandbox.quality:.2f}")
        if not sandbox.passed:
            await self._advance(
                cand, _S.FAILED_SANDBOX, "auto", "no ingestible evidence in dry-run"
            )
            return cand

        conf = score_onboarding(snap, sandbox, thresholds=self._thresholds)
        cand.confidence = conf
        cand.confidence_history.append(conf.total)
        await self._advance(
            cand, _S.SCORED, "auto", f"confidence={conf.total:.2f} band={conf.band.value}"
        )

        if conf.band is Recommendation.AUTO_APPROVE:
            await self._advance(cand, _S.AUTO_APPROVED, "auto", f"high confidence {conf.total:.2f}")
            await self._advance(cand, _S.APPROVED, "auto", "auto-approved (no human required)")
            self._stage_promotion(cand, "auto")
            await self._advance(
                cand, _S.PROMOTED, "auto", "promotion plan generated (staged, not applied)"
            )
        elif conf.band is Recommendation.REVIEW:
            cand.review_packet = build_review_packet(snap, conf, sandbox)
            await self._advance(
                cand, _S.MANUAL_REVIEW, "auto", f"confidence {conf.total:.2f} → human review"
            )
        else:
            await self._advance(
                cand, _S.REJECTED, "auto", f"confidence {conf.total:.2f} below review threshold"
            )
        return cand

    def _stage_promotion(self, cand: OnboardingCandidate, actor: str) -> None:
        plan = build_promotion_plan(cand.source_snapshot, cand.confidence, cand.sandbox)
        cand.promotion_plan = plan
        cand.promotion_history.append(
            {
                "actor": actor,
                "provider_type": plan.provider_type,
                "risk": plan.risk_assessment["level"],
            }
        )

    async def onboard_batch(self, sources: list[CandidateSource]) -> list[OnboardingCandidate]:
        return [await self.onboard(s) for s in sources]

    async def ingest_from_inbox(
        self, inbox: DiscoveryInbox, *, limit: int = 1000
    ) -> list[OnboardingCandidate]:
        """Read NEW discovery candidates and onboard them (read-only; the inbox is not mutated)."""
        new = await inbox.list(status=DiscoveryStatus.NEW, limit=limit)
        return await self.onboard_batch(new)

    # ------------------------------ human-in-the-loop ------------------------------

    async def record_review_decision(
        self, key: str, *, approve: bool, reviewer: str, notes: str = ""
    ) -> OnboardingCandidate | None:
        """Advance a MANUAL_REVIEW candidate on a human decision → APPROVED+PROMOTED or REJECTED."""
        cand = self._candidates.get(key)
        if cand is None or cand.state is not _S.MANUAL_REVIEW:
            return None
        if notes:
            cand.review_notes.append(notes)
        actor = f"human:{reviewer}"
        if approve:
            await self._advance(cand, _S.APPROVED, actor, notes or "approved by reviewer")
            self._stage_promotion(cand, actor)
            await self._advance(
                cand, _S.PROMOTED, actor, "promotion plan generated (staged, not applied)"
            )
        else:
            await self._advance(cand, _S.REJECTED, actor, notes or "rejected by reviewer")
        return cand

    # ------------------------------ observability ------------------------------

    def candidates(self) -> list[OnboardingCandidate]:
        return list(self._candidates.values())

    def review_queue(self) -> list[OnboardingCandidate]:
        return [c for c in self._candidates.values() if c.state is _S.MANUAL_REVIEW]

    def promotion_plans(self) -> list[OnboardingCandidate]:
        return [c for c in self._candidates.values() if c.state is _S.PROMOTED]

    def monitoring(self):
        return build_monitoring(
            self.candidates(), stale_after_hours=self._stale_after, clock=self._clock
        )

    def analytics(self, *, inbox_size: int | None = None) -> OnboardingAnalytics:
        return build_analytics(self.candidates(), inbox_size=inbox_size)
