"""Merge (Phase 10B) — cluster the RawEvents from all extractors into events.

Different extractors describe the same event (JSON-LD + OpenGraph + a card all say "DevFest").
Cluster RawEvents by normalized title (falling back to date), then for each field keep the single
best `ExtractedField` across the cluster — EXTRACTED beats INFERRED, then higher provenance
confidence wins. The contributing extractors are recorded, so the merged event carries *merged
provenance*. Deterministic.
"""

from __future__ import annotations

from app.universal.models import ExtractedField, FieldStatus, RawEvent


def _cluster_key(raw: RawEvent) -> str:
    tk = raw.title_key()
    if tk:
        return f"t::{tk}"
    date = raw.value("start_date")
    return f"d::{date}" if date else "untitled"


def _rank(ef: ExtractedField) -> tuple[int, float]:
    status_rank = 1 if ef.status is FieldStatus.EXTRACTED else 0
    return (status_rank, ef.confidence)


def _better(a: ExtractedField, b: ExtractedField) -> bool:
    return _rank(a) > _rank(b)


def merge_raw_events(raws: list[RawEvent]) -> list[tuple[dict[str, ExtractedField], list[str]]]:
    clusters: dict[str, list[RawEvent]] = {}
    for r in raws:
        clusters.setdefault(_cluster_key(r), []).append(r)

    merged: list[tuple[dict[str, ExtractedField], list[str]]] = []
    for group in clusters.values():
        fields: dict[str, ExtractedField] = {}
        sources: list[str] = []
        for r in group:
            if r.source.value not in sources:
                sources.append(r.source.value)
            for name, ef in r.fields.items():
                if not ef.is_known:
                    continue
                cur = fields.get(name)
                if cur is None or _better(ef, cur):
                    fields[name] = ef
        if fields:
            merged.append((fields, sources))
    return merged
