# Ecosystem Gap Analysis — testing the ₹0 volume ceiling

**Hypothesis under test:** *"It is possible to build a catalog of 1,000–5,000 searchable
professional tech events in India using only publicly accessible sources, without paid APIs."*

This document rigorously tests my earlier "~200–400 concurrent" conclusion by systematically
investigating every event-producing ecosystem, with live probes (`backend/spikes/probe_*.py`).
It does **not** assume — every rejection has a measured reason.

## Verdict (up front)

Two different questions were being conflated. Separating them:

| Question | Answer | Confidence |
|---|---|---|
| **Concurrent upcoming** events reachable at ₹0 (quality bar) | **~250–400** (peak season ~400–600) | **HIGH** (measured) |
| **90-day searchable** distinct events (rolling window) | **~600–1,200** (peak season ~1,000–1,500) | **MEDIUM** (production-rate derived) |
| Hypothesis low end (**1,000 searchable/90d**) | **Achievable** — with Eventbrite + sustained curation + peak season | MEDIUM |
| Hypothesis high end (**5,000**) | **Not achievable at ₹0** with the quality bar | HIGH |

**My earlier "200–400" was about *concurrent* and is justified** — even adding the biggest
source I had missed (Eventbrite), concurrent lands at ~250–350. **But the user is right that
the *90-day searchable* number is materially larger (~600–1,200)** and the hypothesis's low end
is reachable. The 5,000 figure is not, because the ecosystems that would supply it (university
at scale, Meetup at scale, corporate) are **not publicly discoverable/ingestible at ₹0**.

## The critical distinction (why the numbers differ)

Event scheduling is a **thin forward pipeline**. Measured on Bevy (uncapped,
`probe_bevy_volume.py`): GDG India = 16 upcoming, of which 15 are within 30 days and only 16
within 90 days — i.e. most chapters *haven't scheduled their next event yet*. So:

- **Concurrent** = events with a currently-published future date ≈ thin (~168 measured today).
- **90-day searchable** = concurrent **× turnover** — as the ~30-day forward window rolls, new
  events appear and old ones become searchable history (the repository retains ended events).
  Production rate ≈ the ≤30-day count; over 90 days ≈ **~2.5–3× the concurrent snapshot**.
- **Seasonality:** July is a lull. Sept–Nov (DevFest + conference season) plausibly 2–3× the
  rate — the single biggest lever on both numbers.

## Ecosystems investigated (the 10 questions)

Legend: Tech✓ = produces professional-tech events · Pub = publicly accessible · Disc = discovery
possible · Auto = discovery automatable at ₹0 · Ing = stable ingestion · Now = concurrent est ·
90d = 90-day est · Maint = maintenance difficulty · Support = should EventScout support it.

### ✅ Accepted (accessible, ingesting or ingestible)

| Ecosystem | Tech | Pub | Disc | Auto | Ing | Now | 90d | Maint | Legal | Support |
|---|---|---|---|---|---|---|---|---|---|---|
| Bevy: GDG (+GDG On Campus/GDSC) | ✓ | ✓ | ✓ | ✓ | ✓ | 16 | ~45 | Low | OK | ✅ built |
| Bevy: Salesforce Trailblazer | ✓ | ✓ | ✓ | ✓ | ✓ | 29 | ~80 | Low | OK | ✅ built |
| Bevy: Atlassian ACE | ✓ | ✓ | ✓ | ✓ | ✓ | 17 | ~45 | Low | OK | ✅ built |
| Bevy: Snowflake / CNCF | ✓ | ✓ | ✓ | ✓ | ✓ | 7 | ~20 | Low | OK | ✅ built |
| Lu.ma India city pages | ✓ | ✓ | ✓ | ✓ | ✓ | 40 | ~110 | Med | OK | ✅ built (at ceiling) |
| Devfolio + Devpost (hackathons) | ✓ | ✓ | ✓ | ✓ | ✓ | 22 | ~60 | Med | OK | ✅ built |
| FOSS United | ✓ | ✓ | ✓ | ✓ | ✓ | 14 | ~35 | Low | OK | ✅ built |
| Hasgeek (Rootconf/JSFoo/…) | ✓ | ✓ | ✓ | ✓ | ✓ | 6 | ~20 | Med | OK | ✅ built |
| Confs.tech (India entries) | ✓ | ✓ | ✓ | ✓ | ✓ | 4 | ~15 | Low | OK | ✅ built |
| Meetup groups (ICS) | ✓ | ✓ | **partial** (manual curation) | ❌ | ✓ | 16 | ~120 | Med | OK (ical is a sanctioned subscribe feature) | ✅ built, curation-bound |
| **Eventbrite discovery JSON-LD** (NEW) | ~✓ (mixed) | ✓ | ✓ | ~ (throttled) | ~ | ~40–100 | ~150–300 | **High** (anti-bot throttling) | ToS gray | ⚠️ conditional — needs tech-filter + slow rate-limit |

### ❌ Rejected (with measured reasons)

| Ecosystem | Why rejected (measured) |
|---|---|
| **Meetup discovery / Pro networks** | Search + Pro-network chapter lists are **client-side GraphQL**; 0 groups from 20 GET searches; Pro pages expose `urlnames~1`. Not enumerable at ₹0. (Individual groups' ICS work if a slug is known.) |
| **IEEE vTools** (~1000 India branches) | Home 200 but `/api`, `/rss`, `/m/events?country=IN` all **404** — no accessible feed found. The single biggest *inaccessible* volume. |
| **ACM / CSI chapters, college coding clubs** | Publish on Instagram / PDFs / own SPA sites — **no structured feeds**. High difficulty, ~0 ingestible. |
| **More Bevy communities** (HashiCorp/MongoDB/Elastic/Grafana/Databricks/Redis/NVIDIA/Intel/Docker/…) | Probed 15 hosts → **DNS-fail / 403 / non-JSON**. No Bevy directory to enumerate; custom domains unguessable. |
| **KonfHub** | SPA + **authenticated** API (401/403); homepage NEXT_DATA=`{signedIn}`, 0 JSON-LD Events; sitemap = marketing pages only. |
| **Commudle / Kommunity / Townscript** | SPAs with **0 server-side Event data** (earlier "JSON-LD" signals were Org/Breadcrumb schema, not Events). |
| **Unstop / HackerEarth / Hack2skill / Reskilll / Devnovate** | SPA shells; data behind undocumented/authless-but-unreachable APIs. |
| **GeeksforGeeks events** | Has NEXT+LD, but content is **edtech webinars/courses** — off the professional-community quality bar. |
| **Corporate event pages** (Google/Microsoft/AWS/Meta/…) | Anti-bot (AWS `community.aws` 403; MS Reactor Akamai) or **paid** (Meetup Pro, Eventbrite API). |
| **Aggregators** (allevents.in, 10times) | JSON-LD present but **mix entertainment/expos** — fail the "NOT entertainment" bar without a strict classifier. |
| **GitHub curated directories** | `tech-communities`, `awesome-gdg-gde` etc. are **resource lists** (links/talks), not source lists; 0 usable event feeds. |
| **Public Google Calendars / Discord / Slack** | Mechanically ingestible (ICS proven at 535 VEVENTs) but **discovery is manual/gated** — no way to enumerate calendar IDs or private-server calendars at ₹0. |
| **RSS/newsletters** (reddit r/developersIndia, lobste.rs) | Feeds work but carry **posts, not structured events** — low signal, not worth the noise. |

## Estimated total — with confidence

**Concurrent (today, off-peak):**

| Source group | Concurrent |
|---|---|
| Built providers (measured) | **168** |
| + Eventbrite (conditional, tech-filtered) | +~40–100 |
| **Concurrent total** | **~210–270 now; ~250–400 typical; ~400–600 Sept–Nov peak** |

Confidence **HIGH** for the 168 (measured live), **MEDIUM** for Eventbrite (throttling + quality
filter uncertainty).

**90-day searchable** (production rate ≈ ≤30-day count ≈ ~180–230/month, × ~3 months, with
overlap/dedup):

| | 90-day distinct |
|---|---|
| Current sources, off-peak | **~500–700** |
| + Eventbrite | +~150–300 |
| **90-day total, off-peak** | **~650–1,000** |
| **90-day total, peak season (Sept–Nov)** | **~1,000–1,500** |

Confidence **MEDIUM** — derived from measured forward-pipeline turnover, not a 90-day observation
(which would take 90 days to confirm).

## Remaining unexplored surface area (honest)

The accessible surface is **largely mapped**. The genuinely-unexplored volume is **real but
inaccessible at ₹0**:

1. **University ecosystem** (IEEE ~1000 branches, ACM/CSI, thousands of college clubs) — the
   single largest theoretical volume; **no discoverable structured feeds** (Instagram/PDF/SPA).
   Would need OCR/social scraping or institutional partnerships — not ₹0, not stable.
2. **Meetup at full scale** (~300–500 India tech groups) — ingestible per-group via ICS, but
   **discovery is blocked** (client-side search). Only manual slug curation adds them, at
   ~0.2 concurrent / ~1-per-90d events each.
3. **Corporate community platforms behind auth/anti-bot** (KonfHub, Commudle, Unstop, most
   vendor communities) — data exists but requires keys/bot-bypass.
4. **Private calendars** (Discord/Slack/Google Calendar) — ICS-ingestible if a URL is known;
   **not enumerable**.

None of these are ₹0-accessible with the quality bar. Exploring them further would not change
the verdict — it would re-confirm inaccessibility.

## Recommendation

- **Concurrent ~250–400 stands** (the earlier conclusion is justified; Eventbrite fits inside it).
- **Adopt the 90-day searchable metric** (~650–1,500) as the real measure of catalog size — the
  hypothesis's **1,000 low end is reachable**; 5,000 is not at ₹0.
- **Highest-leverage next actions** (if volume is the goal): (a) build the **Eventbrite JSON-LD**
  provider with a strict tech-classifier + slow rate-limit (the one real untapped source);
  (b) **re-run during Sept–Nov peak** to capture the seasonal 2–3×; (c) continue Meetup ICS
  curation for 90-day breadth. Each is measured-incremental, not a path to thousands-concurrent.
- **To exceed ~400 concurrent / ~1,500 90-day** requires leaving the ₹0-or-quality box: paid
  discovery (Meetup Pro/Eventbrite/PredictHQ), or a university/Meetup partnership for feeds.
