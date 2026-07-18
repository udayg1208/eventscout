"""Deterministic taxonomies — the knowledge behind extraction.

Ordered lists of (canonical name, high-precision regex) for topics and technologies, plus
rule maps from topics → skills / audiences / careers, and difficulty signals. Ordered so
extraction output is deterministic. Conservative patterns (word-boundaried) to avoid false
positives, in the spirit of the frozen `classify.py`.
"""

from __future__ import annotations

import re

from app.enrichment.models import Difficulty

_I = re.IGNORECASE


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, _I)


# --- topics (canonical, pattern) — order = output order ---
TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("Artificial Intelligence", _p(r"\ba\.?i\.?\b|artificial intelligence")),
    ("Machine Learning", _p(r"machine learning|\bml\b|\bmlops\b")),
    ("LLMs", _p(r"\bllms?\b|large language model|\bgpt\b|chatgpt")),
    ("Generative AI", _p(r"generative ai|gen ?ai|\bgenai\b|diffusion model|\bgemma\b")),
    ("Data Science", _p(r"data science|data scientist|data engineering|big data|\banalytics\b")),
    ("Cloud", _p(r"\bcloud\b|serverless")),
    ("DevOps", _p(r"\bdevops\b|ci ?/ ?cd|\bcicd\b|site reliability|\bsre\b")),
    ("Kubernetes", _p(r"kubernetes|\bk8s\b|cloud native")),
    ("Backend", _p(r"\bbackend\b|back[- ]end|server[- ]side|microservices?")),
    ("Frontend", _p(r"\bfrontend\b|front[- ]end|\breact\b|\bangular\b|\bvue\b")),
    ("Mobile", _p(r"\bmobile\b|\bandroid\b|\bios\b|\bflutter\b|react native")),
    ("Cybersecurity", _p(r"cyber ?security|infosec|\bpentest|ethical hack|application security")),
    ("Blockchain", _p(r"blockchain|\bethereum\b|\bbitcoin\b|smart contract")),
    ("Web3", _p(r"\bweb3\b|decentrali[sz]ed|\bdefi\b|\bnfts?\b")),
    ("Product", _p(r"product management|product manager|\bproduct\b")),
    ("Startup", _p(r"start[- ]?ups?|founders?|entrepreneur|pitch|demo day|fundrais")),
    ("Open Source", _p(r"open ?source|\bfoss\b|\boss\b")),
    ("Robotics", _p(r"robotics|\brobots?\b")),
    ("IoT", _p(r"\biot\b|internet of things|embedded systems")),
    ("AR/VR", _p(r"\bar ?/ ?vr\b|augmented reality|virtual reality|metaverse|\bxr\b")),
    ("Gaming", _p(r"\bgaming\b|game ?dev|game development")),
]

# --- technologies (canonical, pattern) ---
TECHNOLOGIES: list[tuple[str, re.Pattern[str]]] = [
    ("Python", _p(r"\bpython\b")),
    ("Java", _p(r"\bjava\b")),
    ("JavaScript", _p(r"\bjavascript\b|\bjs\b")),
    ("TypeScript", _p(r"\btypescript\b|\bts\b")),
    ("React", _p(r"\breact\b")),
    ("Next.js", _p(r"next\.?js\b")),
    ("Node.js", _p(r"node\.?js\b|\bnodejs\b")),
    ("Docker", _p(r"\bdocker\b")),
    ("Kubernetes", _p(r"kubernetes|\bk8s\b")),
    ("TensorFlow", _p(r"tensor ?flow")),
    ("PyTorch", _p(r"py ?torch")),
    ("AWS", _p(r"\baws\b|amazon web services")),
    ("Azure", _p(r"\bazure\b")),
    ("GCP", _p(r"\bgcp\b|google cloud")),
    ("Rust", _p(r"\brust\b")),
    ("Go", _p(r"\bgolang\b")),
    ("Flutter", _p(r"\bflutter\b")),
    ("LangChain", _p(r"lang ?chain")),
    ("OpenAI", _p(r"open ?ai")),
    ("Claude", _p(r"\bclaude\b")),
    ("Gemini", _p(r"\bgemini\b|\bgemma\b")),
]

# --- topic → skills / audiences / careers ---
TOPIC_SKILLS: dict[str, list[str]] = {
    "Artificial Intelligence": ["AI Engineering"],
    "Machine Learning": ["Machine Learning", "MLOps"],
    "LLMs": ["Prompt Engineering", "AI Engineering"],
    "Generative AI": ["Prompt Engineering", "AI Engineering"],
    "Data Science": ["Data Analysis", "Machine Learning"],
    "Cloud": ["Cloud Architecture"],
    "DevOps": ["DevOps", "MLOps"],
    "Kubernetes": ["Cloud Architecture", "DevOps"],
    "Backend": ["Backend Development"],
    "Frontend": ["Frontend Development"],
    "Mobile": ["Mobile Development"],
    "Cybersecurity": ["Security Engineering"],
    "Startup": ["Product Management", "Leadership"],
    "Product": ["Product Management"],
    "Open Source": ["Open Source Contribution"],
}

TOPIC_AUDIENCES: dict[str, list[str]] = {
    "Artificial Intelligence": ["Developers", "Data Scientists"],
    "Machine Learning": ["Data Scientists", "Researchers"],
    "LLMs": ["Developers", "Researchers"],
    "Generative AI": ["Developers"],
    "Data Science": ["Data Scientists"],
    "Cloud": ["Developers"],
    "DevOps": ["Developers"],
    "Kubernetes": ["Developers"],
    "Backend": ["Developers"],
    "Frontend": ["Developers", "Designers"],
    "Mobile": ["Developers"],
    "Cybersecurity": ["Security Engineers"],
    "Startup": ["Founders", "Product Managers"],
    "Product": ["Product Managers"],
    "Robotics": ["Researchers"],
}

TOPIC_CAREERS: dict[str, list[str]] = {
    "Artificial Intelligence": ["AI Engineer"],
    "Machine Learning": ["ML Engineer", "AI Engineer"],
    "LLMs": ["AI Engineer"],
    "Generative AI": ["AI Engineer"],
    "Data Science": ["Data Scientist"],
    "Cloud": ["Cloud Engineer"],
    "DevOps": ["DevOps Engineer"],
    "Kubernetes": ["DevOps Engineer", "Cloud Engineer"],
    "Backend": ["Software Engineer"],
    "Frontend": ["Software Engineer"],
    "Mobile": ["Software Engineer"],
    "Cybersecurity": ["Cybersecurity Engineer"],
    "Startup": ["Founder"],
    "Product": ["Product Manager"],
    "Robotics": ["Software Engineer"],
    "IoT": ["Software Engineer"],
}

# --- difficulty signals ---
_BEGINNER = _p(
    r"\b(beginner|intro(duction)?|101|getting started|basics|fundamentals|"
    r"no experience|for beginners)\b"
)
_ADVANCED = _p(r"\b(advanced|deep ?dive|expert|internals|in[- ]depth|masterclass)\b")


def difficulty_from_text(text: str, *, category: str) -> Difficulty:
    if _ADVANCED.search(text):
        return Difficulty.ADVANCED
    if _BEGINNER.search(text):
        return Difficulty.BEGINNER
    # category priors: hands-on formats skew beginner-ish, conferences intermediate.
    if category in {"workshop", "hackathon"}:
        return Difficulty.BEGINNER
    return Difficulty.INTERMEDIATE
