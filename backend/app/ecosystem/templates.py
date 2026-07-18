"""Expansion templates (Phase 10D) — curated, deterministic data the expanders generate from.

Chapter/series expansion fans a known community across cities; sponsor expansion maps a big sponsor
to its known programs; university/venue expansion emits the standard campus club set. These are
*seeds to check*, not confirmed facts — a generated "GDG Delhi" is a target for discovery (10A/10B)
to verify. Data only; no logic, no network.
"""

from __future__ import annotations

from app.organizers.models import Cadence, NodeType

# Major Indian tech-event cities that chapter/series families commonly span.
CITIES: tuple[str, ...] = (
    "Bangalore",
    "Delhi",
    "Mumbai",
    "Pune",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Ahmedabad",
    "Jaipur",
    "Chandigarh",
    "Kochi",
    "Indore",
    "Bhopal",
    "Nagpur",
)

# Chapter family key → display prefix used to name siblings ("GDG" + city).
CHAPTER_DISPLAY: dict[str, str] = {
    "gdg": "GDG",
    "gdsc": "GDSC",
    "ieee": "IEEE",
    "acm": "ACM",
    "csi": "CSI",
    "mozilla": "Mozilla",
    "aws_ug": "AWS UG",
    "kubernetes": "Kubernetes Community",
    "cncf": "Cloud Native",
    "pydata": "PyData",
    "pyladies": "PyLadies",
    "tfug": "TFUG",
    "reactjs": "React",
    "rust": "Rust",
    "linux": "LUG",
    "fossunited": "FOSS United",
    "pythonuser": "PUG",
    "devops": "DevOpsDays",
}

# Sponsor (canonical-key substring) → its public programs/communities (program, technologies).
SPONSOR_PROGRAMS: dict[str, list[tuple[str, list[str]]]] = {
    "google": [
        ("Google Developers", ["Android", "Web", "Cloud"]),
        ("Google Cloud Community", ["Cloud", "Kubernetes", "AI"]),
        ("Google Developer Experts", ["Android", "AI", "Web"]),
        ("Build with AI", ["AI", "Machine Learning"]),
        ("Google Cloud Arcade", ["Cloud"]),
        ("Women Techmakers", ["Community"]),
        ("Google Summer of Code", ["Open Source"]),
    ],
    "microsoft": [
        ("Microsoft Reactor", ["Azure", "AI", "Web"]),
        ("Microsoft Learn Student Ambassadors", ["Azure", "AI"]),
        ("Azure Developer Community", ["Azure", "Cloud"]),
    ],
    "aws": [
        ("AWS User Groups", ["Cloud", "Serverless"]),
        ("AWS Community Builders", ["Cloud"]),
        ("AWS re/Start", ["Cloud"]),
    ],
    "meta": [
        ("Meta Developer Circles", ["React", "AI"]),
        ("PyTorch Community", ["Machine Learning"]),
    ],
    "github": [
        ("GitHub Campus Experts", ["Open Source"]),
        ("GitHub Education", ["Open Source"]),
    ],
    "redhat": [
        ("Red Hat Developer", ["Linux", "Kubernetes", "OpenShift"]),
    ],
}

# The standard campus club set discovered from a university/venue.
UNIVERSITY_UNITS: list[tuple[str, list[str], NodeType]] = [
    ("ACM Student Chapter", ["Computer Science"], NodeType.STUDENT_CHAPTER),
    ("IEEE Student Branch", ["Electronics", "AI"], NodeType.STUDENT_CHAPTER),
    ("CSI Chapter", ["Computer Science"], NodeType.STUDENT_CHAPTER),
    ("GDSC", ["Android", "Web", "Cloud"], NodeType.STUDENT_CHAPTER),
    ("E-Cell", ["Entrepreneurship"], NodeType.UNIVERSITY_CLUB),
    ("Incubation Center", ["Startups"], NodeType.ORGANIZATION),
    ("AI Club", ["AI", "Machine Learning"], NodeType.UNIVERSITY_CLUB),
    ("Robotics Club", ["Robotics", "IoT"], NodeType.UNIVERSITY_CLUB),
    ("Open Source Club", ["Open Source", "Linux"], NodeType.UNIVERSITY_CLUB),
    ("Coding Club", ["Programming"], NodeType.UNIVERSITY_CLUB),
]

# Series brand → default cadence (mirrors 10C; kept local so 10D needs no 10C internals).
SERIES_CADENCE: dict[str, Cadence] = {
    "DevFest": Cadence.ANNUAL,
    "Build with AI": Cadence.QUARTERLY,
    "Hacktoberfest": Cadence.ANNUAL,
    "Cloud Community Day": Cadence.ANNUAL,
    "Google Cloud Arcade": Cadence.QUARTERLY,
    "PyCon": Cadence.ANNUAL,
}


def sponsor_key(name: str) -> str | None:
    low = name.lower()
    for key in SPONSOR_PROGRAMS:
        if key in low:
            return key
    return None
