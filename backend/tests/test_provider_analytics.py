"""Provider analytics: pure aggregation + rendering (no network)."""

from __future__ import annotations

from datetime import date

from analytics.provider_analytics import (
    ProviderMeta,
    Sample,
    SkippedMeta,
    build_stats,
    render_markdown,
)
from app.models.event import Event, EventCategory
from app.providers.gdg import GDGProvider  # placeholder factory (never called here)

TODAY = date(2026, 7, 14)
GEN_AT = "2026-07-14 10:00 UTC"


def _event(title, *, provider, start, category=EventCategory.MEETUP, city=None, description=None):
    return Event(
        title=title,
        url=f"https://example.com/{provider}/{title.replace(' ', '')}",
        city=city,
        description=description,
        start_date=start,
        category=category,
        provider=provider,
    )


def _samples():
    d1, d2 = date(2026, 8, 1), date(2026, 9, 1)
    a = Sample(
        meta=ProviderMeta("a", GDGProvider, "JSON", "REST"),
        events=[
            _event("Alpha", provider="a", start=d1, category=EventCategory.MEETUP),
            _event("Shared Conf", provider="a", start=d2, category=EventCategory.CONFERENCE),
        ],
        elapsed_ms=50.0,
        ok=True,
    )
    b = Sample(
        meta=ProviderMeta("b", GDGProvider, "JSON", "REST"),
        events=[  # duplicate of A's "Shared Conf" but richer -> B survives, A drops
            _event(
                "Shared Conf",
                provider="b",
                start=d2,
                category=EventCategory.CONFERENCE,
                city="Pune",
                description="rich",
            ),
        ],
        elapsed_ms=120.0,
        ok=True,
    )
    c = Sample(
        meta=ProviderMeta("c", GDGProvider, "JSON", "REST"),
        events=[],
        elapsed_ms=5.0,
        ok=False,
    )
    return [a, b, c]


def test_dedup_attribution_and_global_stats():
    skipped = [SkippedMeta("reactor", "—", "SPA", "bot-protected")]
    stats, g = build_stats(_samples(), skipped, TODAY, GEN_AT)
    by_name = {s.name: s for s in stats}

    # A contributed 2, one of which (Shared Conf) is a duplicate that B wins.
    assert by_name["a"].events_fetched == 2
    assert by_name["a"].surviving == 1
    assert by_name["a"].duplicate_count == 1
    assert by_name["a"].status == "working"
    assert by_name["a"].upcoming == 2

    assert by_name["b"].surviving == 1
    assert by_name["b"].duplicate_count == 0

    assert by_name["c"].status == "failed"
    assert by_name["c"].failure_count == 1
    assert by_name["c"].last_fetch == "—"

    assert by_name["reactor"].status == "skipped"

    assert g.merged_events == 3
    assert g.total_real_events == 2
    assert g.total_india_events == 2
    assert g.duplicate_percentage == 33.3
    assert g.working == 2
    assert g.skipped == 1
    assert g.total_providers == 4  # 3 sampled + 1 skipped
    assert g.avg_latency_ms == 85.0  # (50 + 120) / 2, C excluded (failed)
    assert g.slowest == "b" and g.fastest == "a"
    assert g.category_distribution == {"meetup": 1, "conference": 1}


def test_render_markdown_contains_key_sections():
    stats, g = build_stats(_samples(), [], TODAY, GEN_AT)
    md = render_markdown(stats, g, GEN_AT)
    assert "# Provider Analytics" in md
    assert "Auto-generated" in md
    assert "duplicate rate:** 33.3%" in md
    assert "| a | working |" in md
    assert "Category distribution" in md
    assert GEN_AT in md
