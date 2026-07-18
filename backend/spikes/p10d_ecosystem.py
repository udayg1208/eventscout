"""Phase 10D live demonstration: the Ecosystem Expansion Engine (fixtures, no network).

Builds a small Organizer Graph with 10C (GDG Bangalore + a campus ACM chapter), then expands it with
10D: one organizer fans out into sibling chapters, series instances, sponsor programs, campus units,
similar communities, and connected resources — each a Discovery Seed with a relationship path and
explainable confidence. Shows graph growth, duplicate suppression, confidence, relationship paths,
and budget enforcement. Deterministic; the output is Discovery Seeds, not Event objects.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.ecosystem import EcosystemExpansionEngine, ExpansionBudget, SeedKind  # noqa: E402
from app.organizers import OrganizerIntelligenceEngine  # noqa: E402

NOW = datetime(2026, 7, 16, tzinfo=UTC)

GDG = (
    '<html><head><meta property="og:site_name" content="GDG Bangalore"></head>'
    "<body><h1>GDG Bangalore</h1>Google Developer Group Bangalore runs DevFest and Build with AI. "
    "Python, Kubernetes, AI, Cloud. Sponsored by Google. Venue: Bangalore."
    '<a href="https://github.com/gdg-bangalore">GitHub</a>'
    '<a href="https://discord.gg/gdgblr">Discord</a></body></html>'
)
ACM = (
    "<html><body><h1>ACM IIIT Delhi</h1>ACM student chapter at IIIT Delhi. AI, systems, robotics. "
    "Monthly workshops.</body></html>"
)


def main() -> None:
    print("=== Phase 10D — Ecosystem Expansion Engine (fixtures, no network) ===\n")
    org = OrganizerIntelligenceEngine(clock=lambda: NOW)
    org.ingest("https://gdgblr.dev/", GDG)
    org.ingest("u", "<h1>GDG Delhi</h1>Google Developer Group Delhi. DevFest. Python. Delhi.")
    org.ingest("https://iiitd.ac.in/acm", ACM)
    print(
        f"10C organizer graph: {org.graph.as_dict()['counts']['nodes']} nodes, "
        f"{len(org.organizer_ids())} organizers\n"
    )

    eco = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=5, min_confidence=0.25))
    report = eco.expand_from(org)

    print("STEP · expand every known organizer → Discovery Seeds")
    print(
        f"  generated={report.seeds_generated}  merged(duplicates)={report.seeds_merged}  "
        f"unique={eco.seeds.as_dict()['count']}"
    )
    print(f"  by kind: {eco.seeds.by_kind()}\n")

    print("TOP DISCOVERY SEEDS (by confidence):")
    for s in eco.recommend(limit=12):
        row = f"[{s.confidence:.2f}] {s.kind.value:18s} {s.target[:28]:28s}"
        print(f"  {row} :: {s.path.render()[:50]}")

    print("\nRELATIONSHIP PATHS (why a seed exists):")
    for kind in (
        SeedKind.SPONSOR_PROGRAM,
        SeedKind.SERIES_INSTANCE,
        SeedKind.UNIVERSITY_UNIT,
        SeedKind.SIMILAR_ORGANIZER,
    ):
        s = next((x for x in eco.seeds.all() if x.kind is kind), None)
        if s:
            print(f"  {s.kind.value:18s} {s.path.render()}")

    print("\nCONFIDENCE BREAKDOWN (a sponsor program):")
    sp = next((s for s in eco.seeds.all() if s.kind is SeedKind.SPONSOR_PROGRAM), None)
    if sp:
        parts = ", ".join(f"{k}={v:.2f}" for k, v in sp.confidence_breakdown.items())
        print(f"  {sp.target}: {parts}")

    print("\nDUPLICATE SUPPRESSION (re-run collapses everything):")
    r2 = eco.expand_from(org)
    print(
        f"  re-run generated={r2.seeds_generated}, merged={r2.seeds_merged}, "
        f"seed count stable at {eco.seeds.as_dict()['count']}"
    )

    print("\nBUDGET (graph-explosion guard):")
    for b in (
        ExpansionBudget(max_branches=10, max_seeds=200, min_confidence=0.2),
        ExpansionBudget(max_branches=3, max_seeds=10, min_confidence=0.4),
    ):
        e = EcosystemExpansionEngine(budget=b)
        rep = e.expand_from(org)
        print(
            f"  branches={b.max_branches} max_seeds={b.max_seeds} min_conf={b.min_confidence} "
            f"→ {e.seeds.as_dict()['count']} seeds, budget_stops={rep.budget_stops}"
        )

    print("\n  ✔ Discovery Seeds (not events); provenance + relationship paths; no network/LLM")


if __name__ == "__main__":
    main()
