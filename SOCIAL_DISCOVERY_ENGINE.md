# Social Discovery Engine — Phase 8D

Extends EventScout beyond traditional event websites to discover events announced on **publicly
accessible community platforms** — LinkedIn public pages, GitHub, Discord/Telegram public landing
pages, Notion public pages, blogs, and forums. **Public content only:** no login, no auth bypass, no
browser, no LLM. Every extracted field carries provenance; UNKNOWN is always preferred over a guess.
Output stops at the Discovery Inbox (`discovered_by="social"`, `status=NEW`).

Code: `backend/app/discovery/social/` (new subpackage — additive). It **reuses** D4's provenance
model and D1's link/feed extractors, and modifies nothing (Search, Repository, Catalog, D1–D4, the
Expansion Engine 8C, Onboarding, Production, scheduler, frontend, API).

## Supported public sources

| Platform | Module | What (public only) |
|---|---|---|
| LinkedIn | `linkedin.py` | company pages, public event/creator posts, public articles (Pulse) — never private profiles |
| GitHub | `github.py` | discussions, releases, orgs, READMEs, event/community repos |
| Discord | `discord.py` | the public **invite landing page** only — never joins, never private channels |
| Telegram | `telegram.py` | public **channel / invite landing** pages only — never private groups |
| Notion | `notion.py` | public pages — workshops, hackathons, meetups, schedules, calendars |
| Blogs | `blog.py` | Medium, Dev.to, Hashnode, Substack, WordPress, Blogger |
| Forums | `forum.py` | Discourse, phpBB, Flarum, Vanilla — public discussions only |

Each module exposes `matches(url, html)` and `extract(url, html, *, now) -> SocialExtraction`. **All
platform-specific logic lives inside its module**; the engine only routes.

## Extraction architecture

Every page runs through shared extraction (`extractor.build_common`) plus platform specifics. For
each page it detects **title, date, location, organizer, registration URL, technology, community,
calendar, feed, related links** — using JSON-LD Event parsing, OpenGraph/`<title>` metadata, the 5A
tech taxonomy, `city.detect_city`, and D1's reused link/feed extractors. Platform modules add what
only they know (LinkedIn company slug, GitHub org, Discord/Telegram server/channel name, blog
author).

```
app/discovery/social/
  models.py       SocialPlatform (7) · SocialExtraction (10 provenance fields) · SocialPriority
  extractor.py    build_common (JSON-LD/OG/taxonomy/links) + safety_check + FieldBuilder
  linkedin/github/discord/telegram/notion/blog/forum.py   per-platform matches() + extract()
  normalizer.py   to_candidate — SocialExtraction → Discovery Inbox candidate (discovered_by=social)
  priority.py     score — 6-factor explainable SocialPriority
  engine.py       SocialDiscoveryEngine.discover(pages) → SocialDiscoveryReport
  store.py        SocialStore (InMemory + SQLite) — full provenance audit, keyed by url
  interfaces.py   future seams: SocialPageFeed (8B/8C), RenderedSocialExtractor (8E)
```

## Provenance model

Reuses D4's `ExtractedField {value, status, provenance}` where `provenance = {source_snippet,
reason, confidence, method, timestamp}`. A field exists only if grounded in a real snippet; anything
unsupported is `UNKNOWN` (value `None`). Values inferred from evidence (a detected city as location)
are `INFERRED`, never `EXTRACTED`. The full record is persisted to the `SocialStore`; the inbox
candidate carries the distilled verdict (`classification=platform`, `discovery_confidence=priority`).

From the live spike:
```
title            = 'DevFest Bangalore 2026'   (JSON-LD/og/title @0.90)
date             = '2026-11-01'               (JSON-LD startDate @0.90)
location         = 'Bangalore'                (JSON-LD location @0.85)
registration_url = 'https://lu.ma/devfest-blr'(registration link @0.75)
```

## Priority

`score(extraction) -> SocialPriority` (0..1), weights summing to 1.0: organizer reputation (0.20),
tech relevance (0.25), public accessibility (0.15), structured data (0.20), freshness (0.10),
historical yield (0.10). Every factor is inspectable (`score × weight` + reason) and the total is
exactly their weighted sum. In the demo the JSON-LD-rich LinkedIn DevFest scored **0.87** (known org
+ structured data + tech + city); a bare Telegram channel scored 0.45.

## Safety boundaries

The `safety_check` gate rejects a page (no candidate) when it:
- **requires auth** — a login/paywall marker (`authwall`, "sign in to continue/view", "members
  only", "subscribe to read"). We **DECLINE** — we never bypass, simulate a login, or read behind
  the wall.
- is **off-topic** — gambling, adult, politics, religion, shopping, entertainment (casino/betting/
  porn/election/movie-tickets/…).
- has **no positive evidence** — no technology, title, or community signal.

The design is public-content-only by construction: the Discord/Telegram modules read only the public
invite/channel *landing* metadata, never joining or accessing private content. In the demo, a
login-walled LinkedIn post and a gambling Discord invite were both correctly rejected.

## Live demonstration (fixtures, no network)

`spikes/p8d_social_discovery.py`:
```
processed 8 · matched 7 · unmatched 1 · rejected 2 · inserted 5
by platform: linkedin 2 (1 walled) · github 1 · notion 1 · telegram 1 · discord 2 (1 gambling) · blog 1
REJECTED [linkedin]: login/paywall 'Sign in to view'   ·   REJECTED [discord]: off-topic 'Betting'
INBOX (discovered_by=social): linkedin conf 0.87 (Bangalore) · github 0.70 · blog 0.69 · discord 0.62 · notion 0.52 (Delhi) · telegram 0.45
✔ public content only — no login, no browser; stops at the Discovery Inbox
```

## Testing

`tests/test_social_discovery.py` — **11 tests, fixtures only, NO network**: per-platform extraction
(LinkedIn/GitHub/Discord/Telegram/Notion/blog/forum), provenance (present on known fields, UNKNOWN
never fabricated), scoring (weights sum to 1, total = Σ factors, known-org high), safety (login-wall
+ off-topic rejection), and the engine end-to-end (matched/rejected/inserted, discovered_by=social,
provenance persisted). Full backend suite: **514 tests**.

## Scaling strategy

- **Extraction is O(1) per page** — regex + JSON parse, no network in the engine; throughput is
  bounded by however pages are supplied, not by the engine.
- **The candidate identity is the normalized URL** — re-discovery upserts/dedups, so the inbox
  doesn't bloat as the same community pages recur across sources.
- **The registry is additive** — a new platform is one module (`matches` + `extract`); the engine
  never changes.
- **Storage is the storage-agnostic pattern** (SQLite → Postgres) — the provenance audit scales like
  the rest of the system.

## Future integration with 8B and 8C

8D consumes `(url, html)` pairs — it does not fetch. The natural wiring (the `SocialPageFeed` seam):
- **8C (expansion)** already discovers Discord/Telegram/GitHub/Notion/blog nodes and crawls in-scope
  pages; those public HTML pages flow straight into 8D for event extraction.
- **8B (web discovery)** surfaces social-platform URLs from search; their public pages (fetched
  politely by 8B/8C's `PoliteFetcher`) feed 8D.

So 8D is the *understanding* layer over the public-social HTML that 8B/8C fetch — no new fetching,
no new network surface.

## Honest self-review

**Truly true**
- Every extracted field traces to a real snippet; UNKNOWN is never fabricated; the safety gate
  rejects login walls and off-topic pages; public-only is structural (Discord/Telegram read landing
  metadata, never join).

**Weaknesses / limitations**
1. **HTML-only — misses client-rendered content.** LinkedIn, Discord, and Telegram render most of
   their real content via JavaScript; the raw HTML often exposes only OpenGraph metadata (a title +
   description), not the full event. So on those platforms we typically get a *community/source
   lead*, not a fully-parsed event. The `RenderedSocialExtractor` seam (Phase 8E, still public-only)
   is where a renderer would help.
2. **Login walls limit reach — by design.** Much of LinkedIn (and all private Discord/Telegram) is
   behind auth. We decline those pages; we do not and will not bypass them, so public reach is a
   genuine ceiling, not a bug to fix.
3. **Public-content-only is a hard constraint.** We can't see members-only events, gated
   registration, or private community calendars. That's an ethical boundary, not a gap to close.
4. **Platform markup changes break extractors.** Each module keys on current class/meta/URL
   patterns; a platform redesign (LinkedIn/Discord change markup often) silently degrades extraction
   until the module is updated. Regex-over-HTML is inherently brittle.
5. **False positives.** OpenGraph titles are generic ("GDG India" is a community, not an event); a
   blog post *about* an event isn't itself an event source; a GitHub repo may be a library, not a
   community. The engine leans toward recall (surface the lead) — some candidates will not be real
   event sources, and only a later crawl/onboarding confirms them.
6. **Moderation risks.** Public community content is user-generated; a public Discord invite or forum
   thread can be spam, low-quality, or misclassified. The off-topic filter is keyword-based and
   evadable; it is a coarse gate, not content moderation. Nothing is onboarded automatically, so a
   human still reviews before anything goes live — that is the real safeguard.

## Where Phase 8E begins (NOT this phase)

8D reads public HTML deterministically. Phase 8E — **AI-Assisted Deep Discovery & Rendered
Content** — would add browser-rendered extraction for JS-heavy public social pages and AI extraction
of unstructured community posts (still public-only, still no auth). Both are larger capabilities and
require explicit approval.

---

**Status:** 8D complete. Additive; D1–D4 / 8B / 8C / frozen systems untouched; 514 tests green;
public-content-only, provenance-bearing, safety-gated, discovery-only. **Stopping here — Phase 8E
NOT started.**
