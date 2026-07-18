# Community Coverage — Phase 11A (Tier 2 & Tier 3)

Coverage of professional communities and recurring conferences, measured from `catalog.db`.

## Tier 2 — professional communities (measured)

| Community family | In catalog | Source | Status |
|---|---:|---|---|
| Google Developer Groups (GDG) | 20 | gdg (Bevy API) | ✅ covered |
| Salesforce Trailblazer | 30 | salesforce (Bevy) | ✅ covered |
| Atlassian Community | 17 | atlassian (Bevy) | ✅ covered |
| FOSS United | 16 | fossunited | ✅ covered |
| Snowflake User Groups | 6 | snowflake (Bevy) | ✅ covered |
| CNCF / Cloud Native | 1 | cncf (Bevy) | ✅ covered (thin — few upcoming) |
| Python (BangPypers, ChennaiPy, PythonPune, PyData) | ~15 | Meetup ICS | ✅ covered |
| AWS User Groups (Blr, Hyd, Pune) | ~3 | Meetup ICS | ✅ covered (low volume) |
| Docker / Kubernetes / React / JS / Go / Flutter (Bangalore) | ~7 | Meetup ICS | ✅ covered (1–2 each) |
| Women Who Code / WordPress / Deep Learning (Bangalore) | ~3 | Meetup ICS | ✅ covered |

Named Tier-2 families **probed but not machine-readable right now**: Azure UGs, HashiCorp, Elastic,
Docker/K8s outside Bangalore, Mozilla, Linux UGs, Angular/Vue, TensorFlow, Women Techmakers. Their
Bevy/Meetup endpoints returned 403 / not-Bevy / deprecated-iCal (see gap analysis) or had **0 upcoming
events**. They index automatically when they next publish to a reachable feed.

## Tier 3 — recurring conferences (measured)

| Series family | In catalog | Source |
|---|---:|---|
| Unstop conferences (India tech conferences) | 29 (conference) + 27 (ai) | unstop |
| Hasgeek (Rootconf, JSFoo, The Fifth Elephant, …) | 9 | hasgeek |
| confs.tech India conferences | 4 | confs.tech |
| DevFest / GDG conferences | (within GDG 20) | gdg |

DevFest, PyCon, Cloud Community Day, Kubernetes Community Day surface through their host platforms
(GDG/Bevy/Hasgeek/Unstop) rather than as separate providers — the catalog carries them when they are
upcoming and published.

## Tier 4 — hackathon ecosystems (measured, the growth engine)

| Platform | In catalog | Source | Status |
|---|---:|---|---|
| **Unstop** | 251 (hackathon) | unstop | ✅ NEW — dominant |
| Devfolio | 17 | devfolio | ✅ covered |
| Devpost | 8 | devpost | ✅ covered |
| HackerEarth | 0 | probed | only 3 events available; negligible |
| MLH | 0 | probed | not machine-parseable / non-India |
| Hack2Skill, HackClub | 0 | — | no reachable structured feed |

## Tier 5 / Tier 6 — calendars & public pages (measured)

- **ICS/RSS calendars:** 12 Meetup ICS feeds live; the long tail is exhausted (Meetup deprecated public
  iCal — 3 of 51 probed groups reachable).
- **GitHub orgs / Notion / Discord / Telegram / LinkedIn / blogs / forums:** publish **no
  machine-readable event feeds**; auth/JS-gated. Contributed **0** and are unreachable by a no-browser
  system by design.

## Summary

Tiers 2–4 are covered to the extent they are machine-readable today; **Tier 4 (hackathons, via Unstop)
was the campaign's engine**. Tiers 5–6 and the JS/auth-gated parts of Tier 2 are the measured frontier
that a future rendering tier — not this phase — would unlock.
