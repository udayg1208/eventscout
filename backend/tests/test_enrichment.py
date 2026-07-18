"""Phase 5A: AI Event Understanding — deterministic, network-free.

Covers topic/technology extraction, skills, audiences, difficulty, career relevance,
summaries, enrichment, event similarity, the metadata store, and the pipeline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from app.enrichment import (
    DeterministicEnricher,
    Difficulty,
    EnrichmentPipeline,
    InMemoryEnrichmentStore,
    career_relevance,
    detect_audiences,
    estimate_difficulty,
    extract_technologies,
    extract_topics,
    generate_summary,
    infer_skills,
)
from app.models.event import Event, EventCategory
from app.storage.models import StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def _event(title, *, category=EventCategory.MEETUP, description=None, city="Bangalore"):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').replace('/', '-').lower()}",
        city=city,
        provider="p",
        start_date=date(2026, 9, 1),
        category=category,
        description=description,
    )


def _stored(event):
    return StoredEvent.from_event(event, seen_at=NOW)


# --------------------------- extraction ---------------------------


def test_extract_topics_in_taxonomy_order():
    e = _event("Cloud and DevOps with Kubernetes", description="Backend microservices")
    assert extract_topics(e) == ["Cloud", "DevOps", "Kubernetes", "Backend"]


def test_extract_topics_ai_family():
    e = _event("Generative AI and LLMs", description="artificial intelligence and machine learning")
    assert extract_topics(e) == [
        "Artificial Intelligence",
        "Machine Learning",
        "LLMs",
        "Generative AI",
    ]


def test_extract_technologies():
    e = _event("Python and Docker workshop", description="Deploy React on AWS")
    assert extract_technologies(e) == ["Python", "React", "Docker", "AWS"]


def test_technology_java_not_javascript():
    assert extract_technologies(_event("JavaScript deep dive")) == ["JavaScript"]
    assert extract_technologies(_event("Core Java patterns")) == ["Java"]


# --------------------------- difficulty ---------------------------


def test_difficulty_estimation():
    assert estimate_difficulty(_event("Advanced Kubernetes Deep Dive")) is Difficulty.ADVANCED
    assert estimate_difficulty(_event("Kubernetes 101 for Beginners")) is Difficulty.BEGINNER
    assert estimate_difficulty(_event("Kubernetes Community Meetup")) is Difficulty.INTERMEDIATE
    # category prior: workshops skew beginner
    assert (
        estimate_difficulty(_event("Build things", category=EventCategory.WORKSHOP))
        is Difficulty.BEGINNER
    )


# --------------------------- skills / audiences / careers ---------------------------


def test_infer_skills():
    skills = infer_skills(_event("x", category=EventCategory.WORKSHOP), ["LLMs"])
    assert "Prompt Engineering" in skills and "AI Engineering" in skills
    assert "Hands-on Building" in skills  # workshop format
    assert "Networking" in infer_skills(_event("x", category=EventCategory.CONFERENCE), [])


def test_detect_audiences():
    aud = detect_audiences(
        _event("x", category=EventCategory.HACKATHON), ["Startup"], Difficulty.INTERMEDIATE
    )
    assert "Founders" in aud and "Students" in aud and "Developers" in aud
    # empty topics → sensible default
    assert detect_audiences(_event("x"), [], Difficulty.INTERMEDIATE) == ["Developers"]


def test_career_relevance():
    assert career_relevance(["Machine Learning"]) == ["ML Engineer", "AI Engineer"]
    assert career_relevance(["Cybersecurity"]) == ["Cybersecurity Engineer"]
    assert career_relevance([]) == []


def test_generate_summary():
    summary = generate_summary(
        _event("x", category=EventCategory.WORKSHOP, city="Pune"),
        topics=["LLMs"],
        technologies=["Python"],
        audiences=["Developers"],
        difficulty=Difficulty.BEGINNER,
    )
    assert (
        summary
        == "A beginner-level workshop on LLMs featuring Python, aimed at Developers, in Pune."
    )


# --------------------------- enricher ---------------------------


def test_enricher_produces_full_understanding():
    e = _event(
        "Hands-on GenAI Workshop: Building LLM apps with LangChain",
        category=EventCategory.WORKSHOP,
        description="Learn prompt engineering and deploy on AWS with Python.",
    )
    enr = DeterministicEnricher().enrich("k1", e)
    assert "LLMs" in enr.topics and "Generative AI" in enr.topics
    assert set(enr.technologies) >= {"Python", "AWS", "LangChain"}
    assert "Prompt Engineering" in enr.skills
    assert enr.difficulty is Difficulty.BEGINNER
    assert enr.careers == ["AI Engineer"]
    assert enr.summary and enr.method.value == "deterministic"


def test_enricher_is_deterministic():
    e = _event("Kubernetes and Cloud", description="DevOps with Docker")
    a = DeterministicEnricher().enrich("k", e)
    b = DeterministicEnricher().enrich("k", e)
    assert a == b


# --------------------------- similarity ---------------------------


def test_event_similarity():
    ai_1 = _event(
        "Applied Machine Learning", description="AI models", category=EventCategory.MEETUP
    )
    ai_2 = _event(
        "Deep Learning with PyTorch",
        description="machine learning and AI",
        category=EventCategory.MEETUP,
    )
    unrelated = _event(
        "Indie Game Dev Night", description="gaming", category=EventCategory.CONFERENCE
    )
    pipeline = EnrichmentPipeline()
    pipeline.enrich_events([_stored(ai_1), _stored(ai_2), _stored(unrelated)])
    similar = pipeline.similarity().similar_to(_stored(ai_1).key)
    scores = dict(similar)
    assert similar[0][0] == _stored(ai_2).key  # the AI/ML + same-category event ranks first
    # the unrelated event only shares the generic "Networking" skill → far lower score
    assert scores[_stored(ai_2).key] > scores.get(_stored(unrelated).key, 0.0)


def test_similarity_missing_key_is_empty():
    pipeline = EnrichmentPipeline()
    pipeline.enrich_events([_stored(_event("A"))])
    assert pipeline.similarity().similar_to("nonexistent") == []


# --------------------------- store + pipeline ---------------------------


def test_enrichment_store():
    store = InMemoryEnrichmentStore()
    enr = DeterministicEnricher().enrich("k1", _event("AI Meetup"))
    store.save(enr)
    assert store.get("k1") == enr and store.count() == 1
    assert store.get("missing") is None


def test_pipeline_run_over_repository():
    repo = SQLiteEventRepository()
    events = [
        _event("Machine Learning Summit", description="AI"),
        _event("Kubernetes Workshop", category=EventCategory.WORKSHOP),
    ]
    run(repo.bulk_upsert([_stored(e) for e in events]))
    pipeline = EnrichmentPipeline()
    count = run(pipeline.run(repo))
    assert count == 2
    stored = _stored(events[0])
    enrichment = pipeline.store.get(stored.key)
    assert enrichment is not None and "Machine Learning" in enrichment.topics
