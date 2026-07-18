"""Promotion Engine (Phase 7A) — generate a PromotionPlan. NEVER applied to production.

Promotion here means producing a **blueprint** for how a source would become an ingestion provider:
provider type (from the discovery feed type), configuration, refresh interval, retry policy,
declared capabilities, expected volume, and a risk assessment. 7A stops at the plan — no registry
write, no scheduler entry, no provider instance. Actual registration is Phase 7B (behind explicit
approval). Deterministic; derived from the candidate's evidence.
"""

from __future__ import annotations

from app.onboarding.models import OnboardingConfidence, PromotionPlan, SandboxOutcome

# Discovery feed type → how a real provider would ingest it.
_PROVIDER_TYPE = {
    "rss": "rss",
    "atom": "atom",
    "ics": "ics",
    "google_calendar": "ics",
    "json_feed": "json_feed",
    "jsonld_event": "structured_html",
    "microdata_event": "structured_html",
    "opengraph_event": "structured_html",
    "event_sitemap": "sitemap",
    "next_data": "framework_hydration",
    "next_flight": "framework_hydration",
    "hydration_state": "framework_hydration",
    "embedded_json": "framework_hydration",
    "json_api": "json_api",
    "graphql": "graphql",
    "ai_extracted": "ai_assisted",
    "search_result": "crawl_pending",
    "unknown": "manual",
}
_PARSER_HINT = {
    "rss": "feed parser (RSS 2.0)",
    "atom": "feed parser (Atom)",
    "ics": "iCalendar VEVENT parser",
    "json_feed": "JSON Feed parser",
    "structured_html": "schema.org Event (JSON-LD/microdata) parser",
    "sitemap": "sitemap → per-event structured parse",
    "framework_hydration": "extract from hydration payload (needs field mapping)",
    "json_api": "probe endpoint, map JSON → event schema",
    "graphql": "introspect + map GraphQL → event schema",
    "ai_assisted": "AI-extracted fields; requires human verification before ingest",
    "crawl_pending": "run D1/D2 crawl first to determine a concrete parser",
    "manual": "undetermined — manual analysis required",
}


def _expected_volume(plausible_events: int) -> tuple[str, int]:
    """(volume band, refresh interval hours) — richer sources refresh more often."""
    if plausible_events >= 20:
        return "high", 6
    if plausible_events >= 5:
        return "medium", 12
    return "low", 24


def _retry_policy(volume: str) -> dict:
    # Mirrors the shape of the ingestion RetryPolicy (Phase 3B) as DATA — not wired to anything.
    base = {"high": 120, "medium": 300, "low": 600}[volume]
    return {
        "failure_threshold": 3,
        "backoff_seconds": base,
        "cooldown_seconds": base * 5,
        "max_attempts": 3,
    }


def _capabilities(provider_type: str) -> list[str]:
    caps = ["list_events"]
    if provider_type in {"rss", "atom", "json_feed", "ics"}:
        caps.append("delta_sync")
    if provider_type in {"ai_assisted", "crawl_pending", "json_api", "graphql"}:
        caps.append("requires_validation")
    return caps


def _risk(snap: dict, confidence: OnboardingConfidence, sandbox: SandboxOutcome) -> dict:
    factors: list[str] = []
    feed = snap.get("feed_type", "unknown")
    if feed in {"search_result", "unknown"}:
        factors.append("unproven source type")
    if feed in {"ai_extracted", "json_api", "graphql"}:
        factors.append("needs validation/probing before ingestion")
    if sandbox.plausible_events == 0:
        factors.append("no event evidence")
    if float(snap.get("india_confidence", 0.0)) < 0.5:
        factors.append("weak India relevance")
    if confidence.total < 0.5:
        factors.append("low onboarding confidence")

    if (
        feed in {"search_result", "unknown"}
        or sandbox.plausible_events == 0
        or confidence.total < 0.5
    ):
        level = "high"
    elif factors:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "factors": factors}


def build_promotion_plan(
    snapshot: dict, confidence: OnboardingConfidence, sandbox: SandboxOutcome
) -> PromotionPlan:
    feed = snapshot.get("feed_type", "unknown")
    provider_type = _PROVIDER_TYPE.get(feed, "manual")
    volume, refresh = _expected_volume(sandbox.plausible_events)
    return PromotionPlan(
        url=snapshot["url"],
        domain=snapshot["domain"],
        provider_type=provider_type,
        configuration={
            "url": snapshot["url"],
            "domain": snapshot["domain"],
            "parser_hint": _PARSER_HINT.get(provider_type, "manual"),
            "source_feed_type": feed,
        },
        refresh_interval_hours=refresh,
        retry_policy=_retry_policy(volume),
        capabilities=_capabilities(provider_type),
        expected_volume=volume,
        risk_assessment=_risk(snapshot, confidence, sandbox),
        notes=[
            "PLAN ONLY — not applied to production (7A stops before promotion).",
            "Registration into the registry/scheduler is Phase 7B, behind explicit approval.",
        ],
    )
