"""Organizer taxonomy (Phase 10C) — the known chapter families, series, and university units.

Deterministic pattern tables the detectors match against. Chapter families are the big recurring
communities (GDG, IEEE, ACM, PyData, …); series are the recurring event brands (DevFest,
Hacktoberfest, …); university units are the campus structures (department, student chapter,
innovation cell, …). Data only — no logic, no network.
"""

from __future__ import annotations

import re

from app.organizers.models import Cadence, NodeType

# (family key, canonical full name, pattern, node type)
CHAPTER_FAMILIES: list[tuple[str, str, re.Pattern[str], NodeType]] = [
    (
        "gdsc",
        "Google Developer Student Club",
        re.compile(r"\bgdsc\b|google developer student club", re.I),
        NodeType.STUDENT_CHAPTER,
    ),
    (
        "gdg",
        "Google Developer Group",
        re.compile(r"\bgdg\b|google developers? group", re.I),
        NodeType.CHAPTER,
    ),
    ("ieee", "IEEE", re.compile(r"\bieee\b", re.I), NodeType.PROFESSIONAL_SOCIETY),
    ("acm", "ACM", re.compile(r"\bacm\b", re.I), NodeType.PROFESSIONAL_SOCIETY),
    (
        "csi",
        "Computer Society of India",
        re.compile(r"\bcsi\b|computer society of india", re.I),
        NodeType.PROFESSIONAL_SOCIETY,
    ),
    ("mozilla", "Mozilla", re.compile(r"mozilla|\bmoz\b", re.I), NodeType.CHAPTER),
    (
        "aws_ug",
        "AWS User Group",
        re.compile(r"aws user group|\baws ug\b|awsug", re.I),
        NodeType.CHAPTER,
    ),
    (
        "kubernetes",
        "Kubernetes Community",
        re.compile(r"kubernetes|kcd\b|k8s", re.I),
        NodeType.CHAPTER,
    ),
    ("cncf", "Cloud Native Community", re.compile(r"cloud native|cncf", re.I), NodeType.CHAPTER),
    ("pydata", "PyData", re.compile(r"pydata", re.I), NodeType.CHAPTER),
    ("pyladies", "PyLadies", re.compile(r"pyladies", re.I), NodeType.CHAPTER),
    (
        "tfug",
        "TensorFlow User Group",
        re.compile(r"tfug|tensorflow user group", re.I),
        NodeType.CHAPTER,
    ),
    ("reactjs", "React Community", re.compile(r"\breact\b|reactjs", re.I), NodeType.CHAPTER),
    ("rust", "Rust Community", re.compile(r"\brust\b", re.I), NodeType.CHAPTER),
    (
        "linux",
        "Linux User Group",
        re.compile(r"\blug\b|linux user group|\blinux\b", re.I),
        NodeType.CHAPTER,
    ),
    ("fossunited", "FOSS United", re.compile(r"foss united|fossunited", re.I), NodeType.COMMUNITY),
    (
        "pythonuser",
        "Python User Group",
        re.compile(r"python user group|\bpug\b", re.I),
        NodeType.CHAPTER,
    ),
    (
        "devops",
        "DevOps Community",
        re.compile(r"devops days|\bdevopsdays\b", re.I),
        NodeType.CHAPTER,
    ),
]

# (series name, pattern, cadence)
SERIES_PATTERNS: list[tuple[str, re.Pattern[str], Cadence]] = [
    ("DevFest", re.compile(r"devfest", re.I), Cadence.ANNUAL),
    ("Build with AI", re.compile(r"build with ai", re.I), Cadence.QUARTERLY),
    ("Hacktoberfest", re.compile(r"hacktoberfest", re.I), Cadence.ANNUAL),
    ("Cloud Community Day", re.compile(r"cloud community day", re.I), Cadence.ANNUAL),
    (
        "Google Cloud Arcade",
        re.compile(r"cloud arcade|arcade facilitator", re.I),
        Cadence.QUARTERLY,
    ),
    ("PyCon", re.compile(r"\bpycon\b", re.I), Cadence.ANNUAL),
    ("FOSS Meetup", re.compile(r"foss meetup", re.I), Cadence.MONTHLY),
    ("Study Jam", re.compile(r"study jam", re.I), Cadence.QUARTERLY),
    ("Monthly Meetup", re.compile(r"monthly meetup", re.I), Cadence.MONTHLY),
    ("Weekly Workshop", re.compile(r"weekly workshop", re.I), Cadence.WEEKLY),
]

# (unit label, pattern, node type)
UNIVERSITY_UNITS: list[tuple[str, re.Pattern[str], NodeType]] = [
    (
        "student chapter",
        re.compile(r"student chapter|student branch|\bsb\b", re.I),
        NodeType.STUDENT_CHAPTER,
    ),
    ("club", re.compile(r"\bclub\b|\bcell\b", re.I), NodeType.UNIVERSITY_CLUB),
    ("department", re.compile(r"department|\bdept\.?\b|school of", re.I), NodeType.DEPARTMENT),
    (
        "innovation cell",
        re.compile(r"innovation cell|i-?cell|entrepreneurship cell|e-?cell", re.I),
        NodeType.UNIVERSITY_CLUB,
    ),
    ("incubator", re.compile(r"incubat(?:or|ion)", re.I), NodeType.ORGANIZATION),
    (
        "center of excellence",
        re.compile(r"center of excellence|centre of excellence|\bcoe\b", re.I),
        NodeType.DEPARTMENT,
    ),
]

_UNIVERSITY = re.compile(
    r"\b(?:IIT|NIT|IIIT|BITS|VIT|SRM|MUJ|Manipal|university|college|institute of technology|"
    r"institute)\b",
    re.IGNORECASE,
)

_CADENCE_WORDS: list[tuple[Cadence, re.Pattern[str]]] = [
    (Cadence.WEEKLY, re.compile(r"\bweekly\b|every week", re.I)),
    (Cadence.MONTHLY, re.compile(r"\bmonthly\b|every month|each month", re.I)),
    (Cadence.QUARTERLY, re.compile(r"\bquarterly\b|every quarter", re.I)),
    (Cadence.ANNUAL, re.compile(r"\bannual\b|\byearly\b|every year", re.I)),
]

_SPONSOR = re.compile(
    r"sponsored by\s+([A-Z][\w& ]{1,39})|in partnership with\s+([A-Z][\w& ]{1,39})"
    r"|powered by\s+([A-Z][\w& ]{1,39})",
    re.IGNORECASE,
)


def detect_cadence_word(text: str) -> tuple[Cadence, str] | None:
    for cad, pat in _CADENCE_WORDS:
        m = pat.search(text)
        if m:
            return cad, m.group(0)
    return None


def find_sponsors(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _SPONSOR.finditer(text):
        name = next((g for g in m.groups() if g), "").strip(" .")
        if name:
            out.append((name, m.group(0)))
    return out


def is_university(text: str) -> bool:
    return bool(_UNIVERSITY.search(text))
