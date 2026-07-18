# User Intelligence Platform (Phase 5B)

Understands **users** as well as EventScout understands events: evolving preference profiles
learned from interactions, saved events, attendance history, deterministic recommendations
with explanations, and per-user analytics. Additive; nothing frozen is modified.

## Principle: symmetric features, separate storage, deterministic

Users and events share one **feature vocabulary** — namespaced strings like `topic:LLMs`,
`community:Google Developer Groups`, `city:Bangalore`, `format:offline`, `budget:free`. An
event's features come from the frozen catalog + Phase-5A enrichment + Phase-3F entity graph;
a user's profile is the **running weighted sum** of the features of everything they interact
with. Recommendation is then a match between the two vectors. All user data lives in separate
user stores (only event *keys* are referenced); the Event model is never touched. Every
computation is a pure function of the interactions + `now` — reproducible, no LLM, no network.

## Modules (`app/users/`)

| Module | Role |
|---|---|
| `models.py` | `Interaction`, `UserProfile` (namespaced weights + accessors), `AttendanceRecord`, `Recommendation` |
| `interactions.py` | interaction **weights** + `InteractionLog` |
| `features.py` | event/query → feature set (reuses enrichment + entity graph) |
| `profile.py` | **Preference Learning** (`apply_features`) + `UserProfileStore` |
| `saved.py` | **Saved Events Engine** — save / unsave / collections / favorites |
| `attendance.py` | **Attendance History** — registered / attended / missed / cancelled (deterministic lifecycle) |
| `recommend.py` | scoring weights + **explanation generation** |
| `analytics.py` | **User Analytics** |
| `interfaces.py` | future integrations (calendar / Gmail / LinkedIn / WhatsApp / push / AI assistant) — **interfaces only** |
| `engine.py` | `UserIntelligenceEngine` — the facade |

## User profile evolution (preference learning)

Each interaction folds the interacted event's (or search query's) features into the profile,
scaled by the interaction's **strength**:

```
attend +5.0 · register/save +3.0 · click +1.5 · view/search +1.0 · ignore −1.0 · unsave −2.0
```

No manual retraining — the profile *is* the accumulated weighted sum, updated automatically
inside `record_interaction`. Preferred cities/topics/technologies/communities/…​ are the
top-weighted features per namespace; `budget_preference` and `preferred_format` are derived.

**Live** (a user who attended 2 AI events, saved a GDG event, searched "kubernetes and cloud"):
`favorite_topics = [AI 10.0, LLMs 5.0, Cloud 4.0, Kubernetes 1.0]`,
`favorite_communities = [Google Developer Groups 13.0]`, `preferred_format = offline`.

## Saved events & attendance

- **Saved:** save / unsave / named **collections** / **favorites**, per user, by event key.
- **Attendance:** explicit statuses (register / attend / cancel) plus a **deterministic
  derived status** — a still-"registered" event that has ended becomes `MISSED` (from the
  event's dates + `now`). Feeds both recommendations (exclude engaged) and analytics.

## User analytics

Saved / attended counts, favorite topics / technologies / communities, preferred cities /
format / budget, interaction counts by type, and **recommendation acceptance** (shown recs
that were subsequently saved or attended). All derived from the stores + interaction log.

## Future integrations (interfaces only — nothing implemented)

`interfaces.py`: `CalendarSync`, `GmailIntegration`, `LinkedInIntegration`, `WhatsAppNotifier`,
`PushNotifier`, `AICareerAssistant`. A future implementation reads the profile /
recommendations and dispatches — with no change to the engine or anything frozen. (Gmail/
LinkedIn interest inference would require explicit user consent.)

See [RECOMMENDATION_ENGINE.md](RECOMMENDATION_ENGINE.md) for the recommendation pipeline,
scoring, and explanation generation.

## Storage & scale

In-memory stores today (profiles / saved / attendance / interaction log / shown-recs), each
storage-independent and persistable later. Recommendation scores the upcoming candidate set
per request (O(candidates)); at scale it would pre-filter by a few top preference features
(via the Search Infrastructure) before scoring — a retrieval-then-rank shape identical to the
event search path.
