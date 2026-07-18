"""Ingestion Runner — one complete ingestion execution for a single plugin.

The full path every provider uses:

    load plugin -> read provider state -> fetch (retry + timeout) -> normalize ->
    classify -> entity-resolve (self-dedup + DB candidates) -> bulk upsert ->
    update provider state -> ingestion report

No scheduler, no workers, no concurrency here — just one provider, start to finish.
Every stage is guarded: no exception terminates the pipeline; a provider failure is
recorded structurally and reflected in Provider State. The runner touches only the
frozen Repository v2 and Provider State Store through their public interfaces.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from app.ingestion.plugin import ProviderPlugin
from app.ingestion.stages import (
    classify,
    normalize,
    quality_score,
    self_dedupe,
    validate_events,
)
from app.models.event import Event
from app.providers.dedup import event_similarity
from app.storage.models import StoredEvent, event_key
from app.storage.provider_state import ProviderStateStore, new_provider_state
from app.storage.repository import EventRepository

logger = logging.getLogger(__name__)

# Cross-source duplicate threshold (matches the dedup engine).
_RESOLVE_THRESHOLD = 0.85

Sleeper = Callable[[float], Awaitable[None]]


@dataclass
class IngestionReport:
    """The analytics artifact produced after every run."""

    provider_id: str
    ok: bool
    runtime_ms: float
    fetched: int = 0
    accepted: int = 0  # events written (new or updated) to the catalog
    duplicates: int = 0  # self + cross-source
    rejected: int = 0  # failed validation
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    quality_score: float = 0.0


async def run_ingestion(
    plugin: ProviderPlugin,
    repo: EventRepository,
    state_store: ProviderStateStore,
    *,
    now: datetime,
    today: date | None = None,
    sleep: Sleeper = asyncio.sleep,
) -> IngestionReport:
    """Execute one full ingestion for `plugin`. Never raises; always returns a report."""
    today = today or now.date()
    started = time.perf_counter()
    errors: list[str] = []

    await _ensure_registered(plugin, state_store, now, errors)

    raw, fetch_error = await _fetch(plugin, sleep=sleep)
    if raw is None:
        return await _fail(
            plugin, state_store, now, started, [fetch_error, *errors], reason=fetch_error
        )

    processed = classify(normalize(raw))
    outcome = validate_events(processed, today=today)
    survivors, self_dups = self_dedupe(outcome.valid)
    to_upsert, cross_dups = await _resolve(survivors, repo, now=now, errors=errors)
    duplicates = self_dups + cross_dups

    try:
        result = await repo.bulk_upsert(to_upsert)
    except Exception as exc:  # noqa: BLE001 - storage failure must not crash the run
        return await _fail(
            plugin, state_store, now, started, [f"upsert: {exc}", *errors], reason="upsert failed"
        )

    runtime_ms = (time.perf_counter() - started) * 1000
    checkpoint = _batch_checkpoint(to_upsert)
    await _safe(
        state_store.update_after_run(
            plugin.id,
            at=now,
            execution_ms=runtime_ms,
            events_discovered=len(raw),
            checkpoint=checkpoint,
            policy=plugin.retry_policy(),
        ),
        errors,
    )
    logger.info(
        "ingest %s: fetched=%d accepted=%d dups=%d rejected=%d (%+d/%+d/=%d)",
        plugin.id,
        len(raw),
        len(to_upsert),
        duplicates,
        len(outcome.invalid),
        result.inserted,
        result.updated,
        result.unchanged,
    )
    return IngestionReport(
        provider_id=plugin.id,
        ok=True,
        runtime_ms=round(runtime_ms, 1),
        fetched=len(raw),
        accepted=len(to_upsert),
        duplicates=duplicates,
        rejected=len(outcome.invalid),
        inserted=result.inserted,
        updated=result.updated,
        unchanged=result.unchanged,
        errors=errors,
        quality_score=quality_score(outcome.valid, fetched=len(raw), duplicates=duplicates),
    )


# --- stages -----------------------------------------------------------------------


async def _ensure_registered(
    plugin: ProviderPlugin, state_store: ProviderStateStore, now: datetime, errors: list[str]
) -> None:
    """Read provider state; register the plugin (version + capabilities) on first sight."""
    try:
        state = await state_store.get_provider_state(plugin.id)
        if state is None:
            await state_store.save_provider_state(
                new_provider_state(
                    plugin.id,
                    at=now,
                    version=plugin.version,
                    capabilities=plugin.capability_record(),
                )
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"state read: {exc}")


async def _fetch(plugin: ProviderPlugin, *, sleep: Sleeper) -> tuple[list[Event] | None, str]:
    """Fetch with timeout + bounded retry/backoff. Returns (events, "") or (None, error)."""
    last_error = ""
    for attempt in range(1, plugin.max_attempts + 1):
        try:
            events = await asyncio.wait_for(plugin.fetch(), timeout=plugin.timeout_seconds)
            return events, ""
        except Exception as exc:  # noqa: BLE001 - all fetch failures are handled as data
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("ingest %s: fetch attempt %d failed: %s", plugin.id, attempt, last_error)
            if attempt < plugin.max_attempts:
                await sleep(plugin.retry_backoff_seconds * attempt)
    return None, last_error or "fetch failed"


async def _resolve(
    events: list[Event], repo: EventRepository, *, now: datetime, errors: list[str]
) -> tuple[list[StoredEvent], int]:
    """Entity resolution: keep same-provider records (upsert by key) but drop events that
    already exist in the catalog under a *different* key (cross-source duplicates)."""
    to_upsert: list[StoredEvent] = []
    cross_dups = 0
    for event in events:
        key = event_key(event)
        try:
            candidates = await repo.find_candidates(on_date=event.start_date, city=event.city)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"resolve: {exc}")
            candidates = []
        is_cross_dup = any(
            c.key != key and event_similarity(event, c.event) >= _RESOLVE_THRESHOLD
            for c in candidates
        )
        if is_cross_dup:
            cross_dups += 1
            continue
        to_upsert.append(StoredEvent.from_event(event, seen_at=now))
    return to_upsert, cross_dups


# --- helpers ----------------------------------------------------------------------


async def _fail(
    plugin: ProviderPlugin,
    state_store: ProviderStateStore,
    now: datetime,
    started: float,
    errors: list[str],
    *,
    reason: str,
) -> IngestionReport:
    runtime_ms = (time.perf_counter() - started) * 1000
    await _safe(
        state_store.update_after_failure(
            plugin.id, at=now, error=reason, execution_ms=runtime_ms, policy=plugin.retry_policy()
        ),
        errors,
    )
    logger.warning("ingest %s: FAILED (%s)", plugin.id, reason)
    return IngestionReport(
        provider_id=plugin.id,
        ok=False,
        runtime_ms=round(runtime_ms, 1),
        errors=[e for e in errors if e],
    )


async def _safe(coro: Awaitable[object], errors: list[str]) -> None:
    try:
        await coro
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))


def _batch_checkpoint(records: list[StoredEvent]) -> str:
    """A stable fingerprint of the accepted batch — the provider's 'last content hash'."""
    basis = "\n".join(sorted(f"{r.key}:{r.content_hash}" for r in records))
    return hashlib.sha256(basis.encode()).hexdigest()


def render_report(report: IngestionReport) -> str:
    status = "OK" if report.ok else "FAILED"
    lines = [
        f"[{status}] {report.provider_id}  ({report.runtime_ms} ms)",
        f"  fetched={report.fetched} accepted={report.accepted} "
        f"duplicates={report.duplicates} rejected={report.rejected}",
        f"  upserts: +{report.inserted} new / ~{report.updated} updated / ={report.unchanged} same",
        f"  quality={report.quality_score}",
    ]
    if report.errors:
        lines.append(f"  errors: {report.errors[:3]}")
    return "\n".join(lines)
