# Ecosystem Expansion Engine — Phase 10D

Expands outward from **every** known organizer, community, chapter, sponsor, venue, and recurring
series (the 10C Organizer Graph) to discover **entirely new ecosystems**. The output is new **Discovery
Seeds** (`ExpansionSeed`) — targets for discovery (10A/10B) to go find and verify — **never Event
objects**. One organizer becomes dozens of leads: its sibling chapters in other cities, its series
instances, its sponsor's programs, its campus's clubs, its similar communities, and every public
resource it's connected to.

Code: `backend/app/ecosystem/` (new package — additive). It **reuses** 10C's graph, identity
canonicalization, and similarity, plus D4 provenance, and **modifies nothing** (D1–D4, 7A–7B, 8A–8D,
9A, 10A–10C, Search, Repository, Registry, Scheduler, API, Frontend, Event model). No network, no
browser, no LLM. Discovery only — the catalog is never touched.

## The transform

```
Known Organizer (10C)
   │  expand
   ▼
Website · GitHub · LinkedIn · Discord · Telegram · RSS · Calendar   (connected resources)
Sponsors → Sponsor Programs        (Google → Build with AI, Cloud Arcade, …)
Chapter  → Sibling Chapters        (GDG Bangalore → GDG Delhi / Mumbai / Jaipur / …)
Series   → Series Instances        (DevFest → DevFest Delhi / Pune / …)
University/Venue → Campus Units     (IIIT Delhi → ACM / IEEE / GDSC / E-Cell / Robotics Club / …)
Similar Organizers                 (deterministic 10C similarity)
   │
   ▼
NEW Discovery Seeds  (each with a relationship path + explainable confidence + provenance)
```

## The seven isolated expanders

| Expander | From → to | Seed kind |
|---|---|---|
| `ConnectedResourceExpander` | organizer → its own github/discord/feed/calendar/sponsor/venue/… | `connected_resource` |
| `ChapterExpander` | GDG Bangalore → GDG Delhi / Mumbai / … | `chapter_sibling` |
| `SeriesExpander` | DevFest → DevFest Delhi / Pune / … | `series_instance` |
| `SponsorExpander` | Google → Google Developers / Build with AI / Cloud Arcade / … | `sponsor_program` |
| `UniversityExpander` | IIIT Delhi → ACM Chapter / IEEE Branch / GDSC / E-Cell / Robotics Club / … | `university_unit` |
| `VenueExpander` | a campus venue → the clubs it hosts | `venue_unit` |
| `SimilarOrganizerExpander` | deterministic 10C similarity → nearby communities | `similar_organizer` |

Each is independent, takes an `ExpansionContext` (the source organizer + its 10C profile + the graph +
the path so far), and returns provenance-bearing `ExpansionSeed`s.

## Graph traversal

`ConnectedResourceExpander` walks the organizer's real 10C edges (both directions — a sponsor points
*at* the organizer). The other expanders are **generative**: they fan a known family across a curated
set of cities / programs / campus units (`templates.py`), producing *seeds to check* — a generated
"GDG Chennai" is a target for discovery to confirm, not an asserted fact. Every seed records the
**relationship path** that produced it, e.g.:

```
GDG Bangalore --[sponsors]--> Google --[runs_program]--> Google Cloud Arcade
ACM IIIT Delhi --[belongs_to]--> IIIT Delhi --[has_unit]--> ACM Student Chapter
GDG Delhi --[similar_to]--> GDG Bangalore
```

## Confidence — explainable, seven signals

`total = Σ(component × weight)`, weights summing to 1.0, each explained:

| Signal | Weight | Meaning |
|---|---|---|
| relationship_strength | 0.22 | the kind of link (chapter_of/organizes strong, announces_on weaker) |
| graph_distance | 0.20 | `1/(1+depth)` — closer is stronger |
| chapter_overlap | 0.14 | same chapter family as the source |
| organizer_overlap | 0.12 | shared organizer identity signal |
| technology_overlap | 0.12 | Jaccard of tech stacks |
| sponsor_overlap | 0.10 | shared sponsor |
| recurring_history | 0.10 | derives from a recurring series |

## Duplicate resolution & budget

- **Dedup:** seeds are keyed by `(kind, canonical target)` — reusing 10C's identity canonicalization —
  so "GDG Delhi" reached via chapter-sibling *and* via a series instance collapse into one seed, keeping
  the strongest confidence and **recording the alternate path**. Re-running the whole expansion collapses
  entirely (verified: a second run merges 100% of seeds, count unchanged).
- **Budget (graph-explosion guard):** `max_depth`, `max_branches` (per expander per source), `max_seeds`
  (per run), `min_confidence`, and `cooldown_runs` (skip a source re-expanded too recently — incremental).
  A generated sibling that equals an *already-known* organizer is skipped as redundant.

## Live demonstration

`backend/spikes/p10d_ecosystem.py` (fixtures, no network) builds a 3-organizer 10C graph and expands it:

```
10C graph: 14 nodes, 3 organizers
expand → generated=45  merged(duplicates)=10  unique=35
by kind: connected_resource 8 · chapter_sibling 9 · series_instance 6 · sponsor_program 5 ·
         similar_organizer 2 · university_unit 5

TOP SEEDS:  [0.69] chapter_sibling GDG Chennai   ::  GDG Bangalore --[same_chapter]--> GDG Chennai
            [0.58] series_instance DevFest Delhi ::  GDG Bangalore --[same_series]--> DevFest Delhi
sponsor path:  GDG Bangalore --[sponsors]--> Google --[runs_program]--> Google Cloud Arcade
              (sponsor_overlap=1.00, recurring_history=1.00, relationship_strength=0.70)

DUPLICATE SUPPRESSION: re-run merged=45, seed count stable at 35
BUDGET: branches=10 → 60 seeds; branches=3 max_seeds=10 → 6 seeds, 14 budget_stops
```

## Tests

`backend/tests/test_ecosystem.py` — **81 tests, fixtures only, no network/browser/LLM**: models
(path/seed/graph/budget/report), templates, the seven-signal confidence (weights sum to 1, total = Σ,
graph-distance falls with depth, clipping), dedup (identity merge, equivalent paths), each of the seven
expanders (generation, empty cases, `max_branches`, paths, confidence signals), and the engine
(dedup-across-sources, known-organizer filter, `max_seeds`/`min_confidence`/`cooldown` budgets,
incremental accumulation, `expand_from` a 10C engine, recommend), plus both stores. Full backend suite:
**812 passed**.

## Honest self-review

**Truly true**
- One organizer really does fan out into dozens of leads across all seven expanders, each with a
  relationship path explaining *why* and an explainable confidence. Equivalent paths collapse; the
  budget genuinely bounds the fan-out; re-runs are idempotent.

**Weaknesses / limitations**
1. **Seeds are generated candidates, not verified facts.** A "GDG Chennai" or "Build with AI Delhi" is a
   *target to check* — it may not exist. 10D does no fetching; the `SeedValidator` seam (feed a seed to
   10A/10B) is deferred. So the *precision* of the seed list is unknown until downstream discovery runs.
2. **Template-driven coverage is arbitrary.** Cities, sponsor programs, and campus units are hand-curated
   lists — sponsor programs exist only for ~6 big sponsors; an unlisted city or sponsor is missed, and
   the "first N cities" cut-off under budget is not a principled ranking of where a family actually
   operates.
3. **The fan-out is combinatorial.** chapter×cities, series×cities, sponsor×programs can explode; the
   budget caps it, but capping by `max_branches` truncates rather than prioritizes — the *most likely*
   sibling isn't necessarily kept.
4. **Confidence is hand-calibrated and structural.** It ranks seeds sensibly (a sponsor program with tech
   overlap beats a distant generic one) but is not a probability that the ecosystem exists; it can't be,
   without verification.
5. **Traversal is shallow.** Paths are depth 1–2; there's no deep multi-hop chaining (sponsor → program →
   that program's sub-communities → …). `max_depth` exists but the expanders emit fixed shallow depths.
6. **Dedup is by identity key, across a single kind.** The same target under two *kinds* stays two seeds
   (intentional — a chapter sibling and a series instance are different leads), but a genuinely distinct
   organizer that canonicalizes to the same tokens would wrongly merge.
7. **Similar-organizer is O(n²).** Fine for a small graph; needs blocking (by chapter/city) at scale.

## Future integration (NOT this phase)

`interfaces.py` marks the seams (`NotImplementedError`): a **`SeedValidator`** that hands each seed to
real discovery (10A/10B) to confirm the ecosystem exists and promote survivors into the Discovery Inbox,
and an **`ExpansionScheduler`** that re-expands continuously (cooldown-aware) as the 10C organizer graph
grows. The natural loop is **10C organizer graph → 10D seeds → 10A/10B verify → new organizers → 10C →
10D …**, all deferred behind approval.

---

**Status:** 10D complete. Additive; every frozen system untouched; 812 tests green; deterministic,
generative, provenance + relationship paths; no browser/LLM/network; discovery only — Discovery Seeds,
not events. **Stopping here — Phase 10E NOT started.**
