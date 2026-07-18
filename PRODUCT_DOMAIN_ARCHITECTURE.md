# Opportunity Intelligence Platform — Domain & Product Architecture

**A five-year product vision. Implementation-independent: no code, no storage, no
frameworks — only the domain, the capabilities, the flows, and the boundaries.**

---

## 0. The thesis — what the product becomes

The product stops being "a place to search for events." It becomes a **living, trustworthy,
continuously-updated map of every opportunity in the world, and the intelligence to put the
right opportunity in front of the right person at the right moment.**

Two assets are the **core domain** — the defensible IP the whole company is built to own:

1. **The Canonical Opportunity Graph** — every opportunity, organization, person, topic and
   place, de-duplicated from thousands of messy sources into one clean, connected,
   provenance-tracked truth.
2. **The Matching Intelligence** — the understanding of *people* (goals, skills, stage) and
   of *opportunities* deep enough to match them better than anyone else.

Everything else — ingestion, search plumbing, notifications, identity — is **supporting** or
**generic**. A CTO's job is to make sure the best engineering effort compounds into those two
assets and that generic work is kept generic.

**Four structural commitments** shape the entire domain:

- **Canonical vs. Source duality.** Every real-world thing (an opportunity, a company, a
  person) exists twice: as many raw **Source Records** (what each provider claimed) and as one
  **Canonical Record** (the resolved truth). This duality is the backbone of trust and
  correctness and appears in almost every entity.
- **The graph is the product.** The value isn't a list; it's the connections —
  opportunity ↔ organization ↔ person ↔ topic ↔ place. The graph enables what a flat search
  never can ("fellowships from organizations like this one," "conferences where this mentor
  speaks," "the path from this internship to that career").
- **Taxonomy, trust and time are first-class citizens**, not attributes bolted on later.
- **The feedback loop is the moat.** Discover → save → apply → outcome produces data no
  competitor has, and it compounds.

---

## 1. The Domain Model

Organized into seven contexts. Each entity: **purpose · relationships · future growth.**

### A. The Opportunity Core — *the catalog (core domain)*

**Opportunity** — the central entity: a single, canonical, time-bound chance to participate
(a conference, scholarship, grant, internship, hackathon, fellowship, hiring drive…).
*Relationships:* offered by one or more **Organizations**; involves **People** (speakers,
mentors, judges); classified by **Type**, **Topics**, **Skills**; located at a **Venue** /
**Location**; assembled from many **Source Records**; carries an **Application Process**, a
**Value**, and a **Lifecycle**. *Growth:* new types appear constantly — the model must treat
"type" as open-ended data, never a fixed list; opportunities may nest (a hackathon *within* a
conference) and syndicate across sources.

**Opportunity Type** — the *kind* of opportunity (conference, meetup, workshop, hackathon,
competition, fellowship, scholarship, grant, accelerator, incubator, hiring drive, internship,
research program, open-source program, government program, startup program, community
program…). *Relationships:* categorizes Opportunities; belongs to the managed **Taxonomy**.
*Growth:* an extensible, governed vocabulary with attributes per type (a scholarship has an
award; an internship has a duration) — not an enumeration frozen in code.

**Opportunity Series / Recurrence** — the persistent identity behind repeating opportunities
(an annual conference, a rolling internship, a quarterly cohort). *Relationships:* one Series
has many Opportunity instances; links year-over-year history. *Growth:* enables trend lines
("this conference has grown 3×"), early prediction ("next cohort likely opens in March"), and
"notify me when it returns."

**Lifecycle / Timeline** — the *state of time* for an opportunity: announced → open →
deadline approaching → closed → past → archived; plus rolling/always-open. *Relationships:*
drives visibility, notifications, and expiry. *Growth:* per-type lifecycles (a grant's review
window differs from a meetup's), timezone-aware, deadline reminders.

**Application Process** — *how* one takes part: application route, deadline(s), eligibility,
selectivity, required materials. *Relationships:* belongs to an Opportunity; consumed by the
user's **Application** tracking. *Growth:* structured eligibility (age, geography, field,
stage) enabling "only show what I qualify for"; multi-stage processes.

**Value / Compensation** — what the opportunity *costs or gives*: free/paid, ticket price, or
inbound award/stipend/prize/salary. *Relationships:* belongs to an Opportunity. *Growth:* must
model money flowing **both directions** (a scholarship pays the applicant; a conference charges
them) — a single "price" concept is structurally wrong for this product.

### B. Actors & the Graph — *the connective tissue (core domain)*

**Organization** — any entity that offers, hosts, funds or backs opportunities. Company,
university, community, nonprofit, government body, accelerator — these are **facets/roles** of
one Organization concept, not separate entities. *Relationships:* offers/hosts/sponsors
Opportunities; employs/affiliates **People**; related to other Organizations (parent, partner).
*Growth:* organization profiles become a product surface ("follow this company's
opportunities"); entity resolution ("Google" across 500 sources → one canonical org);
reputation/quality signal.

**Person** — a named human in the opportunity world: speaker, mentor, judge, organizer,
recruiter, founder, researcher. Again **roles**, not separate types. *Relationships:* affiliated
with Organizations; participates in Opportunities in a role; may *become* a **User**. *Growth:*
people-graph features ("events where this speaker appears"), mentor discovery, disambiguating
common names via entity resolution.

**Affiliation / Role** — the *relationship* connecting a Person or Organization to an
Opportunity or to each other, with a role and time (speaker-at, sponsor-of, employer-of,
organizer-of). *Relationships:* the edges of the graph. *Growth:* the role vocabulary itself
becomes governed taxonomy; weighted/verified relationships.

**Venue** — a physical or virtual place an opportunity happens. *Relationships:* belongs to a
**Location**; hosts Opportunities; may belong to an Organization. *Growth:* venue reputation,
capacity, accessibility; recurring-venue intelligence.

### C. Classification & Semantics — *the taxonomy (supporting, high-leverage)*

**Category** — a broad, human-facing grouping used for browsing. *Relationships:* organizes
Types/Topics. *Growth:* localized, audience-specific category schemes.

**Topic** — *what an opportunity is about* (AI, climate, fintech, biotech), hierarchical.
*Relationships:* tags Opportunities, People, Organizations; parent/child topics. *Growth:* a
governed ontology mapping thousands of messy source labels to canonical topics; multilingual.

**Skill** — a capability an opportunity builds or requires (Python, public speaking, grant
writing). *Relationships:* linked to Opportunities and to a User's **AI Profile**; the join
key for matching. *Growth:* a skills ontology with relationships (adjacent/prerequisite),
powering career-path recommendations.

**Tag** — uncontrolled, folksonomic labels (from sources or users). *Relationships:* annotate
Opportunities. *Growth:* a feeder into curated taxonomy (promote frequent tags to Topics).

**Location / Region** — canonical geography (city, state, country, region, "online",
"global"). *Relationships:* places Venues, Opportunities, Users, Organizations. *Growth:*
hierarchical geo, travel/visa-aware eligibility, regional trend analysis.

### D. Sourcing & Provenance — *ingestion (supporting) feeding core*

**Provider / Source** — an origin of opportunity data (an API, a site, a community, a partner
feed, and eventually direct submissions). *Relationships:* produces **Source Records** and
**Sync Jobs**; has **Health** and declared behavior. *Growth:* from tens to thousands; from
scraped to partner-submitted to user-submitted; per-source trust weighting.

**Source Record** — *what one provider said* about an opportunity (or org/person) at a point in
time — raw, un-merged, possibly wrong or duplicated. *Relationships:* normalized then resolved
into one **Canonical** Opportunity/Organization/Person via a **Match Group**; retains full
provenance. *Growth:* the audit trail behind every canonical fact; conflict resolution ("source
A says the deadline moved").

**Match Group / Entity Resolution** — the decision that several Source Records describe **the
same** real-world thing, collapsing them into one canonical entity. *Relationships:* links N
Source Records → 1 Canonical Opportunity/Org/Person. *Growth:* from rule/fuzzy matching to
learned models; the quality of this is a core competitive advantage.

**Provenance / Attribution** — the record of *which sources contributed which facts* to a
canonical entity, and when. *Relationships:* connects Canonical ↔ Source Records. *Growth:*
per-field provenance and confidence; "last confirmed by 3 sources 2 hours ago"; source credit.

**Sync Job / Ingestion Run** — one execution of pulling from a Provider. *Relationships:*
belongs to a Provider; updates **Health**; produces Source Records. *Growth:* incremental/delta
runs, checkpoints, backfills, replay.

**Provider Health** — the living operational state of a Provider (reliability, freshness,
volume, error patterns, trust). *Relationships:* summarizes Sync Jobs; feeds the **Scheduler**
and source trust weighting. *Growth:* anomaly detection (a source's volume drops to zero),
auto-throttling, auto-retirement of dead sources.

### E. Users & Personalization — *the demand side (mixed core/generic)*

**User / Account** — an identity that uses the platform to discover and act. *Relationships:*
owns an **AI Profile**, **Bookmarks**, **Applications**, **Saved Searches**, **Reminders**;
may correspond to a **Person** in the graph. *Growth:* organizations-as-users (B2B), teams,
roles/permissions; identity is a **generic** subdomain — buy/standardize, don't over-invest.

**AI Profile** — the platform's *semantic understanding of a user*: interests, skills, goals,
career stage, constraints (geo, availability, eligibility) — derived from explicit input **and**
observed behavior. *Relationships:* the counterpart to an Opportunity in **Matching**; built
from **Interactions** + **Preferences**. *Growth:* the personalization engine's heart —
embedding-based, evolving, explainable; a privacy-sensitive asset.

**Preference** — explicit user settings (topics, locations, types, cost, notification cadence,
"only what I'm eligible for"). *Relationships:* shapes the AI Profile and filtering. *Growth:*
fine-grained controls; preference learning.

**Interaction / Signal** — an observed user action (view, save, dismiss, apply, click-through,
dwell). *Relationships:* feeds AI Profile, Recommendation, quality signals, analytics. *Growth:*
the raw fuel of the flywheel; must be captured cleanly and privately from day one.

**Saved Search / Alert** — a standing query the user wants watched. *Relationships:* matched
against new/updated Opportunities → **Notifications**. *Growth:* semantic (not just keyword)
alerts; digest intelligence ("5 new matches this week").

**Bookmark / Collection** — user-curated saved opportunities, optionally grouped. *Growth:*
shareable/collaborative collections; team shortlists.

**Application** — the user's *tracked pursuit* of an opportunity (interested → applied →
in-progress → decision). *Relationships:* links User ↔ Opportunity; produces an **Outcome**.
*Growth:* the closing of the loop — deadline management, document reuse, status tracking; the
unique dataset of what actually happens.

**Outcome** — the *result* of an application (accepted, rejected, attended, awarded, hired).
*Relationships:* completes an Application. *Growth:* the rarest and most valuable data —
"which opportunities lead to which results for which profiles" — feeding matching and trust;
a genuine long-term moat.

**Reminder** — a time-anchored nudge (deadline approaching, event tomorrow). *Relationships:*
attached to Opportunities/Applications; delivered via **Notification**. *Growth:* smart timing.

**Notification** — a message delivered to a user across a channel (email, push, in-app, chat).
*Relationships:* generated by Alerts, Reminders, Recommendations. *Growth:* multi-channel,
frequency governance, engagement optimization; a **generic** capability.

### F. Intelligence & Delivery — *derived projections (core: matching)*

**Search Index / Search Document** — a fast, query-optimized **projection** of the catalog for
discovery. *Relationships:* derived from Canonical Opportunities; rebuildable. *Growth:*
semantic + keyword + faceted; typo-tolerant; multilingual.

**Embedding / Semantic Vector** — the mathematical meaning of an opportunity, a profile, a
topic. *Relationships:* enables similarity, semantic search, matching. *Growth:* the substrate
for recommendations and "more like this."

**Recommendation** — a ranked, personalized set of opportunities for a user *or* an
opportunity's ideal audience. *Relationships:* joins **AI Profile** ↔ **Opportunity** via
**Match Score**. *Growth:* from content-based to behavioral to predictive ("apply before this
closes; it fits you"); proactive rather than reactive — **core**.

**Match Score** — the graded fit between a person and an opportunity (or an opportunity and an
audience). *Relationships:* the output of Matching Intelligence. *Growth:* explainable,
multi-factor, outcome-calibrated.

**Quality / Trust Score** — how *good and real* an opportunity, organization or source is
(complete, corroborated, not spam, not dead). *Relationships:* attached to Opportunities /
Orgs / Sources; gates search and recommendations. *Growth:* essential at thousands of sources;
combats spam and decay; drives moderation.

**Insight / Trend** — aggregate intelligence over the catalog and behavior (what's rising,
where, for whom). *Relationships:* derived from everything. *Growth:* a product in its own
right (market reports, "state of hackathons"), and B2B/partner value.

### G. Governance & Platform — *keeping the system trustworthy (supporting)*

**Admin / Moderator + Roles & Permissions** — internal actors who curate taxonomy, resolve
entity-resolution conflicts, and moderate. *Growth:* delegated/partner moderation, tooling.

**Moderation Case / Report** — a flagged issue (spam, duplicate, wrong data, abuse).
*Relationships:* concerns any Canonical entity or Source. *Growth:* community reporting,
automated triage, trust workflows.

**Audit Log** — the immutable trail of who/what changed a canonical fact. *Growth:*
compliance, rollback, provenance for corrections.

**Taxonomy Version** — the governed, versioned state of Types/Categories/Topics/Skills.
*Relationships:* everything classified references it. *Growth:* controlled evolution without
breaking historical classification; the taxonomy is a *managed product*, not a constant.

**Tenant / Partner + API Consumer** — future B2B: organizations listing their own
opportunities, recruiters, integrators, and AI agents consuming the platform. *Growth:*
multi-tenancy, partner submission portals, programmatic/agent access as a first-class channel.

**Consent / Privacy Record** — the domain fact of what a user permitted (personalization,
tracking, data retention, erasure). *Relationships:* governs AI Profile, Interactions,
Notifications. *Growth:* regulatory compliance across geographies; a first-class concern
because the product is deeply personalized.

---

## 2. Service / Capability Architecture

Described as **business capabilities** (bounded contexts), each with a responsibility and a
**subdomain class** — *core* (the moat, invest heavily), *supporting* (necessary, build
adequately), *generic* (standardize/buy, don't over-invest). This classification is the
single most important CTO decision here: it directs where engineering compounds.

| Capability | Responsibility | Class |
|---|---|---|
| **Ingestion** | Acquire raw data from every Provider; normalize each Source Record into the canonical shape; validate. | Supporting |
| **Entity Resolution & Catalog** | Own the **system of record**: resolve Source Records into canonical Opportunities/Orgs/People, deduplicate, merge, maintain the **graph** and provenance. The heart of the platform. | **Core** |
| **Taxonomy** | Own and govern Types/Categories/Topics/Skills; map messy labels to canonical concepts; version the vocabulary. | Supporting (high-leverage) |
| **AI Enrichment** | Add derived meaning — embeddings, classification refinement, skill/topic extraction, quality scoring — asynchronously, best-effort, never blocking ingestion. | **Core** (matching substrate) |
| **Search** | Serve fast, faceted, semantic + keyword discovery from a rebuildable projection of the catalog. | Supporting |
| **Recommendation & Matching** | Match **AI Profiles** ↔ **Opportunities**; personalize, rank, and proactively surface. | **Core** |
| **Identity & Profile** | Accounts, authentication, and the **AI Profile** + preferences + consent. | Identity = generic; AI Profile = core |
| **Engagement** | Bookmarks, collections, application tracking, outcomes, reminders. | Supporting |
| **Notification** | Deliver alerts/reminders/recommendations across channels with frequency governance. | Generic |
| **Analytics & Insights** | Turn catalog + behavior into trends, dashboards, and partner-facing intelligence. | Supporting |
| **Scheduler / Orchestration** | Decide *when and what* to ingest/enrich/expire across thousands of providers using declared metadata + health; orchestrate background work. | Supporting |
| **Provider Management** | Register, configure, monitor and trust-weight sources; the provider lifecycle. | Supporting |
| **Trust & Safety / Moderation** | Detect and resolve spam, duplicates, decay, abuse; uphold quality. | Supporting (rising to core at scale) |
| **Admin & Governance** | Internal tooling, taxonomy curation, entity-resolution review, audit. | Supporting |
| **Access / Contracts** | The boundary through which consumers, partners and agents reach the platform. | Generic |

**The distillation:** *Entity Resolution & Catalog*, *Matching*, and *AI Enrichment* are where
the company wins. Ingestion, search, notification, identity are table stakes — make them solid
and boring. Never let generic work starve the core.

---

## 3. Data Flow

**A. The Write Path — from noise to canonical truth (the foundry).**
`Providers → Ingestion (fetch + normalize each Source Record) → cheap deterministic
classification → Entity Resolution (match Source Records to a canonical Opportunity/Org/Person,
deduplicate, merge, attach provenance) → the Catalog (system of record) emits a domain event
"opportunity created/updated".`
Everything downstream reacts to that event — the write path's job is done the moment the
canonical truth is committed.

**B. The Enrichment Path — meaning added after truth (asynchronous, best-effort).**
`Catalog change event → AI Enrichment (embeddings, refined classification, skill/topic
extraction, quality score) → writes derived facts back to the canonical entity → re-emits
"enriched".` Slow and external work never blocks A; failures retry without losing the base
record.

**C. The Projection Path — truth reshaped for delivery.**
`Catalog/enriched events → build/refresh projections: Search Index, recommendation candidates,
insight aggregates.` Projections are always rebuildable from the catalog, so they can be
regenerated, versioned, or replaced without risk.

**D. The Read / Discovery Path — the user meets the opportunity.**
`User query and/or AI Profile → Search + Matching (retrieve candidates, then personalize and
rank using profile, quality, freshness, graph signals) → results/recommendations → the user.`

**E. The Feedback Flywheel — the moat (closes the loop).**
`User Interactions, Bookmarks, Applications, Outcomes → signals → update AI Profile, tune
Matching and ranking, adjust Quality/Trust and source weighting, feed Analytics.`
Better matches → more engagement → richer signals → better matches. This loop is why the
product improves with use and why competitors can't catch up on data alone.

**F. The Attention Path — proactive delivery.**
`New/updated Opportunity events → matched against Saved Searches and AI Profiles → Reminders
and Notifications at intelligent times.` The platform reaches out; the user doesn't only pull.

The unifying principle: **the Catalog is the single source of truth; everything else is a
reaction to catalog events or a projection of catalog state.** This event-driven spine is what
lets capabilities evolve and extract independently.

---

## 4. API / Capability Boundaries

Logical boundaries and their contracts — *who talks to the platform and for what* — independent
of protocol.

- **Discovery Contract (consumer-facing):** search, browse, opportunity/organization/person
  detail, recommendations, engagement (save, track, remind). The main product surface.
- **Profile & Identity Contract:** authenticate; read/update preferences, AI Profile, consent.
  Privacy-governed.
- **Ingestion & Provider Contract (inbound):** how Providers and partners *feed* data —
  scraped, API-pulled, partner-pushed, and eventually user-submitted. Includes the provider
  registration/config/health surface.
- **Partner / B2B Contract:** organizations listing and managing their own opportunities;
  recruiters; sponsors — a curated, authenticated submission and analytics surface.
- **Intelligence / Agent Contract:** programmatic, structured access for external AI agents and
  integrators to query the opportunity graph and matching — a first-class channel in an
  agentic world, not an afterthought.
- **Governance / Admin Contract (internal):** taxonomy curation, entity-resolution review,
  moderation, audit.
- **Internal Domain-Event Contract:** the asynchronous, published events by which contexts
  react to one another ("opportunity updated", "user applied"). This is the most important
  boundary of all — the async backbone that keeps contexts decoupled. Contexts integrate
  through **published events and explicit contracts, never by reaching into each other's
  internal state.**

---

## 5. Monolith → Services — the evolution

**Start (and stay, longer than instinct suggests): a modular monolith with hard internal
boundaries and one async event backbone.** Bounded contexts are separated *logically* from day
one — separate models, separate ownership, communication only via events and contracts — but
deployed together. This gives context clarity without distributed-systems tax before it's
warranted.

**What remains together (the transactional core):** Catalog & Entity Resolution, Taxonomy,
Identity & Profile, Engagement. These share strong consistency needs and change together; keep
them co-located and transactional as long as possible.

**What extracts first, and why (independent lifecycle + scaling pressure + failure isolation):**

1. **Ingestion & Enrichment workers** — resource-spiky, failure-prone, embarrassingly parallel,
   and must never destabilize the read path. First to move to independent, horizontally-scaled
   workers off a durable queue.
2. **Search** — a read-heavy, independently-scalable projection with its own performance
   profile; extracts naturally behind its contract.
3. **Notification** — bursty, external-dependency-heavy, isolate its failures.
4. **Analytics / Insights** — heavy aggregate reads; separate so it never contends with
   ingestion or discovery (its own read replica of catalog state).
5. **Recommendation / Matching** — extracts when it needs its own compute (vector/model
   serving) and release cadence.

**The seams that make extraction cheap** (and which we must honor *today* even inside the
monolith): the catalog is the only source of truth; every other capability consumes catalog
**events** or a rebuildable **projection**; no shared internal models across contexts; contracts
are explicit. Get these seams right and extraction is a deployment decision, not a rewrite.

**What triggers each extraction is a *metric*, not a calendar** — write contention, tail
latency, independent release needs, blast-radius isolation. Extract on evidence; never
distribute for fashion.

---

## 6. Cross-cutting domain principles (the invariants)

1. **Canonical vs. Source everywhere.** Opportunities, Organizations, People all have the
   raw-many → resolved-one duality with full provenance. Never overwrite truth without keeping
   what each source said.
2. **The graph over the list.** Model and preserve relationships; they are the differentiated
   value.
3. **Taxonomy is managed data, not code.** Types/topics/skills evolve under governance and
   versioning.
4. **Time and lifecycle are first-class.** Opportunities live through states; recurrence has
   identity; deadlines drive attention.
5. **Trust and quality are first-class.** At thousands of sources, unscored data is unusable;
   quality gates discovery.
6. **Privacy and consent are first-class.** Deep personalization makes user-data governance a
   domain concern, not a legal afterthought.
7. **Everything reacts to catalog events; projections are rebuildable.** This is what keeps the
   system evolvable for a decade.
8. **Distill relentlessly.** Concentrate the best effort on the core (canonical graph +
   matching + enrichment); keep the generic generic.

---

## 7. What this means for today (alignment, not a build order)

This is the destination. We do **not** build most of it now. Its only job today is to ensure no
near-term decision forecloses it. The mapping from the current system:

| Today | Matures into | The invariant to honor now |
|---|---|---|
| `Event` | one **Opportunity Type** among many | model the record so "type" is open data and dates/value/eligibility can generalize — never assume event-shape |
| Provider | **Provider / Source** | keep raw **Source Records** distinct from the canonical record, with provenance, from day one |
| Composite dedup | **Entity Resolution** | treat dedup as canonical-assembly with provenance, not as throwing rows away |
| `classify` | **Classification + Taxonomy** | classification reads managed taxonomy data, not a hardcoded enum |
| Ranking | **Matching Intelligence** | keep ranking a separable read-side concern that can later consume an **AI Profile** |
| (none yet) | **AI Profile / Recommendation** | capture user **Interactions** cleanly and privately as soon as there are users |
| In-memory/DB store | **Catalog = system of record** | one source of truth; search/recs are rebuildable **projections**; capabilities talk via events |

**The single alignment test for every future decision:** *does it strengthen, or at least not
weaken, the Canonical Opportunity Graph and the Matching Intelligence — and does it keep the
core/supporting/generic boundaries honest?* If yes, it fits the five-year product. If it
quietly hardcodes event-shape, discards provenance, freezes taxonomy into code, or blends the
core into generic plumbing, it is debt against the vision regardless of how well it serves
today.

---

*Approve this domain architecture (with any changes), and we map the current implementation
onto it — starting by making Repository v2 and the ingestion engine speak this domain's
language (Source Record, Canonical Opportunity, Provenance, Provider Health, Projection), so
every line we write from here compounds toward the final product.*
