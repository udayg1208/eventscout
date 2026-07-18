# Provider Scorecard

Multi-provider event coverage for the India event discovery engine. Updated after
each provider. Upcoming-event counts are a live snapshot (they change over time).
Live numbers are auto-tracked in `PROVIDER_ANALYTICS.md`; the ingestion-measured
totals are in `COVERAGE_REPORT.md`.

| Provider | Status | Source type | Categories | India coverage | Upcoming (snapshot) | API stability | Maint. risk | Notes |
|----------|--------|-------------|------------|----------------|---------------------|---------------|-------------|-------|
| Confs.tech | ✅ Complete | JSON (GitHub dataset) | Conference | Medium | 4 | High | Low | Keyless static dataset; no price/desc |
| Devfolio | ✅ Complete | JSON (search API) | Hackathon | High | 16 | Medium | Medium | Unofficial API; `is_free=True` |
| GDG | ✅ Complete | JSON (Bevy) | Meetup | Medium | 15 | Medium | Low | Shared `bevy.py`; minimal fields |
| CNCF | ✅ Complete | JSON (Bevy) | Meetup | Low | 1 | Medium | Low | Shared `bevy.py`; KCDs; low volume |
| FOSS United | ✅ Complete | JSON (Frappe REST) | Meetup/Workshop/Conf/Webinar | High | 14 | High | Low | India-native; real `event_type` + free flag |
| Hasgeek | ✅ Complete | HTML (JSON-LD) | Conference/Meetup | High | 6 | Medium | Medium | India-native; per-project schema.org JSON-LD |
| Lu.ma | ✅ Complete | HTML (`__NEXT_DATA__`) | Meetup/Workshop/Hackathon | High | 40 | Medium | Medium | India city pages; highest-volume source |
| **Atlassian ACE** | ✅ **New (3G)** | JSON (Bevy) | Meetup | Medium | 17 | Medium | Low | `ace.atlassian.com`; Jira/Confluence user groups; shared `bevy.py` |
| **Salesforce Trailblazer** | ✅ **New (3G)** | JSON (Bevy) | Meetup | High | 27 | Medium | Low | `trailblazercommunitygroups.com`; dev/admin groups; shared `bevy.py` |
| **Snowflake User Groups** | ✅ **New (3G)** | JSON (Bevy) | Meetup | Low | 6 | Medium | Low | `usergroups.snowflake.com`; data community; shared `bevy.py` |
| **Devpost** | ✅ **New (3G)** | JSON (hackathon API) | Hackathon | Medium | 6 | Medium | Medium | `search=india`; free-text date/location parsed; `is_free=True` |

## Investigated & skipped (Phase 3G — evidence in `spikes/probe_providers*.py`)

| Candidate | Decision | Why |
|-----------|----------|-----|
| Meetup.com | ⏭️ Skip | API is now **Pro-only (paid)**; site is a Cloudflare-guarded SPA — no ₹0 discovery |
| Eventbrite | ⏭️ Skip | Public search API **removed (2019)**; OAuth-gated; no keyless India discovery |
| allevents.in | ⏸️ Defer | JSON-LD present but the "technology" feed **mixes entertainment/expos** ("The Messi Experience", green-energy expo) — poor signal without a strict classifier |
| 10times.com | ⏸️ Defer | JSON-LD present but **expo/trade-show heavy**; quality + dedup risk |
| Commudle | ⏸️ Defer | India-native + high value, but public API returns **503**; site is an Angular shell — needs deeper API investigation |
| Unstop | ⏸️ Defer | India-native competitions, but data sits behind an **undocumented SPA API** (shell only) |
| AWS (community.aws) | ⏭️ Skip | Bevy-style path returns **403** (blocked) |
| MongoDB / Postman | ⏭️ Skip | **404** — not Bevy-hosted at the probed hosts |
| HashiCorp / Twilio / UiPath | ⏭️ Skip | **DNS / SSL failure** — no reachable keyless API |
| Microsoft Reactor | ⏭️ Skip | Bot-protected (Akamai); no public API (unchanged from M9) |
| Sessionize / Eventyay | ⏭️ Skip | No discovery/list API / ~0 upcoming India (unchanged from M9) |

## ICS family (config-driven, hierarchical — the redesign)

`ICSProvider` (generic iCalendar parser) + `ics_sources.py` (curated catalog): **each feed
is its own provider** with its own id/city/category/health/refresh, generated from data by
`build_registry()`. Adding a source = adding a line (no code, no architecture change) — the
"hundreds of small providers" model. Seeded with 9 probe-confirmed India tech Meetup group
`.ics` feeds (bangpypers, pydelhi, chennaipy, awsugblr, flutter-bangalore, golang-blr,
devops-blr, k8s-blr, aws-hyderabad). Grows over time — see `FEASIBILITY_REPORT.md`.

**Composite snapshot (ingestion-measured, 20 live providers → 164 deduped active events):**
luma 40 · salesforce 27 · atlassian 17 · devfolio 16 · gdg 15 · fossunited 14 ·
meetup-bangpypers 10 · hasgeek 6 · devpost 6 · snowflake 6 · confs.tech 4 · (ICS k8s/aws 1 each) · cncf 1.
Categories: meetup 98 · hackathon 25 · ai 18 · conference 12 · workshop 7 · startup 2 · webinar 2.
Cities: 41 (Bangalore 46, Delhi 18, Mumbai 11, Jaipur 6, Hyderabad 5, Pune 5, …).
Duplicate rate 2.4%. Provider health: **20/20 healthy** (6 ICS groups healthy with 0 current events).

**Reusable families:** `bevy.py` backs **5** providers (GDG, CNCF, Atlassian, Salesforce,
Snowflake); `ICSProvider` backs **all curated .ics feeds** (unbounded via config). A new
API provider is a `providers/*.py` file + a `build_registry()` entry + a test; a new ICS
source is one line in `ics_sources.py`. No frozen interface is touched. **Discovery is the
limiter, not architecture** — see `FEASIBILITY_REPORT.md`.
