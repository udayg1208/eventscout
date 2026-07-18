"""Phase 10F live demonstration: the Continuous Autonomous Growth Scheduler (fixtures, no network).

Drives the full growth loop over the REAL engines — 10C organizers → 10D ecosystem expansion → 10E
seed validation → the existing Discovery Inbox → onboarding (human-gated, simulated) → production
monitoring → growth metrics → detected opportunities → the next expansion cycle. Runs many cycles
until the system reaches a steady state, then advances the clock a week and adds a new organizer to
show the loop *reacting* and growing again. Deterministic: the discovery fetcher/searcher are
fixtures — no network, no browser, no LLM; nothing is onboarded/promoted automatically.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys
from datetime import UTC, datetime, timedelta

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.fetch import FetchResult  # noqa: E402
from app.ecosystem import DEFAULT_BUDGET, EcosystemExpansionEngine  # noqa: E402
from app.growth import (  # noqa: E402
    GrowthBudgetEngine,
    GrowthEngine,
    GrowthInputs,
    OpportunitySignals,
    SeedBuffer,
    TaskKind,
    make_expansion_step,
    make_onboarding_step,
    make_organizer_refresh_step,
    make_production_monitor_step,
    make_validation_step,
)
from app.organizers import OrganizerIntelligenceEngine  # noqa: E402
from app.validation import RetryPolicy, SeedValidationEngine  # noqa: E402

CLOCK = [datetime(2026, 7, 17, tzinfo=UTC)]

GOOD_CITIES = {"bangalore", "delhi", "mumbai", "pune", "chennai", "hyderabad", "kolkata", "noida"}


def _page(city: str) -> str:
    return (
        f'<html><head><meta property="og:site_name" content="GDG {city}">'
        f'<script type="application/ld+json">{{"@type":"Event","name":"DevFest {city} 2026",'
        f'"startDate":"2026-11-01","location":{{"@type":"Place","name":"{city}",'
        f'"address":{{"addressLocality":"{city}"}}}}}}</script></head>'
        f"<body><h1>GDG {city}</h1>Google Developer Group {city}. DevFest. Python, AI. {city}."
        "</body></html>"
    )


PARKED = "<html><body>This domain is for sale. Contact us to buy.</body></html>"


class MixedFetcher:
    """A reachable page for known-city slugs (real events) else a parked page — a realistic mix."""

    async def get(self, url: str):
        low = url.lower()
        for city in GOOD_CITIES:
            if city in low:
                return FetchResult(url=url, status=200, content_type="text/html", text=_page(city))
        return FetchResult(url=url, status=200, content_type="text/html", text=PARKED)


class NoSearcher:
    def search(self, query):
        return []


def organizer_cities(org: OrganizerIntelligenceEngine) -> set[str]:
    out = set()
    for oid in org.organizer_ids():
        prof = org.profile(oid)
        city = prof.get("city") if prof else None
        if city:
            out.add(str(city))
    return out


async def main() -> None:
    print("=== Phase 10F — Continuous Autonomous Growth Scheduler (fixtures, no network) ===\n")

    org = OrganizerIntelligenceEngine(clock=lambda: CLOCK[0])
    org.ingest_organizer(
        "GDG Bangalore", text="Google Developer Group Bangalore, a GDG chapter in Bangalore, India."
    )

    eco = EcosystemExpansionEngine(budget=dataclasses.replace(DEFAULT_BUDGET, max_seeds=8))
    inbox = InMemoryDiscoveryInbox()
    val = SeedValidationEngine(
        inbox,
        MixedFetcher(),
        searcher=NoSearcher(),
        clock=lambda: CLOCK[0],
        retry=RetryPolicy(max_retries=2, cooldown_runs=1),
    )
    buffer = SeedBuffer()
    health = {"failures": 0}

    async def promote(n: int) -> int:  # simulated, human-approved 7A onboarding
        return n

    steps = {
        TaskKind.EXPANSION: make_expansion_step(org, eco, buffer),
        TaskKind.VALIDATION: make_validation_step(val, buffer),
        TaskKind.ONBOARDING: make_onboarding_step(buffer, promote_hook=promote),
        TaskKind.PRODUCTION_MONITOR: make_production_monitor_step(lambda: _health(health)),
        TaskKind.ORGANIZER_REFRESH: make_organizer_refresh_step(
            org, {"GDG Bangalore": ("https://gdg-bangalore.dev/", _page("Bangalore"))}
        ),
    }

    def inputs() -> GrowthInputs:
        cities = organizer_cities(org)
        # clean city names from GDG chapter-sibling seeds ("GDG Chennai" -> "Chennai")
        seed_cities = {
            s.target.split()[-1]
            for s in eco.seeds.all()
            if s.target.startswith("GDG ") and len(s.target.split()) == 2
        }
        return GrowthInputs(
            # stale-organizer refreshes are handled by the planner via the freshness engine, so we
            # don't also feed them as opportunities (that would double-count).
            signals=OpportunitySignals(
                organizer_cities=cities, seed_cities=seed_cities, now=CLOCK[0]
            ),
            has_seed_backlog=bool(buffer.pending_seeds),
            has_onboarding_backlog=buffer.pending_candidates > 0,
            cities_known=cities | seed_cities,
            cities_covered=cities,
        )

    eng = GrowthEngine(
        steps=steps,
        budget=GrowthBudgetEngine(clock=lambda: CLOCK[0]),
        inputs_provider=inputs,
        clock=lambda: CLOCK[0],
    )

    print(f"SEED: 1 organizer ({org.organizer_ids()[0]}), empty inbox\n")
    await _run_wave(eng, inbox, buffer, "WAVE 1 — cold start", max_cycles=16)

    # --- react to change: a week passes and a new organizer appears ---
    CLOCK[0] += timedelta(days=8)
    health["failures"] = 4  # production trouble shows up
    org.ingest_organizer(
        "GDG Hyderabad", text="Google Developer Group Hyderabad, a GDG chapter in Hyderabad, India."
    )
    print(
        f"\n>>> 8 days later ({CLOCK[0].date()}): new organizer 'GDG Hyderabad' ingested; "
        f"4 production failures observed <<<\n"
    )
    await _run_wave(eng, inbox, buffer, "WAVE 2 — react & regrow", max_cycles=16)

    print("\n=== FINAL GROWTH METRICS ===")
    for k, v in eng.metrics.snapshot().as_dict().items():
        print(f"    {k:22s}: {v}")

    print("\n=== DASHBOARD SNAPSHOT ===")
    snap = eng.snapshot(now=CLOCK[0])
    print(f"    backlog        : {snap.backlog}")
    print(f"    budgets        : {snap.budgets}")
    opp = [o["kind"] + ":" + o["target"] for o in snap.opportunities]
    shown = ", ".join(opp[:6]) + (f"  (+{len(opp) - 6} more)" if len(opp) > 6 else "")
    print(f"    opportunities  : {shown}")
    print(f"    recommendations: {[r['kind'] for r in snap.recommendations]}")

    print(
        f"\n=== DISCOVERY INBOX (discovered_by=validation, status=NEW): "
        f"{await inbox.count()} candidates ==="
    )
    for c in (await inbox.list(limit=6)):
        print(f"    [{c.classification:16s}] conf={c.discovery_confidence:.2f} {c.url}")

    print(
        "\n  ✔ the loop grew EventScout autonomously from 1 organizer — expansion → validation →\n"
        "    inbox → onboarding → production → opportunities → expansion — reaching steady state\n"
        "    each wave; no providers/weights/queries changed automatically; no network/LLM."
    )


async def _health(state):
    return dict(state)


async def _run_wave(eng, inbox, buffer, title, *, max_cycles):
    print(f"--- {title} ---")
    start_run = eng.run_count()
    idle = 0
    for _ in range(max_cycles):
        rec = await eng.run_cycle(now=CLOCK[0])
        o = rec.outcome
        detail = (
            f"seeds+{o['seeds_generated']} val{o['seeds_validated']} "
            f"acc{o['accepted']} rej{o['rejected']} prom{o['promoted']} fail{o['failures']}"
        )
        kind = rec.task_kind or "idle"
        print(
            f"  cycle {rec.run:2d}: {kind:18s} [{detail}]  "
            f"inbox={await inbox.count()} backlog={eng.queue.backlog()}"
        )
        idle = idle + 1 if rec.task_kind is None else 0
        if idle >= 3:
            print(f"  → steady state reached after {rec.run - start_run} cycles")
            break


if __name__ == "__main__":
    asyncio.run(main())
