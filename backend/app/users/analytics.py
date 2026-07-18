"""User Analytics — a per-user summary from the profile + stores."""

from __future__ import annotations

from app.users.models import UserProfile


def build_user_analytics(
    *,
    profile: UserProfile,
    saved: set[str],
    attended_keys: set[str],
    interaction_counts: dict[str, int],
    shown_recs: set[str],
    engaged_keys: set[str],
) -> dict:
    acceptance = round(len(shown_recs & engaged_keys) / len(shown_recs), 4) if shown_recs else 0.0
    return {
        "saved_events": len(saved),
        "attended_events": len(attended_keys),
        "favorite_topics": profile.top("topic", 5),
        "favorite_technologies": profile.top("tech", 5),
        "favorite_communities": profile.top("community", 5),
        "preferred_cities": profile.top("city", 5),
        "preferred_format": profile.preferred_format,
        "budget_preference": profile.budget_preference,
        "interaction_counts": interaction_counts,
        "recommendation_acceptance": acceptance,
    }
