# Recommendation Engine (Phase 5B)

Deterministic, explainable recommendations — no LLM, no embeddings. Built on user profiles
(5B) + event understanding (5A) + entity affinity (3F) + freshness/trending (4D). Code:
`backend/app/users/engine.py` + `recommend.py`.

## Pipeline

```
User profile  (learned weighted features)
   ▼  Candidates      = upcoming events not already saved/attended
   ▼  Interest        = Σ profile.weight(feature) over the event's features, normalized 0..1
   ▼  Freshness       = Phase-4D freshness_score(event, now)
   ▼  Trending        = Phase-4D trending score(event, now)
   ▼  Similarity      = max enrichment-feature overlap with any saved/attended event
   ▼  Score           = 0.6·interest + 0.15·freshness + 0.15·trending + 0.10·similarity
   ▼  Explain         = deterministic reasons from the strongest matched features
   ▼  Rank            = score desc, ties by key → top-N
```

## Scoring

| Signal | Weight | Source |
|---|---|---|
| **interest** | 0.60 | dot product of the profile's preference weights with the event's features (topics, tech, city, category, audience, difficulty, **community**, **organizer**, format, budget), min-max normalized across the candidate set |
| **freshness** | 0.15 | `freshness_score` (discovery recency + start proximity) |
| **trending** | 0.15 | Trending Engine score (source quality + freshness + popularity + update frequency) |
| **similarity** | 0.10 | max Jaccard of enrichment features with the user's saved/attended events |

Interest naturally captures **organizer affinity, community affinity, and city affinity**
because those are features the profile accumulates. Already-engaged and past events are
excluded. Deterministic: identical inputs → identical ranking (ties break by event key).

## Explanation generation

Every recommendation explains *why*. Reasons are the user's **strongest matched features**,
ordered so the most compelling ones surface first (community/organizer → topic → tech → city
→ category — not by raw weight, so "you follow GDG" beats "you like meetup events" when
tied), plus a similarity reason when the event resembles something the user engaged with. All
template-based and deterministic.

**Live output** (a user who attended AI events and follows GDG):

```
[0.896] Google Vertex AI: An Introduction to AutoML
   - Recommended because you follow Google Developer Groups.
   - Recommended because you follow Google.
   - Recommended because it's similar to events you've engaged with.
[0.873] Build With AI - Buildathon
   - Recommended because you follow Google Developer Groups.
   - Recommended because you frequently attend Artificial Intelligence events.
   - Recommended because it's similar to events you've engaged with.
```

The "frequently attend" phrasing is used once the user has attendance history; otherwise
"you're interested in …".

## Determinism

No LLM, no embeddings, no randomness. Interest normalization, freshness, trending, and
similarity are all pure functions of the catalog + profile + `now`. `test_users.py` asserts
ranking (engaged excluded, interest-matched event first), explanation content, and analytics.

## Future evolution

The engine is the natural home for the Phase-4A **Personalization Layer**: when embeddings
arrive (5A's `Embedder` interface), a semantic interest term joins the score without changing
the pipeline shape; the `AICareerAssistant` interface (5B) consumes the profile +
recommendations for conversational guidance. All additive, behind existing interfaces.

## Reproduce

```
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m5b_recommend
```
