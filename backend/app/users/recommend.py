"""Recommendation scoring weights + deterministic explanation generation.

Every recommendation explains *why* — built from the strongest matched preference features,
in a fixed order, so the same profile + event always yields the same reasons. No LLM.
"""

from __future__ import annotations

from app.users.models import UserProfile

RECOMMENDATION_WEIGHTS = {
    "interest": 0.6,
    "freshness": 0.15,
    "trending": 0.15,
    "similarity": 0.10,
}

# Which matched features make the most compelling *explanation* (lower = mentioned first),
# independent of scoring — "you follow GDG" beats "you like meetup events" even when tied.
_NAMESPACE_PRIORITY = {
    "community": 0,
    "organizer": 0,
    "topic": 1,
    "tech": 2,
    "city": 3,
    "category": 4,
}


def _phrase(namespace: str, value: str, profile: UserProfile) -> str | None:
    if namespace in ("community", "organizer"):
        return f"Recommended because you follow {value}."
    if namespace == "topic":
        if profile.attended_count > 0:
            return f"Recommended because you frequently attend {value} events."
        return f"Recommended because you're interested in {value}."
    if namespace == "tech":
        return f"Recommended because you're interested in {value}."
    if namespace == "city":
        return f"Recommended because you attend events in {value}."
    if namespace == "category":
        return f"Recommended because you like {value} events."
    return None


def generate_reasons(
    profile: UserProfile,
    features: dict[str, float],
    *,
    similar_to_engaged: bool,
    max_reasons: int = 3,
) -> list[str]:
    matched = sorted(
        ((f, profile.weight(f)) for f in features if profile.weight(f) > 0),
        key=lambda kv: (_NAMESPACE_PRIORITY.get(kv[0].split(":", 1)[0], 9), -kv[1], kv[0]),
    )
    reasons: list[str] = []
    budget = max_reasons - (1 if similar_to_engaged else 0)
    for feature, _weight in matched:
        namespace, value = feature.split(":", 1)
        phrase = _phrase(namespace, value, profile)
        if phrase and phrase not in reasons:
            reasons.append(phrase)
        if len(reasons) >= budget:
            break
    if similar_to_engaged and len(reasons) < max_reasons:
        reasons.append("Recommended because it's similar to events you've engaged with.")
    if not reasons:
        reasons.append("Recommended based on freshness and trending signals.")
    return reasons[:max_reasons]
