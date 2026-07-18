"""Hybrid Retriever — Reciprocal Rank Fusion (RRF) over candidate sets.

RRF fuses several retrievers' ranked lists using only rank *position*, so it is agnostic to
each retriever's score scale (bm25 vs. recency vs. entity) — no per-retriever weight tuning
required. A candidate's fused score is the sum over sets of `1 / (k + rank)`. Deterministic:
ties break by event key. A single set passes through in its own order.
"""

from __future__ import annotations

from collections import defaultdict

from app.search.candidates import Candidate, CandidateSet

_RRF_K = 60  # standard RRF constant; dampens the weight of very deep ranks


class HybridRetriever:
    def __init__(self, k: int = _RRF_K) -> None:
        self._k = k

    def fuse(self, candidate_sets: list[CandidateSet], *, limit: int) -> list[Candidate]:
        scores: dict[str, float] = defaultdict(float)
        sources: dict[str, set[str]] = defaultdict(set)
        for candidate_set in candidate_sets:
            for rank, candidate in enumerate(candidate_set.candidates):
                scores[candidate.event_key] += 1.0 / (self._k + rank + 1)
                sources[candidate.event_key].add(candidate.source)
        fused = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))  # deterministic
        return [
            Candidate(key, score, "+".join(sorted(sources[key]))) for key, score in fused[:limit]
        ]
