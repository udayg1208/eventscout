"""Phase 7B live demonstration (not a test): controlled production operations, fully deterministic.

Takes PromotionPlans (as 7A would emit) and drives them through the control plane:
Preflight → Registry → Scheduler → Canary → Health → Rollback|Active → Learning → Analytics.
Includes a healthy provider, failing providers (rolled back), a preflight failure, and a live
provider that degrades after going active (continuous-monitoring rollback). Then a learning report
calibrates confidence. NO network, NO LLM, NO real provider — a deterministic mock canary.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.onboarding.models import PromotionPlan  # noqa: E402
from app.operations import (  # noqa: E402
    CanaryMetrics,
    MockCanarySync,
    OperationsEngine,
    SQLiteOperationsStore,
    provider_id_for,
)
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402


def plan(domain, ptype, *, refresh=12, vol="medium", risk="low", feed="rss", caps=("list_events",)):
    return PromotionPlan(
        url=f"https://{domain}/feed",
        domain=domain,
        provider_type=ptype,
        configuration={"url": f"https://{domain}/feed", "domain": domain, "source_feed_type": feed},
        refresh_interval_hours=refresh,
        retry_policy={"failure_threshold": 3, "backoff_seconds": 300, "cooldown_seconds": 1500},
        capabilities=list(caps),
        expected_volume=vol,
        risk_assessment={"level": risk, "factors": []},
        notes=["PLAN ONLY — staged by 7A"],
    )


# (plan, prediction, canary metrics) — a realistic mix.
PLANS = [
    (
        plan("gdg.community.dev", "rss", vol="high", feed="rss"),
        {"confidence": 0.87, "discovered_by": "crawl", "was_manual": False},
        CanaryMetrics(fetched=14, valid=14, duplicates=2, new_events=12, latency_ms=180),
    ),
    (
        plan("fossunited.org", "ics", feed="ics"),
        {"confidence": 0.74, "discovered_by": "crawl", "was_manual": False},
        CanaryMetrics(fetched=8, valid=8, duplicates=1, new_events=7, latency_ms=240),
    ),
    (
        plan("reactindia.io", "structured_html", vol="low", feed="jsonld_event"),
        {"confidence": 0.82, "discovered_by": "crawl", "was_manual": True},
        CanaryMetrics(fetched=6, valid=6, duplicates=0, new_events=6, latency_ms=300),
    ),
    (
        plan("sketchy-events.io", "crawl_pending", vol="low", risk="high", feed="search_result"),
        {"confidence": 0.55, "discovered_by": "search", "was_manual": True},
        CanaryMetrics(fetched=9, valid=1, duplicates=9, new_events=0, latency_ms=8000, failures=4),
    ),
    (
        plan("broken-feed.net", "rss", feed="rss"),
        {"confidence": 0.7, "discovered_by": "crawl", "was_manual": False},
        CanaryMetrics(fetched=10, valid=2, duplicates=1, new_events=1, latency_ms=500),
    ),  # parser fail
    (
        plan("undetermined.com", "manual", feed="unknown"),  # fails preflight
        {"confidence": 0.5, "discovered_by": "search", "was_manual": True},
        CanaryMetrics(fetched=0, valid=0, new_events=0, fetch_success=False),
    ),
]


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="p7b_"))
    state = SQLiteProviderStateStore(str(tmp / "provider_state.db"))
    store = SQLiteOperationsStore(str(tmp / "operations.db"))
    scenarios = {provider_id_for(p.domain): m for p, _, m in PLANS}
    engine = OperationsEngine(state, store, MockCanarySync(scenarios))

    print("=== Phase 7B — Controlled Production Operations (deterministic, no network) ===\n")
    print("PIPELINE  Plan → Preflight → Registry → Scheduler → Canary → Health → Active|Rollback\n")

    for p, prediction, _ in PLANS:
        reg = await engine.promote(p, prediction=prediction)
        marker = {
            "active": "✔ ACTIVE",
            "rolled_back": "✘ ROLLED BACK",
            "failed_preflight": "⊘ FAILED PREFLIGHT",
        }.get(reg.state.value, reg.state.value)
        print(f"  {reg.domain:22s} [{reg.provider_type:16s}] canary×{reg.canary_syncs} → {marker}")

    # ---- continuous monitoring: a healthy provider degrades after going active ----
    print("\n=== CONTINUOUS MONITORING ===")
    degraded = CanaryMetrics(
        fetched=10, valid=1, duplicates=10, new_events=0, latency_ms=200, failures=5
    )
    pid = provider_id_for("fossunited.org")
    out = await engine.continuous_sync(pid, degraded)
    print(f"  {out.domain}: live sync degraded (dup + zero-events + failures) → {out.state.value}")

    # ---- health snapshots ----
    print("\n=== PROVIDER HEALTH (reused Provider State Store) ===")
    for p, _, _ in PLANS:
        pid = provider_id_for(p.domain)
        h = await engine.health(pid)
        if h:
            print(
                f"  {p.domain:22s} status={h.health_status:9s} uptime={h.uptime:.2f} "
                f"quality={h.event_quality:.2f} dup%={h.duplicate_pct:.2f} trend={h.success_trend}"
            )

    # ---- learning / calibration ----
    report = await engine.learn()
    print("\n=== LEARNING REPORT (predicted vs observed — analytics only, no ML) ===")
    print(f"  sample={report.sample}  calibration_error={report.calibration_error}")
    for b in report.buckets:
        print(
            f"    conf [{b.lower:.2f},{b.upper:.2f})  n={b.count}  predicted={b.predicted_mean:.2f}"
            f"  observed={b.observed_rate:.2f}  Δ={b.delta:+.2f}"
        )
    print(f"  suggested confidence adjustments by feed type: {report.model.adjustments}")
    for r in report.reasons:
        print(f"    · {r}")

    # ---- feedback ----
    fb = engine.feedback(stale_providers=0)
    print("\n=== FEEDBACK SIGNALS ===")
    print(
        f"  sandbox_accuracy={fb.sandbox_accuracy}  confidence_accuracy={fb.confidence_accuracy}  "
        f"approval_accuracy={fb.approval_accuracy}  provider_quality={fb.provider_quality}  "
        f"manual_overrides={fb.manual_overrides}"
    )

    # ---- analytics ----
    a = engine.analytics()
    print("\n=== OPERATIONS ANALYTICS ===")
    print(
        f"  total_promotions={a.total_promotions}  active={a.active}  rolled_back={a.rolled_back}  "
        f"failed_preflight={a.failed_preflight}"
    )
    print(
        f"  promotion_success_rate={a.promotion_success_rate}  "
        f"canary_success_rate={a.canary_success_rate}  rollback_rate={a.rollback_rate}"
    )
    print(
        f"  discovery_precision={a.discovery_precision}  review_precision={a.review_precision}  "
        f"confidence_calibration_error={a.confidence_calibration_error}"
    )
    print(f"  growth_velocity={a.growth_velocity} active providers  by_type={a.by_provider_type}")
    print(f"  by_state={a.by_state}")
    canary_n = len(await store.history("canary"))
    rollback_n = len(await store.history("rollback"))
    learning_n = len(await store.history("learning"))
    print(
        f"\n  history streams (nothing deleted): "
        f"canary={canary_n} rollback={rollback_n} learning={learning_n}"
    )

    await state.close()
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
