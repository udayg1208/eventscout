"""AI Classification (Phase 6G / D4) — label a discovered source across 14 classes.

`AIClassifier` is the seam an LLM plugs into; `MockAIClassifier` is a deterministic stand-in that
labels from the page text plus the AIExtraction. Every label carries a confidence and a reason —
nothing opaque — and classes only fire on positive evidence (no evidence → the label simply
doesn't appear). NON_TECH is asserted only when there is genuinely no technology signal.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from app.discovery.ai.extractor import ExtractionInput
from app.discovery.ai.models import AIClassification, AIExtraction, ClassLabel, SourceClass

# (SourceClass, regex, confidence, reason) — evidence-driven, deterministic.
_RULES: list[tuple[SourceClass, str, float, str]] = [
    (
        SourceClass.UNIVERSITY,
        r"\buniversity\b|\bcollege\b|\binstitute\b|student branch|campus|\.edu\b|\.ac\.in",
        0.85,
        "academic markers",
    ),
    (
        SourceClass.GOVERNMENT,
        r"\bministry\b|\bgovernment\b|\bgovt\b|gov\.in|nic\.in|municipal",
        0.85,
        "government markers",
    ),
    (
        SourceClass.COMMUNITY,
        r"\bcommunity\b|user group|\bchapter\b|meetup group|\bgdg\b|foss united|pydata",
        0.8,
        "community markers",
    ),
    (
        SourceClass.CONFERENCE,
        r"\bconference\b|\bsummit\b|\bconf\b|rootconf|pycon",
        0.8,
        "conference markers",
    ),
    (SourceClass.MEETUP, r"\bmeetups?\b|user group", 0.8, "meetup markers"),
    (SourceClass.HACKATHON, r"\bhackathons?\b|devfolio|hack\b", 0.85, "hackathon markers"),
    (SourceClass.WEBINAR, r"\bwebinars?\b|online session|virtual event", 0.75, "webinar markers"),
    (SourceClass.WORKSHOP, r"\bworkshops?\b|\bbootcamp\b|hands-?on", 0.75, "workshop markers"),
    (
        SourceClass.STARTUP,
        r"\bstartups?\b|\bfounders?\b|accelerator|incubator|pitch|demo day",
        0.75,
        "startup markers",
    ),
    (
        SourceClass.PRODUCT,
        r"product launch|product demo|our platform|\bsaas\b|launch event",
        0.7,
        "product markers",
    ),
    (
        SourceClass.OPEN_SOURCE,
        r"open source|\boss\b|\bfoss\b|github\.com|apache|linux foundation",
        0.8,
        "open-source markers",
    ),
    (
        SourceClass.COMPANY,
        r"\bpvt\.?\s*ltd\b|\binc\.?\b|we are hiring|\bcareers\b|engineering team",
        0.65,
        "company markers",
    ),
]


class AIClassifier(ABC):
    name: str = "classifier"

    @abstractmethod
    def classify(self, page: ExtractionInput, extraction: AIExtraction) -> AIClassification: ...


class MockAIClassifier(AIClassifier):
    name = "mock-classifier"

    def classify(self, page: ExtractionInput, extraction: AIExtraction) -> AIClassification:
        body = f"{page.title or ''}\n{page.text}".lower()
        labels: list[ClassLabel] = []

        # Tech vs non-tech is anchored on the extraction's technology evidence (not keywords alone).
        if extraction.technologies.is_known:
            n = len(extraction.technologies.value)  # type: ignore[arg-type]
            labels.append(
                ClassLabel(
                    SourceClass.TECH,
                    round(min(1.0, 0.5 + n * 0.2), 3),
                    f"{n} technology(ies) extracted",
                )
            )
        else:
            labels.append(ClassLabel(SourceClass.NON_TECH, 0.6, "no technology signal found"))

        for cls, pat, conf, reason in _RULES:
            m = re.search(pat, body)
            if m:
                labels.append(ClassLabel(cls, conf, f"{reason}: '{m.group(0)}'"))

        # Highest-confidence label first; stable by class name for determinism on ties.
        labels.sort(key=lambda ceil: (-ceil.confidence, ceil.label.value))
        return AIClassification(labels=labels, method=extraction.method)
