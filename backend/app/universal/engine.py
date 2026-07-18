"""Universal Event Engine (Phase 10B) — any page → provenance-bearing events.

Runs the isolated extractors in structural tiers (structured → semi-structured → textual), in
parallel within each tier, merging results as it goes and **stopping early** once a confident event
has been assembled — so a JSON-LD page never pays for the semantic scan. Merged events are
normalized, validated (off-topic rejected), and scored by the explainable eight-component
confidence engine. Optionally fingerprints pages to skip unchanged ones. Deterministic; no network,
no browser, no LLM; discovery only — nothing is written anywhere.
"""

from __future__ import annotations

import asyncio

from app.universal.confidence import UniversalConfidence
from app.universal.extractors import EXTRACTION_TIERS
from app.universal.fingerprint import FingerprintStore, fingerprint
from app.universal.merge import merge_raw_events
from app.universal.models import Page, UniversalEvent, UniversalReport
from app.universal.normalize import normalize
from app.universal.text_utils import strip_tags
from app.universal.validator import UniversalValidator


class UniversalEventEngine:
    def __init__(
        self,
        *,
        tiers=None,
        validator: UniversalValidator | None = None,
        confidence: UniversalConfidence | None = None,
        fingerprints: FingerprintStore | None = None,
        min_confidence: float = 0.35,
        early_stop: float = 0.8,
        parallel: bool = True,
    ) -> None:
        self._tiers = tiers if tiers is not None else EXTRACTION_TIERS
        self._validator = validator or UniversalValidator()
        self._confidence = confidence or UniversalConfidence()
        self._fingerprints = fingerprints
        self._min = min_confidence
        self._early = early_stop
        self._parallel = parallel

    async def extract(
        self, url: str, html: str, *, content_type: str = "text/html"
    ) -> UniversalReport:
        page = Page(url=url, html=html, content_type=content_type)
        if self._fingerprints is not None:
            fp = fingerprint(html)
            if self._fingerprints.unchanged(url, fp):
                return UniversalReport(url=url, skipped_unchanged=True)
            self._fingerprints.remember(url, fp)

        raws = []
        ran: list[str] = []
        merged: list = []
        for tier in self._tiers:
            for result in await self._run_tier(tier, page):
                ran.append(result.source.value)
                raws.extend(result.events)
            merged = merge_raw_events(raws)
            if merged and self._peak(merged) >= self._early:
                break

        context = strip_tags(html)[:5000]  # page text so off-topic pages are caught
        events: list[UniversalEvent] = []
        rejected = 0
        for fields, sources in merged:
            fields = normalize(fields)
            verdict = self._validator.validate(fields, context)
            cs = self._confidence.score(fields, sources)
            if not verdict.valid:
                rejected += 1
                continue
            if cs.total >= self._min:
                events.append(
                    UniversalEvent(
                        source_url=url,
                        fields=fields,
                        confidence=cs.total,
                        confidence_breakdown=cs.components,
                        sources=sources,
                        valid=True,
                        reject_reason=None,
                    )
                )
        events.sort(key=lambda e: (-e.confidence, e.title or ""))
        return UniversalReport(
            url=url, events=events, extractors_run=ran, raw_events=len(raws), rejected=rejected
        )

    def _peak(self, merged) -> float:
        return max((self._confidence.score(normalize(f), s).total for f, s in merged), default=0.0)

    async def _run_tier(self, tier, page: Page):
        if self._parallel:
            return list(await asyncio.gather(*[asyncio.to_thread(e.extract, page) for e in tier]))
        return [e.extract(page) for e in tier]
