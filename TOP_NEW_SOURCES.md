# Top New Sources — Phase 11A

Sources ranked by contribution to the catalog after the expansion campaign. Measured from
`catalog.db` (`provider` column, `status='active'`).

## Providers by event contribution (505 total)

| Rank | Source | Events | Share | Added this phase? | Type |
|---:|---|---:|---:|:--:|---|
| 1 | **Unstop** | **295** | 58.4% | ✅ NEW | Hackathons/workshops/conferences/tech-competitions (JSON API) |
| 2 | Lu.ma | 61 | 12.1% | — | City meetups (embedded JSON) |
| 3 | Salesforce Trailblazer | 30 | 5.9% | — | Bevy community |
| 4 | Google Developer Groups | 20 | 4.0% | — | Bevy community |
| 5 | Devfolio | 17 | 3.4% | — | Hackathons |
| 6 | Atlassian Community | 17 | 3.4% | — | Bevy community |
| 7 | FOSS United | 16 | 3.2% | — | FOSS meetups |
| 8 | Meetup: bangpypers | 10 | 2.0% | — | ICS feed |
| 9 | Hasgeek | 9 | 1.8% | — | Conferences |
| 10 | Devpost | 8 | 1.6% | — | Hackathons |
| 11 | Snowflake User Groups | 6 | 1.2% | — | Bevy community |
| 12 | confs.tech | 4 | 0.8% | — | Conference dataset |
| 13–24 | 12× Meetup ICS feeds | 12 | 2.4% | 3 ✅ NEW | Community calendars |
| 25 | CNCF | 1 | 0.2% | — | Bevy community |

## The single decisive lever

**Unstop alone contributed 295 of the 505 events (58%)** and drove the catalog from 206 → 501. It was
the only new high-volume source found among all probed candidates because it exposes a clean, keyless,
paginated JSON API (`unstop.com/api/public/opportunity/search-result`) — most other India event
platforms are JS-rendered or bot-protected.

New sources added this phase:
- `app/providers/unstop.py` — **Unstop** provider (4 opportunity types, honest normalization).
- `app/providers/ics_sources.py` — **AWS User Group Pune**, **PyData Bangalore**, **PyData Chennai**
  (probe-confirmed reachable Meetup ICS feeds).

## Sources probed but NOT added (measured, with reason)

| Candidate | Why not added |
|---|---|
| 30 Bevy community hosts (HashiCorp, MongoDB, Twilio, Elastic, …) | 403 / not-Bevy / unresolvable — only the already-wired CNCF answered |
| HackerEarth | API works but only 3 events |
| MLH | events page not machine-parseable; predominantly non-India |
| 48 of 51 Meetup ICS candidates | 404/403 — Meetup deprecated public iCal |
| 10times, Townscript, Insider | JavaScript-rendered / down — no server-side event data |
| Commudle | no reachable public JSON API at probed paths |
| allevents.in | aggregator (JSON-LD) — cross-lists events already sourced directly; rejected to avoid duplicate inflation |

See [CATALOG_EXPANSION_REPORT.md](CATALOG_EXPANSION_REPORT.md) for the full measured gap analysis.
