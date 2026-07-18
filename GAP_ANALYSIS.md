# Gap Analysis — India Event Coverage

**Trigger:** the deduped India event count reached **107** (target band 100–150) with
5 of 7 categories represented — the point at which the strategy says to stop adding
providers and analyze gaps. Snapshot from live provider runs (see `PROVIDER_ANALYTICS.md`).

## Where we are
- **7 working providers**, 4 skipped/deferred, **107 deduped upcoming India events**, **0% duplicate rate**.
- **By provider:** luma 44 · devfolio 16 · gdg 14 · fossunited 14 · confs.tech 11 · hasgeek 7 · cncf 1.
- **By category:** meetup 65 · conference 19 · hackathon 19 · webinar 2 · workshop 2 · **ai 0 · startup 0**.
- **By city:** Bangalore 35 · Delhi 19 · Mumbai 11 · unknown 11 · Online 5 · Pune 2 · Chennai 2 · Hyderabad 1 · (long tail of tier‑2 cities, 1 each).

## 1. Missing / weak categories
- **`ai` and `startup` are unused (0 each)** despite many AI and startup *meetups* existing — they are currently labelled `meetup` because no source exposes those as a type. **This is a classification gap, not a coverage gap** — more providers won't fix it.
- **`webinar` (2) and `workshop` (2) are thin.** Real workshops exist (FOSS United, Lu.ma) but many are titled generically and fall back to `meetup`/`conference`.
- **Meetup-heavy (61%).** Healthy for discovery, but the mix is skewed.

## 2. Geographic gaps
- **Metro concentration:** Bangalore + Delhi + Mumbai = **65 / 107 (61%)**.
- **Hyderabad (1), Pune (2), Chennai (2), Kolkata (1)** are under-represented relative to their real tech-event volume — a provider/city-page coverage gap (e.g., Lu.ma Hyderabad/Pune pages had a different embedded shape and contributed little).
- **11 events have no detectable city** (offline but city not in the source) — mostly Devfolio/Hasgeek records without a clean locality.

## 3. Weak provider areas
- **CNCF: 1 event.** Very low volume (correct, but marginal). Keep — it's near-free (shares `bevy.py`) and adds cloud-native events when they exist.
- **Confs.tech: 4 upcoming / 11 fetched.** It does **not** filter to upcoming, so 7 past events are surfaced (ranking buries them, but they shouldn't be returned). **Data-quality bug.**
- **GDG latency ~9 s** (descending 500-event pages) — the slowest provider; acceptable behind the 1 h cache but the outlier.

## 4. Duplicate issues
- **0% duplicates** and **0 same-title-across-providers** — genuinely low because the sources barely overlap (hackathons vs conferences vs meetups vs city-meetups).
- **Risk (not yet realized):** the same event cross-posted to Lu.ma *and* GDG would only be caught if titles match exactly; the `(normalized-title, start_date)` key is not resilient to title variations. Worth hardening *before* overlap grows (the ranking/dedup upgrade already outlined).

## 5. Ranking issues
- Past Confs.tech events are returned and merely down-ranked — fixing the upcoming filter (item 3) removes them entirely.
- Ranking is the M6 heuristic (relevance/date/completeness). It has **no location-match or popularity signal** yet, and city-less events (11) can't benefit from a location boost. The richer scheme (relevance 40 / date 20 / location 15 / source 10 / popularity 10 / completeness 5) is not yet implemented.

## 6. Opportunities for future providers (deferred, not skipped)
| Candidate | Likely value | Notes |
|---|---|---|
| **PyData** | Medium (conferences/AI) | Would add `ai`/data conferences; NumFOCUS/PyData India chapters. Revisit if we want more `ai`/conference depth. |
| **IEEE** | Low–medium | Academic/technical; India sections exist but discovery API is unclear. |
| Meetup.com | High volume but | Paid API / bot-protected — expensive per effort. |
| Docker / HashiCorp / AWS | Low (India) | Corporate marketing, thin India coverage (AWS already deferred). |

## Recommendation

**Stop adding providers. Shift engineering effort to quality.** We have 107 real,
deduped India events across 5 categories and ~25 cities — enough breadth that the
*marginal event per new provider is now lower than the marginal value of fixing
quality*. The highest-leverage work, in order:

1. **Category classification** (biggest quality win): derive `ai` / `startup` /
   `workshop` from titles + keywords at the boundary (many events already say
   "AI", "startup", "workshop"). Fixes the two empty categories without new data.
2. **Confs.tech upcoming filter** (data-quality bug): drop past events at the
   provider boundary.
3. **Ranking upgrade**: add the location-match + source-quality (+ optional
   popularity) signals to the existing deterministic scorer.
4. **Dedup hardening**: fuzzier cross-provider key (title similarity + city + date)
   before overlap grows.
5. **UX / recommendations** on the frontend: category chips as filters, "near me",
   "this weekend", and result grouping — this is where user-visible value now lives.

**Revisit providers only if a specific gap demands it** — e.g., add **PyData** if we
decide `ai`/data-conference depth is a priority after the classification fix.
