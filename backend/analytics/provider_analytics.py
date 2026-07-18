"""Provider analytics — engineering observability only.

Regenerates PROVIDER_ANALYTICS.md from real provider runs. This module *reads* the
provider layer; it never modifies it, the public API, SearchService, or QueryParser.

Design: `collect()` is the only part that touches the network (times a real cold
fetch per provider). `build_stats()` and `render_markdown()` are pure, so the metric
math and report format are unit-tested without any network.

Run (from backend/):
    ./.venv/Scripts/python.exe -m analytics.provider_analytics
"""

from __future__ import annotations

import asyncio
import collections
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.models.event import Event
from app.models.search import SearchQuery
from app.providers.atlassian import AtlassianProvider
from app.providers.base import EventProvider
from app.providers.classify import classify_category
from app.providers.cncf import CNCFProvider
from app.providers.confstech import ConfsTechProvider
from app.providers.dedup import deduplicate
from app.providers.devfolio import DevfolioProvider
from app.providers.devpost import DevpostProvider
from app.providers.fossunited import FOSSUnitedProvider
from app.providers.gdg import GDGProvider
from app.providers.hasgeek import HasgeekProvider
from app.providers.ics import ICSProvider
from app.providers.ics_sources import ICS_SOURCES
from app.providers.luma import LumaProvider
from app.providers.salesforce import SalesforceProvider
from app.providers.snowflake import SnowflakeProvider


@dataclass
class ProviderMeta:
    name: str
    factory: Callable[[], EventProvider]  # class or zero-arg builder (ICS is parameterized)
    source_type: str
    api_type: str


@dataclass
class SkippedMeta:
    name: str
    source_type: str
    api_type: str
    reason: str


# Kept in sync as providers are added (this is the observability registry, not the
# production provider list in app/providers/__init__.py).
WORKING: list[ProviderMeta] = [
    ProviderMeta("confs.tech", ConfsTechProvider, "JSON", "GitHub static dataset"),
    ProviderMeta("devfolio", DevfolioProvider, "JSON", "Elasticsearch search API"),
    ProviderMeta("gdg", GDGProvider, "JSON", "Bevy REST"),
    ProviderMeta("cncf", CNCFProvider, "JSON", "Bevy REST"),
    ProviderMeta("fossunited", FOSSUnitedProvider, "JSON", "Frappe REST"),
    ProviderMeta("hasgeek", HasgeekProvider, "HTML", "JSON-LD (schema.org)"),
    ProviderMeta("luma", LumaProvider, "HTML", "Embedded __NEXT_DATA__ JSON"),
    # --- Phase 3G expansion ---
    ProviderMeta("atlassian", AtlassianProvider, "JSON", "Bevy REST (ace.atlassian.com)"),
    ProviderMeta("salesforce", SalesforceProvider, "JSON", "Bevy REST (trailblazer)"),
    ProviderMeta("snowflake", SnowflakeProvider, "JSON", "Bevy REST (usergroups)"),
    ProviderMeta("devpost", DevpostProvider, "JSON", "Devpost hackathon API"),
]
SKIPPED: list[SkippedMeta] = [
    SkippedMeta("microsoft-reactor", "—", "SPA (Akamai)", "Bot-protected; no public API"),
    SkippedMeta("aws-events", "JSON", "/api/dirs", "Needs directoryId; weak India yield"),
    SkippedMeta("sessionize", "JSON", "per-event API", "No discovery/list API; per-event only"),
    SkippedMeta(
        "eventyay", "JSON", "Open Event API", "~0 upcoming India events (Singapore-centric)"
    ),
    # --- Phase 3G investigation skips (evidence in spikes/probe_providers*.py) ---
    SkippedMeta("meetup.com", "—", "SPA + Cloudflare", "API now Pro-only (paid); anti-bot"),
    SkippedMeta("eventbrite", "—", "OAuth", "Public search API removed (2019); no ₹0 discovery"),
    SkippedMeta("allevents.in", "HTML", "JSON-LD", "Mixes entertainment/expos — poor signal"),
    SkippedMeta("10times.com", "HTML", "JSON-LD", "Expo/trade-show heavy; quality + dedup risk"),
    SkippedMeta("commudle", "—", "SPA", "Public API 503/blocked; Angular shell only"),
    SkippedMeta("unstop", "—", "SPA", "Data behind undocumented API; shell only"),
    SkippedMeta("aws-community", "JSON", "Bevy?", "403 blocked"),
    SkippedMeta("mongodb / postman", "JSON", "—", "404 — not Bevy-hosted"),
    SkippedMeta("hashicorp / twilio / uipath", "—", "—", "DNS / SSL failure — no reachable API"),
    SkippedMeta(
        "meetup discovery", "—", "GraphQL", "Group search is client-side — not enumerable at ₹0"
    ),
]

# Config-driven ICS family: one observability entry per curated feed (parameterized builder).
WORKING += [
    ProviderMeta(
        s.id,
        lambda s=s: ICSProvider(
            name=s.id, ics_url=s.ics_url, city=s.city, category=s.category
        ),
        "ICS",
        "iCalendar (.ics)",
    )
    for s in ICS_SOURCES
]


@dataclass
class Sample:
    meta: ProviderMeta
    events: list[Event]
    elapsed_ms: float
    ok: bool


@dataclass
class ProviderStats:
    name: str
    status: str
    source_type: str
    api_type: str
    events_fetched: int
    upcoming: int
    india: int
    categories: list[str]
    cache_enabled: bool
    last_fetch: str
    failure_count: int
    avg_fetch_ms: float
    duplicate_count: int
    surviving: int


@dataclass
class GlobalStats:
    total_providers: int
    working: int
    skipped: int
    merged_events: int
    total_real_events: int
    total_india_events: int
    category_distribution: dict[str, int]
    duplicate_percentage: float
    avg_latency_ms: float
    slowest: str
    fastest: str


async def collect(metas: list[ProviderMeta]) -> list[Sample]:
    """Run each provider once (cold fetch) and time it. Never raises."""
    samples: list[Sample] = []
    for meta in metas:
        provider = meta.factory()
        start = time.perf_counter()
        try:
            events = await provider.search(SearchQuery())
            ok = True
        except Exception:  # noqa: BLE001 - observability must not crash on a bad provider
            events, ok = [], False
        elapsed_ms = (time.perf_counter() - start) * 1000
        samples.append(Sample(meta, events, elapsed_ms, ok))
    return samples


def build_stats(
    samples: list[Sample],
    skipped: list[SkippedMeta],
    today: date,
    generated_at: str,
) -> tuple[list[ProviderStats], GlobalStats]:
    """Pure aggregation: per-provider stats + global stats, including dedup attribution."""
    merged = [event for sample in samples for event in sample.events]
    survivors = deduplicate(merged)
    survivor_ids = {id(event) for event in survivors}

    provider_stats: list[ProviderStats] = []
    for sample in samples:
        surviving = sum(1 for e in sample.events if id(e) in survivor_ids)
        provider_stats.append(
            ProviderStats(
                name=sample.meta.name,
                status="working" if sample.ok else "failed",
                source_type=sample.meta.source_type,
                api_type=sample.meta.api_type,
                events_fetched=len(sample.events),
                upcoming=sum(1 for e in sample.events if e.start_date >= today),
                india=len(sample.events),  # every provider is India-scoped by design
                categories=sorted({e.category.value for e in sample.events}),
                cache_enabled=True,
                last_fetch=generated_at if sample.ok else "—",
                failure_count=0 if sample.ok else 1,
                avg_fetch_ms=round(sample.elapsed_ms, 1),
                duplicate_count=len(sample.events) - surviving,
                surviving=surviving,
            )
        )
    for sk in skipped:
        provider_stats.append(
            ProviderStats(
                name=sk.name,
                status="skipped",
                source_type=sk.source_type,
                api_type=sk.api_type,
                events_fetched=0,
                upcoming=0,
                india=0,
                categories=[],
                cache_enabled=False,
                last_fetch="—",
                failure_count=0,
                avg_fetch_ms=0.0,
                duplicate_count=0,
                surviving=0,
            )
        )

    ok_latencies = [(s.meta.name, s.elapsed_ms) for s in samples if s.ok]
    duplicates = len(merged) - len(survivors)
    global_stats = GlobalStats(
        total_providers=len(samples) + len(skipped),
        working=sum(1 for s in samples if s.ok),
        skipped=len(skipped),
        merged_events=len(merged),
        total_real_events=len(survivors),
        total_india_events=len(survivors),
        # Post-classification (what search actually returns); per-provider
        # `categories` below stay raw (what each provider produces).
        category_distribution=dict(
            collections.Counter(
                classify_category(e).value for e in survivors
            ).most_common()
        ),
        duplicate_percentage=round(duplicates / len(merged) * 100, 1) if merged else 0.0,
        avg_latency_ms=round(sum(v for _, v in ok_latencies) / len(ok_latencies), 1)
        if ok_latencies
        else 0.0,
        slowest=max(ok_latencies, key=lambda x: x[1])[0] if ok_latencies else "—",
        fastest=min(ok_latencies, key=lambda x: x[1])[0] if ok_latencies else "—",
    )
    return provider_stats, global_stats


def render_markdown(provider_stats: list[ProviderStats], g: GlobalStats, generated_at: str) -> str:
    lines: list[str] = [
        "# Provider Analytics",
        "",
        f"_Auto-generated by `analytics/provider_analytics.py` at {generated_at}. "
        "Do not edit by hand._",
        "",
        "## Global statistics",
        "",
        f"- **Total providers:** {g.total_providers} ({g.working} working, {g.skipped} skipped)",
        f"- **Total real events (deduped):** {g.total_real_events}",
        f"- **Total India events:** {g.total_india_events}",
        f"- **Merged (pre-dedup):** {g.merged_events} → "
        f"**duplicate rate:** {g.duplicate_percentage}%",
        f"- **Average provider latency:** {g.avg_latency_ms} ms",
        f"- **Slowest provider:** {g.slowest} · **Fastest provider:** {g.fastest}",
        "",
        "### Category distribution (deduped, post-classification)",
        "",
        "| Category | Events |",
        "|----------|--------|",
    ]
    for cat, count in g.category_distribution.items():
        lines.append(f"| {cat} | {count} |")

    lines += [
        "",
        "## Provider profile",
        "",
        "| Provider | Status | Source type | API type | Cache | Last successful fetch |",
        "|----------|--------|-------------|----------|-------|-----------------------|",
    ]
    for p in provider_stats:
        lines.append(
            f"| {p.name} | {p.status} | {p.source_type} | {p.api_type} | "
            f"{'yes' if p.cache_enabled else '—'} | {p.last_fetch} |"
        )

    lines += [
        "",
        "## Provider metrics",
        "",
        "| Provider | Events fetched | Upcoming | India | Categories | Failures | "
        "Avg fetch (ms) | Duplicates | Surviving dedup |",
        "|----------|----------------|----------|-------|------------|----------|"
        "----------------|------------|-----------------|",
    ]
    for p in provider_stats:
        cats = ", ".join(p.categories) if p.categories else "—"
        lines.append(
            f"| {p.name} | {p.events_fetched} | {p.upcoming} | {p.india} | {cats} | "
            f"{p.failure_count} | {p.avg_fetch_ms} | {p.duplicate_count} | {p.surviving} |"
        )
    lines.append("")
    return "\n".join(lines)


def output_path() -> Path:
    # backend/analytics/provider_analytics.py -> project root
    return Path(__file__).resolve().parents[2] / "PROVIDER_ANALYTICS.md"


async def main() -> None:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    samples = await collect(WORKING)
    provider_stats, global_stats = build_stats(samples, SKIPPED, date.today(), generated_at)
    markdown = render_markdown(provider_stats, global_stats, generated_at)
    path = output_path()
    path.write_text(markdown, encoding="utf-8")
    print(
        f"wrote {path} — {global_stats.working} working providers, "
        f"{global_stats.total_real_events} deduped events"
    )


if __name__ == "__main__":
    asyncio.run(main())
