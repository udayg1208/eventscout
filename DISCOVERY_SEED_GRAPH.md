# Discovery Seed Graph — Phase 10D

A companion to [ECOSYSTEM_EXPANSION.md](ECOSYSTEM_EXPANSION.md), focused on the *output*: the Discovery
Seed Graph — what a seed is, how equivalent seeds collapse, how relationship paths explain them, how the
budget bounds the graph, and how it persists and grows.

## What a Discovery Seed is

An `ExpansionSeed` is a **new target for discovery**, not an event and not an organizer (yet):

```
ExpansionSeed
  kind          chapter_sibling | series_instance | sponsor_program | university_unit |
                venue_unit | similar_organizer | connected_resource
  target        "GDG Chennai"                      (the new ecosystem to go find)
  target_key    canonical identity key             (for dedup, reused from 10C)
  source        the organizer it was expanded from
  reason        one-line human explanation
  confidence    explainable 0..1 + 7-signal breakdown
  provenance    a D4 Provenance record
  path          the RelationshipPath that produced it
  search_hint   a query to hand to discovery ("GDG Chennai tech community")
  alt_paths     other routes that also produced this seed
```

The seed is deliberately a *lead*: it says "there is probably a GDG in Chennai — go look, here's a query
and here's why we think so." Confirming it is discovery's job (10A/10B), not 10D's.

## Relationship paths — why a seed exists

Every seed carries a `RelationshipPath` (nodes + relations) rendered as a chain:

```
GDG Bangalore --[sponsors]--> Google --[runs_program]--> Google Cloud Arcade
ACM IIIT Delhi --[belongs_to]--> IIIT Delhi --[has_unit]--> Robotics Club
```

This is the audit trail: an operator (or a downstream validator) can see the exact reasoning that
produced a lead and judge it before spending a fetch on it. The path's depth also feeds the confidence
(closer = stronger).

## One seed, many routes — duplicate resolution

Seeds key on `(kind, canonical target)`, and the canonical target uses **10C's identity
canonicalization** — so "GDG Delhi" and "Google Developer Group Delhi" are the *same* seed. When a
second route reaches an existing seed, the graph:

1. keeps the **strongest** confidence (and its breakdown/reason), and
2. **records the alternate path** on `alt_paths`.

So a seed reached by both a chapter-sibling fan-out and a series instance is one entry that remembers
both derivations. A full re-expansion therefore collapses completely — idempotent by construction.

## Budget — bounding the graph

Generative expansion is combinatorial, so the `ExpansionBudget` is the governor:

| Knob | Effect |
|---|---|
| `max_branches` | cap seeds per expander per source (truncates the city/program fan-out) |
| `max_seeds` | hard cap on total seeds per run (stops the run, counted in `budget_stops`) |
| `min_confidence` | drop weak leads at generation time |
| `max_depth` | bound the relationship-path length |
| `cooldown_runs` | skip a source re-expanded within N runs (incremental re-expansion) |

Plus a structural filter: a generated sibling that equals an **already-known organizer** is dropped as
redundant (a new ecosystem, by definition, isn't one you already have).

## Persistence & incrementality

The `SeedGraph` persists via `SeedStore` — InMemory (the live object) or SQLite (one JSON row per seed,
keyed by `(kind, canonical target)`, `INSERT OR REPLACE`). Because the key is stable, a scheduled
re-expansion **upserts** rather than duplicates; the relationship path and alternate paths survive the
round-trip (the D4 `Provenance` object does not — its *reason* does). The engine accumulates seeds across
runs in memory and `persist()`/`load_from_store()` round-trips the whole graph.

## Scaling

- **Now:** in-memory + SQLite, single process; similar-organizer is O(n²) over organizers; generation is
  bounded by the budget.
- **Better:** block similar-organizer comparisons by chapter/city; rank the city/program fan-out by a
  real prior (observed presence) instead of a fixed list order, so `max_branches` keeps the *likely*
  siblings.
- **The loop:** the intended closed loop is **10C graph → 10D seeds → 10A/10B verify → new organizers →
  back into 10C → 10D …**, gated by the `SeedValidator` / `ExpansionScheduler` seams (deferred).

## Honest self-review (seed-graph view)

- **The graph is a candidate graph, not a knowledge graph.** Its nodes are *hypotheses* ("GDG Chennai
  probably exists"), unlike 10C's organizer graph whose nodes are extracted from real pages. Reading a
  seed as a fact would be wrong — it's a prioritized to-check list.
- **Idempotent dedup is real and verified**, but it's exact-identity dedup: it won't merge two seeds that
  describe the same ecosystem under different names it can't canonicalize, nor across kinds (by design).
- **Confidence orders the list well but isn't calibrated to existence.** Without the validator loop, a
  0.69 seed isn't "69% likely to exist" — it's "ranks above a 0.58 seed". Treat it as ranking, not
  probability.
- **Budget truncates, it doesn't prioritize.** Capping the fan-out at `max_branches` keeps the first N by
  generation order, which is not the same as the N most likely — a known limitation until a presence
  prior ranks the cities.

---

**Status:** 10D complete — additive, deterministic, generative; Discovery Seeds with relationship paths;
idempotent dedup; budget-bounded; InMemory + SQLite persistence; 812 tests green; no browser/LLM/network.
**Stopping here — Phase 10E NOT started.**
