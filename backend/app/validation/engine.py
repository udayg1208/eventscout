"""Seed Validation engine (Phase 10E) — close the discovery loop.

For each 10D Discovery Seed: plan the verification (per-kind strategy), fetch the candidate pages
(injected `Fetcher` — real in prod, `StaticFetcher` in tests; optional `searcher`), collect
evidence by running the real 10B/10C extractors, merge the four confidences, decide, and — only
when VERIFIED / PARTIALLY_VERIFIED — upsert a `CandidateSource(status=NEW)` into the existing
Discovery Inbox. Every decision is audited; INSUFFICIENT results are scheduled for retry with
cooldown until abandonment. Deterministic given fixtures; no browser, no LLM; verification only —
nothing onboarded.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.validation.confidence import VerificationConfidenceMerger
from app.validation.decision import DecisionEngine
from app.validation.evidence import EvidenceCollector
from app.validation.inbox import CandidateBuilder
from app.validation.metrics import ValidationMetrics
from app.validation.models import (
    AuditRecord,
    Evidence,
    RetryState,
    ValidationReport,
    VerificationDecision,
    VerificationResult,
)
from app.validation.planner import VerificationPlanner, slugify
from app.validation.retry import RetryPolicy
from app.validation.store import ValidationStore


class SeedValidationEngine:
    def __init__(
        self,
        inbox,
        fetcher,
        *,
        searcher=None,
        planner: VerificationPlanner | None = None,
        collector: EvidenceCollector | None = None,
        merger: VerificationConfidenceMerger | None = None,
        decision: DecisionEngine | None = None,
        retry: RetryPolicy | None = None,
        builder: CandidateBuilder | None = None,
        metrics: ValidationMetrics | None = None,
        store: ValidationStore | None = None,
        max_urls: int = 3,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inbox = inbox
        self._fetcher = fetcher
        self._searcher = searcher
        self._planner = planner or VerificationPlanner()
        self._collector = collector or EvidenceCollector()
        self._merger = merger or VerificationConfidenceMerger()
        self._decision = decision or DecisionEngine()
        self._retry = retry or RetryPolicy()
        self._builder = builder or CandidateBuilder()
        self.metrics = metrics or ValidationMetrics()
        self._store = store
        self._max_urls = max_urls
        self._clock = clock
        self._run = 0
        self._retry_states: dict[str, RetryState] = {}
        self.audit: list[AuditRecord] = []

    def _key(self, seed) -> str:
        return seed.target_key or slugify(seed.target)

    async def validate(self, seed, *, run: int | None = None) -> VerificationResult:
        run = self._run if run is None else run
        plan = self._planner.plan(seed)
        strat = self._planner.strategy_for(seed)

        urls = list(plan.candidate_urls)
        if self._searcher is not None:
            urls += [u for u in self._searcher.search(plan.search_query) if u not in urls]

        evidence = Evidence()
        for url in urls[: self._max_urls]:
            page = await self._fetcher.get(url)
            if page is None or page.status >= 400 or not page.text:
                continue
            evidence.merge(await self._collector.collect(page.url or url, page.text, seed))
            if evidence.signal_count() >= 4:
                break

        score, strat_reasons = strat.evaluate(seed, evidence)
        conf = self._merger.merge(seed_confidence=seed.confidence, evidence=evidence)
        decision, reasons = self._decision.decide(evidence, conf, score)
        now = self._clock()
        result = VerificationResult(
            seed_target=seed.target,
            seed_kind=seed.kind.value,
            decision=decision,
            confidence=conf,
            evidence=evidence,
            plan=plan,
            reasons=[*reasons, "strategy: " + " ".join(strat_reasons)],
            timestamp=now,
        )

        if result.accepted:
            candidate = self._builder.build(result, now=now)
            result.inbox_outcome = await self._inbox.upsert(candidate)
            result.candidate_key = candidate.key

        record = AuditRecord(
            seed_target=seed.target,
            seed_kind=seed.kind.value,
            decision=decision.value,
            confidence=conf.total,
            evidence=evidence.as_dict(),
            reasons=result.reasons,
            verification_path=plan.steps,
            inbox_outcome=result.inbox_outcome,
            timestamp=now.isoformat(),
        )
        self.audit.append(record)
        self.metrics.record(result)
        st = self._retry_states.setdefault(self._key(seed), RetryState(seed_key=self._key(seed)))
        _, st = self._retry.on_decision(st, decision, run)
        if self._store is not None:
            await self._store.save_audit(record)
            await self._store.save_retry(st)
        return result

    async def validate_batch(self, seeds, *, run: int | None = None) -> ValidationReport:
        self._run += 1
        run = self._run if run is None else run
        report = ValidationReport()
        for seed in seeds:
            st = self._retry_states.get(self._key(seed))
            if not self._retry.eligible(st, run):
                report.skipped_cooldown += 1
                continue
            result = await self.validate(seed, run=run)
            report.total += 1
            d = result.decision
            if d is VerificationDecision.VERIFIED:
                report.verified += 1
            elif d is VerificationDecision.PARTIALLY_VERIFIED:
                report.partial += 1
            elif d is VerificationDecision.INSUFFICIENT_EVIDENCE:
                report.insufficient += 1
            else:
                report.rejected += 1
            if result.inbox_outcome in ("inserted", "updated"):
                report.accepted_to_inbox += 1
            if result.inbox_outcome == "updated":
                report.duplicates += 1
            state = self._retry_states[self._key(seed)]
            if state.abandoned:
                report.abandoned += 1
            elif d is VerificationDecision.INSUFFICIENT_EVIDENCE:
                report.retries_scheduled += 1
        return report

    def retry_state(self, seed_key: str) -> RetryState | None:
        return self._retry_states.get(seed_key)

    def audit_trail(self) -> list[AuditRecord]:
        return list(self.audit)
