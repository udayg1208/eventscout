"""Universal validator (Phase 10B) — keep tech/professional events, reject everything else.

A page can contain event-shaped data that isn't a professional/tech event: shopping, politics,
religion, gambling, adult, entertainment, travel/tourism, coupons, jobs, products. This rejects
those — but only when the candidate shows a reject signal *and* no positive tech/event signal, so a
real hackathon that happens to mention "jobs" or "travel" survives. Also requires a minimum event
shape (a title). Every verdict is explained. Deterministic; no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.universal.models import ExtractedField
from app.universal.text_utils import detect_technologies

_REJECT = [
    (
        "shopping",
        re.compile(
            r"add to cart|buy now|shop now|checkout now|price drop|mega sale|flat \d+% off", re.I
        ),
    ),
    (
        "politics",
        re.compile(
            r"\belection\b|political party|vote for|campaign rally|\bparliament\b|\bmanifesto\b",
            re.I,
        ),
    ),
    (
        "religion",
        re.compile(
            r"\bchurch\b|\btemple\b|\bmosque\b|prayer meeting|\bsermon\b|religious gathering",
            re.I,
        ),
    ),
    (
        "gambling",
        re.compile(
            r"\bcasino\b|\bbetting\b|\bpoker\b|\blottery\b|\bjackpot\b|real money game", re.I
        ),
    ),
    ("adult", re.compile(r"\bxxx\b|\bescort\b|adult content|18\+ only", re.I)),
    (
        "entertainment",
        re.compile(
            r"movie premiere|film screening|celebrity meet|comedy night|music festival"
            r"|concert tickets",
            re.I,
        ),
    ),
    (
        "travel",
        re.compile(
            r"tour package|holiday package|travel package|honeymoon|resort booking|\btourism\b"
            r"|vacation deal",
            re.I,
        ),
    ),
    (
        "coupons",
        re.compile(r"promo code|coupon code|\bvoucher\b|cashback offer|deal of the day", re.I),
    ),
    (
        "jobs",
        re.compile(
            r"job opening|walk[- ]in interview|\bvacancy\b|now hiring"
            r"|apply for this (?:job|role)|recruitment drive",
            re.I,
        ),
    ),
    ("products", re.compile(r"order now|out of stock|free shipping|add to bag|product page", re.I)),
]


@dataclass
class ValidationResult:
    valid: bool
    reason: str | None = None


def _blob(fields: dict[str, ExtractedField]) -> str:
    parts = []
    for name in ("title", "description", "venue", "audience", "tags", "event_type"):
        f = fields.get(name)
        if f and f.is_known:
            parts.append(str(f.value))
    return " ".join(parts)


def _has_tech_event_signal(fields: dict[str, ExtractedField], blob: str) -> bool:
    if (fields.get("technologies") and fields["technologies"].is_known) or (
        fields.get("event_type") and fields["event_type"].is_known
    ):
        return True
    return bool(detect_technologies(blob))


class UniversalValidator:
    def validate(self, fields: dict[str, ExtractedField], context: str = "") -> ValidationResult:
        """Validate one event. `context` is the surrounding page text, so a fake "event" on a
        shopping/jobs page is caught even when its own fields look innocent."""
        title = fields.get("title")
        if not (title and title.is_known):
            return ValidationResult(False, "no title — not an event")
        blob = (_blob(fields) + " " + context).strip()
        # a real tech event survives an off-topic keyword; only reject when there is no tech signal
        tech_signal = _has_tech_event_signal(fields, blob)
        for category, pat in _REJECT:
            m = pat.search(blob)
            if m and not tech_signal:
                return ValidationResult(False, f"off-topic ({category}): matched '{m.group(0)}'")
        return ValidationResult(True, None)
