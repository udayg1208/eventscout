# Community Discovery — Phase 8D

Where the tech-event world actually lives is not just conference websites — it's **communities**:
a GDG chapter's LinkedIn, a PyData Discord, a FOSS United Telegram channel, a college's GitHub org, a
Notion handbook of meetups. Phase 8D discovers these public community surfaces and turns them into
Discovery Inbox candidates. Companion to **[SOCIAL_DISCOVERY_ENGINE.md](SOCIAL_DISCOVERY_ENGINE.md)**
(the engine).

## The community thesis

Events are announced *where the community gathers*. A single organizer often has:

```
        organizer (e.g. GDG Bangalore)
        ├─ LinkedIn company page   → event posts
        ├─ GitHub org              → devfest repo, discussions, releases
        ├─ Discord server          → community + announcements (invite landing is public)
        ├─ Telegram channel        → public announcements
        ├─ Notion handbook         → schedule of workshops/hackathons
        └─ blog (Substack/Medium)  → event write-ups + RSS
```

Traditional discovery (D1–D2) sees the organizer's *website*. Community discovery sees the other six
surfaces — each a public lead the crawler and inbox can pursue. Together with 8C's graph, a single
organizer becomes a cluster of connected sources.

## What is public vs. what we never touch

The line is bright and structural:

| Platform | We read (public) | We NEVER touch |
|---|---|---|
| LinkedIn | company pages, public posts, public articles | private profiles, connections, anything behind the auth wall |
| GitHub | discussions, releases, orgs, READMEs (all public) | private repos, anything needing a token |
| Discord | the public **invite landing page** metadata | joining the server, any channel, member lists |
| Telegram | public **channel/invite landing** pages | private groups, member data, message history behind auth |
| Notion | pages the owner made **public** | private/shared-with-me pages |
| Blogs/Forums | public posts and threads | member-only posts, paywalled content |

The Discord and Telegram modules are deliberately minimal: they read only the landing-page metadata
(the server/channel name + description that the platform renders for anyone), then hand off a
**community candidate**. We never join, authenticate, or read private content — and that is a
permanent design boundary, not a temporary limitation (see the engine doc's self-review).

## From a community page to a candidate

Each public page yields a provenance-bearing `SocialExtraction` (title/date/location/organizer/
registration/technology/community/calendar/feed/related links), which normalizes to a Discovery
Inbox candidate:

- `discovered_by = "social"`, `status = NEW`
- `classification` = the platform (linkedin/github/discord/telegram/notion/blog/forum)
- `feed_type` = ICS (a calendar), RSS (a feed), or SEARCH_RESULT (a community/organizer page)
- `discovery_confidence` = the priority score; `city`/`organization`/`technology_confidence` from
  the extraction

The candidate is a **lead to inspect**, not a confirmed event. A Discord community node says "there's
a Rust community here worth watching"; a LinkedIn event post with JSON-LD says "here's a specific
event". Both stop at the inbox for review.

## How community discovery feeds the rest

- **8C (expansion graph)** already emits `GITHUB`/`NOTION`/`DISCORD`/`TELEGRAM`/`BLOG`/`COMMUNITY`
  nodes when it crawls an organizer site. 8D is the extractor that *understands* those nodes' public
  pages — the two compose: 8C finds the community surfaces, 8D reads them.
- **8B (web discovery)** surfaces community URLs from search ("GDG Bangalore LinkedIn", "PyData
  Discord"); their public HTML feeds 8D.
- **7A onboarding** later decides whether a discovered community source becomes a provider — with a
  human in the loop, because community content is user-generated and noisier than a curated feed.

## Community-quality signals (priority)

Community sources are ranked with the same explainable priority: a **known organizer** (GDG, FOSS
United, PyData, CNCF, Hasgeek, IEEE, …) scores highest on reputation; **structured data** (a JSON-LD
event on a LinkedIn post) beats a bare OpenGraph title; **tech relevance** and **freshness** filter
the noise. This is what separates "a real community that runs events" from "a random public page".

## Ethics & safety of community discovery

Community discovery is powerful and must be handled carefully:

- **Public only, always.** We never log in, never join, never bypass access controls. If a page asks
  us to sign in, we decline it.
- **No private data.** We extract event/organizer signals, not people. Member lists, private
  messages, and personal profiles are out of scope.
- **Human-gated onboarding.** Nothing a community page yields is onboarded or promoted automatically;
  a person reviews before anything reaches production. Given user-generated content's noise and
  moderation risk, that human gate is the essential safeguard.

## Limitations (honest)

- **Client-rendered platforms leak little.** LinkedIn/Discord/Telegram render via JavaScript; from
  raw HTML we usually get only the OpenGraph title — a *community lead*, not a full event.
- **Markup churn.** These platforms redesign often; extractors degrade until updated.
- **False positives.** A community node isn't a confirmed event source; a blog *about* an event isn't
  the event. Recall-first, human-confirmed.

---

**Status:** community discovery turns the six public community surfaces around an organizer into
Discovery Inbox leads — public-only, provenance-bearing, human-gated. The layer that finds where the
tech-event community actually gathers, composing with 8C's graph and 8B's search.
