# Organizer & Community Intelligence Engine — Phase 10C

Discovers the **organizers** — the people, orgs, clubs, chapters, communities and recurring ecosystems
that continuously *generate* events — rather than individual events. The output is an **Organizer
Graph** (typed nodes + typed edges), never Event objects. Once one organizer is found, its ecosystem
(chapter parent, university, series, sponsors, calendars, feeds, social channels) is expanded
automatically, so EventScout learns the *sources* of events instead of chasing one event at a time.

Code: `backend/app/organizers/` (new package — additive). It **reuses** D4's provenance model, 10B's
text helpers (`strip_tags`, `detect_technologies`, `detect_location`) and provenance builders, and D1's
domain util, and **modifies nothing** (D1–D4, 7A–7B, 8A–8D, 9A, 10A, 10B, Search, Repository, Registry,
Scheduler, Event model, API, Frontend). No network, no browser, no LLM; discovery only — the catalog is
never touched.

## The graph model

**21 node types** — Organization, Community, MeetupGroup, UniversityClub, University, Department,
Chapter, StudentChapter, ProfessionalSociety, ConferenceSeries, RecurringEvent, Sponsor, Venue,
Website, Calendar, Feed, GitHubOrg, NotionWorkspace, Discord, Telegram, LinkedInPage.

**13 relation types** — organizes, hosts, belongs_to, chapter_of, sponsors, uses_calendar, uses_feed,
announces_on, member_of, partner_of, same_community, same_series, recurring.

The `OrganizerGraph` supports incremental `add_node` (merges by id), `add_edge` (dedups by
source+relation+target), `merge_nodes` (folds one node into another, reassigning edges), neighbour /
type queries, and **named views** — `community_view()` and `series_view()` return the Community Graph
and Series Graph as filtered subgraphs.

## Architecture

```
app/organizers/
  models.py        NodeType (21) · RelationType (13) · Health · Cadence · OrganizerProfile (16 fields)
                   · Node · Edge · OrganizerGraph (+ community/series views)
  taxonomy.py      chapter families · series patterns · university units · sponsor/cadence patterns
  identity.py      canonicalization + alias resolution (the "GDG = Google Developer Group" merge)
  chapters.py      detect_chapter — GDG/GDSC/IEEE/ACM/PyData/… family + implied node type
  series.py        detect_series — DevFest/Hacktoberfest/… + cadence
  university.py    detect_university_name + detect_university_units (dept/club/student-chapter/CoE)
  extract.py       OrganizerExtractor — page → provenance-bearing OrganizerProfile
  similarity.py    CommunitySimilarity — 8-signal explainable score
  relationships.py RelationshipDiscoverer — expand one organizer into its ecosystem subgraph
  confidence.py    OrganizerConfidence — 8-signal explainable score
  health.py        classify_health — active/dormant/inactive/seasonal/new
  prediction.py    predict_opportunity — deterministic recurrence reasoning
  engine.py        OrganizerIntelligenceEngine — ingest, resolve, expand, query
  store.py         GraphStore (InMemory + SQLite) — incremental knowledge-graph persistence
  interfaces.py    future seams: SocialChannelFetcher · GraphDatabaseBackend (NotImplementedError)
```

## Organizer extraction

`OrganizerExtractor.extract(url, html)` produces an `OrganizerProfile` — 16 provenance-bearing fields:
name, aliases, parent_org, chapter, university, department, community, series, sponsors, venue,
domains, calendars, feeds, social_pages, city, technologies. Name comes from JSON-LD organizer /
`og:site_name` / `<h1>` / `<title>`; social/calendar/feed links are classified by URL pattern
(github.com, discord.gg, t.me, linkedin.com, *.notion.site, *.ics, /feed). Every value cites its
snippet; anything unsupported is **UNKNOWN**.

## Identity resolution

The hard, distinctive piece: "GDG Bangalore", "Google Developer Group Bangalore", "Google Developers
Group Bangalore" are **one** organizer; "IEEE MUJ", "IEEE Student Branch MUJ", "IEEE MUJ SB" are **one**.
Canonicalization: lowercase → expand known abbreviations (GDG → *google developer group*, SB → *student
branch*, UG → *user group*, TFUG → *tensorflow user group*) → singularize common plurals
(developers → developer) → drop identity-neutral filler (student, branch, group, chapter, …) → reduce to
an **order-independent token set**. Same token set → same organizer.

```
GDG Bangalore                       → {bangalore, developer, google}
Google Developer Group Bangalore    → {bangalore, developer, google}   ← merged
Google Developers Group Bangalore   → {bangalore, developer, google}   ← merged
GDG Pune                            → {developer, google, pune}        ← distinct (city differs)

IEEE MUJ / IEEE Student Branch MUJ / IEEE MUJ SB → {ieee, muj}          ← all merged
```

## Chapter, series & university detection

- **Chapters** (17 families): GDG, GDSC, IEEE, ACM, CSI, Mozilla, AWS UG, Kubernetes, Cloud Native,
  PyData, PyLadies, TFUG, React, Rust, Linux, FOSS United, Python UG — each implying a node type
  (chapter / student chapter / professional society).
- **Series** (10 brands): DevFest, Build with AI, Hacktoberfest, Cloud Community Day, Google Cloud
  Arcade, PyCon, FOSS Meetup, Study Jam, Monthly Meetup, Weekly Workshop — each with a cadence
  (an explicit "monthly"/"weekly" in the text overrides the default).
- **University**: the institution (IIT/NIT/BITS/… or "X University/College/Institute") and the campus
  unit (department, club, student chapter, innovation cell, incubator, centre of excellence).

## Relationship discovery — auto-expansion

`RelationshipDiscoverer.expand` turns one organizer into a connected subgraph from what extraction found:
chapter parent (`chapter_of`), university/department (`belongs_to`), each series (`organizes` +
`recurring`), each sponsor (`sponsors`), the venue (`hosts`), calendars (`uses_calendar`), feeds
(`uses_feed`), and every website/GitHub/Discord/Telegram/LinkedIn/Notion channel (`announces_on`). One
GDG page becomes ~14 nodes and ~16 edges.

## Confidence, health & opportunity — explainable, deterministic

- **Confidence** (8 signals, weights sum to 1): recurring-series presence, structured-metadata quality,
  social presence, external references, organizer web presence, calendars, feeds, identity consistency.
- **Health**: `new` (just appeared) · `active` (hosted within ~1.5 cadence periods) · `seasonal`
  (sparse-but-regular annual/quarterly, between occurrences) · `dormant` (overdue a few periods) ·
  `inactive` (long silent) — from the event history + cadence.
- **Opportunity**: projects the next expected date and rates the probability of an upcoming
  announcement — e.g. *"usually hosts monthly; last event 33d ago → due now → high probability of an
  upcoming announcement"*. No ML.

## Community similarity

`CommunitySimilarity.score` compares two organizers over 8 signals (same organizer, chapter, series,
university, city, technologies, venue, sponsors), weighted and explained. `engine.link_similar()` uses
it to add `same_community` / `same_series` edges — building the community & series graphs beyond direct
expansion.

## Live demonstration

`backend/spikes/p10c_organizers.py` (fixtures, no network) walks the full flow:

```
STEP 1-2  'GDG Bangalore' + 'Google Developers Group Bangalore' → org:bangalore developer google  (merged)
STEP 3    chapter=gdg  community=Google Developer Group  type=chapter
STEP 4-7  calendars/feeds/github/discord/telegram/linkedin all found
STEP 8    series=[DevFest, Build with AI, Monthly Meetup]  confidence=0.87  health=active
          prediction: [high] usually hosts monthly; last event 33d ago → due now → upcoming announcement
STEP 9    graph: 14 nodes, 16 edges  (chapter_of · organizes · hosts · uses_calendar · announces_on · …)
          IEEE MUJ aliases merged; GDG Bangalore ~same_community~ GDG Delhi ~same_series~
```

## Tests

`backend/tests/test_organizers.py` — **76 tests, fixtures only, no network/browser/LLM**: identity
(GDG/IEEE alias merges, distinct cities, abbreviations, filler), chapters/series/university detection,
extraction (full profile, hint, JSON-LD parent, social/calendar/feed links, provenance), the graph
model (merge, dedup, merge_nodes, views), similarity + confidence (weights sum to 1, total = Σ,
explained), health (all five states), prediction (all four buckets), relationship expansion, the engine
end-to-end (ingest, alias merge, ecosystem, confidence/health/prediction, link_similar, incremental
merge), and both stores. Full backend suite: **731 passed**.

## Honest self-review

**Truly true**
- Identity resolution really merges the alias families the brief names, and keeps distinct cities
  distinct. One organizer page expands into a real ecosystem subgraph. Health/prediction produce the
  exact "hosts monthly → due now → high probability" reasoning, deterministically. Every field cites a
  snippet.

**Weaknesses / limitations**
1. **Identity resolution is token-set based, not fuzzy/ML.** It nails the enumerated abbreviations but
   an unknown abbreviation (not in the expansion map) won't merge, and two genuinely different orgs with
   the same distinctive token set *would* merge. It also drops word order, so pathological reorderings
   could over-merge. No edit-distance, no learning.
2. **The chapter/series taxonomy is a hand-curated list.** Families/series not enumerated are missed,
   and some patterns are broad — "Rust"/"React"/"Linux" match any page that merely mentions the tech, so
   a chapter can be over-attributed. It's a keyword taxonomy, not understanding.
3. **Health & prediction depend on event dates the caller supplies.** 10C does not fetch an organizer's
   event history; it reasons over whatever dates are recorded plus a cadence inferred from text/series
   defaults (not observed frequency). Garbage-in applies; a wrong cadence skews the prediction.
4. **"Auto-expand" materialises what the page already exposed — it does not fetch.** The GitHub/Discord/
   LinkedIn nodes come from links on the page; 10C never visits them (that's the `SocialChannelFetcher`
   seam). So the ecosystem is as complete as the source page's links, no more.
5. **The parent-chapter node is a global aggregation, not a fetched org.** "Google Developer Group" is
   inferred from the family; it's a hub node connecting siblings, not a verified real organization.
6. **Confidence is hand-calibrated structural, not learned**, and community linking is O(n²) pairwise —
   fine at small scale, not for a huge graph.
7. **Byte-level only.** A pure-runtime SPA organizer page that exposes nothing in served bytes yields
   nothing — the same ceiling as 10B, liftable only by the deferred browser seam.

## Future integration (NOT this phase)

`interfaces.py` marks the seams: `SocialChannelFetcher` (pull a public GitHub org / Discord landing page
to enrich a channel node — 8D public-only rules) and `GraphDatabaseBackend` (back the graph with a real
graph DB for cross-source scale). The engine also composes naturally with **10B** (a UniversalEvent's
organizer/community fields feed `ingest_organizer`) and **10A** (discovered pages feed `ingest`). All
deferred, no network/LLM in 10C.

---

**Status:** 10C complete. Additive; every frozen system untouched; 731 tests green; provenance-bearing,
deterministic, byte-level; no browser/LLM/network; discovery only — Organizer Graph, not events.
**Stopping here — Phase 10D NOT started.**
