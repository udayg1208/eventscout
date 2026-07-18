# Ranking Score Breakdown

How the search engine orders results. Fully **deterministic and explainable** — no
embeddings, no vectors, no LLM. Every event gets a score in `[0, 1]` from six pure
functions in `backend/app/providers/ranking.py`, combined with one weight table
(`WEIGHTS`).

## The weighted model

| Component | Weight | Function | Range | What it measures |
|-----------|:------:|----------|:-----:|------------------|
| Query relevance | **40%** | `score_query_relevance` | 0–1 | Query keywords in title/description + category match |
| Date proximity | **20%** | `score_date` | 0–1 | `1 / (1 + days_until/30)`; past = 0 (0.5 at ~30 days out) |
| Location match | **15%** | `score_location` | 0/0.5/1 | Exact city = 1, online = 0.5, else 0; 0 when no city queried |
| Source quality | **10%** | `score_source` | 0–1 | Per-provider data-quality prior (fossunited 1.0 … gdg/cncf 0.6) |
| Popularity / richness | **10%** | `score_popularity` | 0–1 | Content richness (description length, known price, venue, multi-day) — the model has no attendee data |
| Completeness | **5%** | `score_completeness` | 0–1 | Share of optional fields populated (out of 6) |

`score_event = Σ WEIGHTS[c] · score_c`. Weights sum to 1.0 (unit-tested). Ties break
deterministically by sooner `start_date`, then title.

## Worked example
Top result for **"AI events in Bangalore"** — *Gemma × Hugging Face Bengaluru Meetup*
(provider `luma`, city Bangalore), computed live:

| Component | score | × weight | contribution |
|-----------|:-----:|:--------:|:------------:|
| relevance | 1.000 | 0.40 | 0.400 |
| date | 0.968 | 0.20 | 0.194 |
| location | 1.000 | 0.15 | 0.150 |
| source | 0.700 | 0.10 | 0.070 |
| popularity | 0.150 | 0.10 | 0.015 |
| completeness | 0.333 | 0.05 | 0.017 |
| **TOTAL** | | | **0.845** |

It wins on relevance (classified `ai`, matches the category), an imminent date, and an
exact Bangalore match — exactly the intuition we want, and you can see *why*.

## Before / after (live dataset, same events, reordered)

Old scorer: 0.50 relevance (which folded city in) / 0.35 date / 0.15 completeness — no
source or richness signal. New scorer adds location, source quality, and richness.

**"all upcoming" (browse, 108 results) — 4 of the top 6 changed:**

| # | OLD | NEW |
|---|-----|-----|
| 1 | FutureForge Hackathon `[devfolio]` | FutureForge Hackathon `[devfolio]` |
| 2 | Build with Gemma `[devfolio]` | Build with Gemma `[devfolio]` |
| 3 | FOSS - GCEE `[fossunited]` | **HackVSIT7.0 `[devfolio]`** |
| 4 | Gemma × Hugging Face `[luma]` | **FOSS - GCEE `[fossunited]`** |
| 5 | Google Cloud Arcade `[gdg]` | **HyperFusion `[devfolio]`** |
| 6 | Kickstart with AI `[gdg]` | **Ignisys 1.O `[devfolio]`** |

**"events in Bangalore" (35 results) — 4 of the top 6 changed.**

**Interpretation:** the new ranking promotes events with richer data and higher source
quality (devfolio hackathons carry descriptions + a known free/paid flag) above sparse
records (gdg events expose almost no fields), among events of similar date. Precise
queries like "AI events in Bangalore" (4 results) are already decided by relevance +
date, so their order is unchanged — the new signals act as tie-breakers, exactly as
intended (source quality "influences ordering only when relevance is similar").

## Tuning
All behavior lives in two constants in `ranking.py`: `WEIGHTS` and `_SOURCE_QUALITY`.
Change a weight, re-run the tests (`tests/test_ranking.py` covers each component and the
five ordering scenarios), and regenerate this comparison via
`python -m spikes.m10_ranking_compare`.
