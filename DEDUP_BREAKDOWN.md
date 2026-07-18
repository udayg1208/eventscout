# Deduplication Breakdown

How the engine collapses the same event cross-posted across providers (different
titles / URLs / city spellings) into one richest record. **Deterministic**, fuzzy via
`rapidfuzz` — no embeddings, no vectors, no LLM. Code: `backend/app/providers/dedup.py`.

## Algorithm

1. **Block by `start_date`.** Duplicates share a date, so only same-day events are
   compared. This keeps the work near-linear (most date blocks hold a handful of
   events) instead of O(n²) over the whole set.
2. **Cluster within each block** by single-link greedy grouping: an event joins the
   first cluster containing a member it is similar to (≥ threshold), else it starts a
   new cluster. Stable input order ⇒ deterministic.
3. **Choose the richest** event of each cluster as the survivor.

## Similarity formula

`event_similarity(a, b) ∈ [0, 1]` with two hard gates then a fuzzy score:

```
if |a.date − b.date| > 1 day:                 return 0.0     # different dates
if a.city and b.city and normalized differ:    return 0.0     # different cities
url = url_similarity(a.url, b.url)
if url ≥ 0.95:                                  return 1.0     # same link confirms
return min(1.0, title_similarity + 0.10 · url)                # title drives, url nudges
```

- **`title_similarity`** = `max(token_sort_ratio, ratio)` on normalized titles.
  `token_sort_ratio` handles word **reordering** ("AI Meetup Bangalore" ↔ "Bangalore AI
  Meetup"); `ratio` handles **spacing/abbreviation** ("GenAI" ↔ "Gen AI"). We
  deliberately avoid `WRatio` — its partial-substring component over-matches short
  titles (it scored two unrelated events 0.87).
- **`url_similarity`** = 1.0 for equal normalized URLs, else char ratio.
- **`normalize_title`** lowercases, strips punctuation, collapses whitespace.
  **`normalize_url`** keeps host+path (drops scheme, `www.`, query, fragment, trailing
  slash). **`normalize_city`** canonicalizes aliases (Bengaluru → Bangalore).

**Threshold:** `0.85`. Real duplicates score ≥ 0.95; unrelated same-day/same-city
events score ≤ ~0.35 — a wide, safe margin.

## Merge rules / conflict resolution

`choose_best_event` keeps the single **richest** record (no Frankenstein field-merge,
so provenance stays intact). Richness key, compared in order:

1. completeness (count of populated optional fields)
2. has description
3. free/paid flag known
4. has price
5. has location
6. provider quality (`score_source`)
7. longer description (final tie-break)

## Examples

**Merged (real, this dataset):** exact title differs, same date, same provider — the
old exact-title dedup missed it, the new engine catches it:

| | Title | Provider | Date |
|---|---|---|---|
| A | The Fifth Elephant 2026 Annual Conference | hasgeek | 2026-07-31 |
| B | **Speak at** The Fifth Elephant 2026 Annual Conference | hasgeek | 2026-07-31 |

`title_similarity ≈ 0.96` → merged; the richer of the two survives.

**Protected against (false positives):**

| A | B | Why not merged |
|---|---|---|
| AI Meetup (Bangalore) | AI Meetup (Delhi) | city gate → 0.0 |
| AI Meetup (Jul 1) | AI Meetup (Aug 1) | date gate → 0.0 |
| Cloud Security Meetup | Frontend Development Workshop | title ≈ 0.32 |
| Build with Gemma | Founders Cubbon Walk | title ≈ 0.4 (WRatio wrongly gave 0.87) |

## Old vs new (live merged dataset, 109 events)

| Engine | Key | Duplicates removed |
|--------|-----|:------------------:|
| Old | exact `(normalized_title, start_date)` | **0** |
| New | fuzzy title + date/city gates + URL | **1** (the Fifth Elephant pair) |

The dataset currently has little cross-provider overlap (distinct platforms), so the
count is small — but the engine now catches slight-variation duplicates the old exact
key never could, with zero false positives. Reproduce: `python -m spikes.m11_dedup_compare`.

## Tuning
`_SIMILARITY_THRESHOLD`, `_URL_CONFIRM`, `_MAX_DATE_DELTA_DAYS` are the knobs. Tests in
`tests/test_dedup.py` cover each function plus all eight scenarios.
