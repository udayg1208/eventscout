"""Provider Sandbox — validate a provider before it reaches production storage.

Runs a plugin through Fetch -> Validate -> Normalize -> Classify -> Entity Resolution
(self-dedup) -> Preview Report, **without touching the production catalog or state**
(the sandbox is given no repository — it structurally cannot write). Its report is the
evidence a human uses to approve a new provider for production.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date

from app.ingestion.plugin import ProviderPlugin
from app.ingestion.stages import (
    classify,
    event_preview,
    normalize,
    quality_score,
    self_dedupe,
    validate_events,
)

logger = logging.getLogger(__name__)

# A provider must clear this quality bar (and return data) to be auto-approvable.
_MIN_QUALITY = 0.3
_MAX_SAMPLE = 3
_MAX_ERRORS = 10


@dataclass
class SandboxReport:
    provider_id: str
    ok: bool
    fetched: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates: int = 0
    normalized_sample: list[dict] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    missing_fields: dict[str, int] = field(default_factory=dict)
    quality_score: float = 0.0
    error: str | None = None  # set when the fetch itself failed

    @property
    def passed(self) -> bool:
        """Auto-approval verdict: fetched real data, no fatal error, quality clears the bar."""
        return self.ok and self.fetched > 0 and self.quality_score >= _MIN_QUALITY


async def run_sandbox(plugin: ProviderPlugin, *, today: date | None = None) -> SandboxReport:
    """Execute a plugin in isolation and return a preview report. Never raises."""
    today = today or date.today()
    try:
        raw = await asyncio.wait_for(plugin.fetch(), timeout=plugin.timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - sandbox must never crash on a bad provider
        logger.warning("sandbox: %s fetch failed: %s", plugin.id, exc)
        return SandboxReport(plugin.id, ok=False, error=f"{type(exc).__name__}: {exc}")

    processed = classify(normalize(raw))
    outcome = validate_events(processed, today=today)
    survivors, duplicates = self_dedupe(outcome.valid)
    score = quality_score(outcome.valid, fetched=len(raw), duplicates=duplicates)

    return SandboxReport(
        provider_id=plugin.id,
        ok=True,
        fetched=len(raw),
        valid=len(outcome.valid),
        invalid=len(outcome.invalid),
        duplicates=duplicates,
        normalized_sample=[event_preview(e) for e in survivors[:_MAX_SAMPLE]],
        validation_errors=[reason for _, reason in outcome.invalid][:_MAX_ERRORS],
        missing_fields=outcome.missing_fields,
        quality_score=score,
    )


def render_sandbox_report(report: SandboxReport) -> str:
    lines = [
        f"Sandbox report — {report.provider_id}",
        f"  status         : {'OK' if report.ok else 'FETCH FAILED'}"
        + (f" ({report.error})" if report.error else ""),
        f"  fetched        : {report.fetched}",
        f"  valid / invalid: {report.valid} / {report.invalid}",
        f"  duplicates     : {report.duplicates}",
        f"  quality score  : {report.quality_score}",
        f"  auto-approve   : {'YES' if report.passed else 'NO'}",
    ]
    if report.missing_fields:
        gaps = ", ".join(f"{k}={v}" for k, v in sorted(report.missing_fields.items()))
        lines.append(f"  missing fields : {gaps}")
    if report.validation_errors:
        lines.append(f"  sample errors  : {report.validation_errors[:3]}")
    if report.normalized_sample:
        lines.append("  normalized sample:")
        for item in report.normalized_sample:
            lines.append(f"    - [{item['category']}] {item['title'][:48]} ({item['city']})")
    return "\n".join(lines)
