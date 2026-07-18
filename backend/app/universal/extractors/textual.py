"""Textual extractors (Phase 10B) — Markdown, Tables, Definition lists, FAQ.

For pages whose event information is in prose/structure rather than serialized JSON: GitHub READMEs
and docs (MkDocs/Docusaurus/Notion exports) in Markdown; schedule/agenda `Date | Event | Venue`
tables; `<dl>` definition lists (When/Where/Cost); and FAQ blocks (When? Where? How to register?).
Each maps its structure to universal fields with provenance via the shared `enrich_from_text`
helper.
"""

from __future__ import annotations

import re

from app.universal.extractors.base import enrich_from_text, raw_from_text
from app.universal.models import ExtractedField, ExtractionResult, ExtractionSource, Page, RawEvent
from app.universal.provenance import known
from app.universal.text_utils import find_date, find_registration_url, strip_tags

_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _page_title(page: Page) -> tuple[str, str] | None:
    for pat, why in ((_H1, "<h1>"), (_TITLE, "<title>")):
        m = pat.search(page.html)
        if m:
            text = strip_tags(m.group(1))
            if text:
                return text[:200], why
    return None


# --------------------------------------------------------------------------- field roles

_ROLE = [
    ("deadline", re.compile(r"deadline|last date|closes", re.I)),
    ("start_date", re.compile(r"\bdate\b|\bwhen\b|\bday\b|schedule", re.I)),
    ("registration_url", re.compile(r"regist|rsvp|\blink\b|apply|tickets?", re.I)),
    ("fee", re.compile(r"\bcost\b|\bfee\b|\bprice\b|charge", re.I)),
    ("venue", re.compile(r"venue|where|location|place|room|hall", re.I)),
    ("speakers", re.compile(r"speaker|presenter|by\b", re.I)),
    ("organizer", re.compile(r"organi[sz]er|host|organi[sz]ed", re.I)),
    ("city", re.compile(r"\bcity\b", re.I)),
    ("audience", re.compile(r"eligib|audience|who\b|for whom", re.I)),
    (
        "title",
        re.compile(
            r"event|\btitle\b|topic|session|workshop|\btalk\b|conference|meetup|hackathon", re.I
        ),
    ),
]


def _role_of(label: str) -> str | None:
    low = label.lower()
    for name, pat in _ROLE:
        if pat.search(low):
            return name
    return None


def _field_for(role: str, value: str, snippet: str, conf: float) -> ExtractedField | None:
    value = value.strip()
    if not value:
        return None
    if role in ("start_date", "deadline"):
        d = find_date(value)
        return (
            known(d[0], snippet=snippet, reason=f"{role} cell/label", confidence=conf)
            if d
            else None
        )
    if role == "registration_url":
        m = re.search(r'href=["\']([^"\']+)["\']', value) or re.search(r"https?://\S+", value)
        return (
            known(
                m.group(1) if m else value,
                snippet=snippet,
                reason="registration cell",
                confidence=conf,
            )
            if m
            else None
        )
    if role == "speakers":
        return known(
            [s.strip() for s in re.split(r",|&|/", strip_tags(value)) if s.strip()][:8],
            snippet=snippet,
            reason="speakers cell",
            confidence=conf,
        )
    return known(
        strip_tags(value)[:200], snippet=snippet, reason=f"{role} cell/label", confidence=conf
    )


# --------------------------------------------------------------------------- markdown

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
_MD_ROW = re.compile(r"^\s*\|(.+)\|\s*$", re.MULTILINE)
_MD_SEP = re.compile(r"^\s*\|?\s*:?-{2,}")


def _looks_markdown(page: Page) -> bool:
    if "markdown" in page.content_type:
        return True
    html = page.html
    tags = html.count("<")
    md_marks = len(_MD_HEADING.findall(html)) + html.count("| ")
    return md_marks >= 2 and tags < md_marks * 4


class MarkdownExtractor:
    source = ExtractionSource.MARKDOWN

    def extract(self, page: Page) -> ExtractionResult:
        if not _looks_markdown(page):
            return ExtractionResult(source=self.source, note="not markdown")
        text = page.html
        events: list[RawEvent] = []
        # headings whose section carries a date → an event
        headings = list(_MD_HEADING.finditer(text))
        for i, h in enumerate(headings):
            title = h.group(2).strip()
            body = text[h.end() : headings[i + 1].start() if i + 1 < len(headings) else len(text)]
            if find_date(title + " " + body[:400]):
                events.append(
                    raw_from_text(
                        self.source,
                        title=title,
                        title_snippet=f"# {title}",
                        text=title + " " + body[:600],
                        base_url=page.url,
                        conf=0.5,
                    )
                )
        # markdown table rows
        events.extend(_markdown_table(text, page.url, self.source))
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} markdown events"
        )


def _markdown_table(text: str, base_url: str, source: ExtractionSource) -> list[RawEvent]:
    rows = [m.group(1) for m in _MD_ROW.finditer(text)]
    if len(rows) < 3:
        return []
    header = [c.strip() for c in rows[0].split("|")]
    roles = [_role_of(c) for c in header]
    if "title" not in roles and "start_date" not in roles:
        return []
    events: list[RawEvent] = []
    for row in rows[1:]:
        if _MD_SEP.match("|" + row):
            continue
        cells = [c.strip() for c in row.split("|")]
        ev = _row_to_event(header, roles, cells, base_url, source, "markdown table row")
        if ev:
            events.append(ev)
    return events


# --------------------------------------------------------------------------- html tables

_TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.IGNORECASE | re.DOTALL)


def _row_to_event(header, roles, cells, base_url, source, why) -> RawEvent | None:
    f: dict[str, ExtractedField] = {}
    for role, raw in zip(roles, cells, strict=False):
        if role and role not in f:
            ef = _field_for(role, raw, f"{why}: {strip_tags(raw)[:60]}", 0.55)
            if ef:
                f[role] = ef
    if "title" not in f or not f["title"].is_known:
        return None
    joined = " ".join(strip_tags(c) for c in cells)
    enrich_from_text(f, joined, base_url=base_url, conf=0.5)
    return RawEvent(source=source, fields=f)


class TableExtractor:
    source = ExtractionSource.TABLE

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for body in _TABLE.findall(page.html):
            rows = _TR.findall(body)
            if len(rows) < 2:
                continue
            header = [strip_tags(c) for c in _CELL.findall(rows[0])]
            roles = [_role_of(c) for c in header]
            if "title" not in roles and "start_date" not in roles:
                continue
            for row in rows[1:]:
                cells = _CELL.findall(row)
                if len(cells) < 2:
                    continue
                ev = _row_to_event(header, roles, cells, page.url, self.source, "table row")
                if ev:
                    events.append(ev)
        # markdown tables that survived into .html
        events.extend(_markdown_table(page.html, page.url, self.source))
        return ExtractionResult(source=self.source, events=events, note=f"{len(events)} table rows")


# --------------------------------------------------------------------------- definition lists

_DL = re.compile(r"<dl\b[^>]*>(.*?)</dl>", re.IGNORECASE | re.DOTALL)
_DT_DD = re.compile(r"<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>", re.IGNORECASE | re.DOTALL)


class DefinitionListExtractor:
    source = ExtractionSource.DEFINITION_LIST

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        title = _page_title(page)
        for body in _DL.findall(page.html):
            pairs = _DT_DD.findall(body)
            if not pairs:
                continue
            f: dict[str, ExtractedField] = {}
            if title:
                f["title"] = known(
                    title[0], snippet=title[1], reason="page title for <dl>", confidence=0.5
                )
            joined = []
            for dt, dd in pairs:
                label, value = strip_tags(dt), dd
                joined.append(strip_tags(dd))
                role = _role_of(label)
                if role and role != "title" and role not in f:
                    ef = _field_for(
                        role, value, f"<dt>{label}</dt><dd>{strip_tags(dd)[:60]}</dd>", 0.6
                    )
                    if ef:
                        f[role] = ef
            enrich_from_text(f, " ".join(joined), base_url=page.url, conf=0.5, html=page.html)
            if f.get("title") or f.get("start_date"):
                events.append(RawEvent(self.source, f))
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} definition lists"
        )


# --------------------------------------------------------------------------- FAQ

_FAQ_QA = re.compile(
    r"<(?:summary|strong|b|h[2-6])\b[^>]*>\s*([^<]*\?)\s*</(?:summary|strong|b|h[2-6])>(.*?)"
    r"(?=<(?:summary|strong|b|h[2-6])\b|</details>|</div>|$)",
    re.IGNORECASE | re.DOTALL,
)


class FaqExtractor:
    source = ExtractionSource.FAQ

    def extract(self, page: Page) -> ExtractionResult:
        qas = _FAQ_QA.findall(page.html)
        if len(qas) < 2:
            return ExtractionResult(source=self.source, note="no FAQ block")
        f: dict[str, ExtractedField] = {}
        title = _page_title(page)
        if title:
            f["title"] = known(
                title[0], snippet=title[1], reason="page title for FAQ", confidence=0.5
            )
        answers = []
        for q, a in qas:
            role = _role_of(q)
            answers.append(strip_tags(a))
            if role and role != "title" and role not in f:
                ef = _field_for(
                    role,
                    a if role == "registration_url" else strip_tags(a),
                    f'Q:"{q.strip()[:40]}" A:"{strip_tags(a)[:50]}"',
                    0.55,
                )
                if ef:
                    f[role] = ef
        enrich_from_text(f, " ".join(answers), base_url=page.url, conf=0.5, html=page.html)
        if "registration_url" not in f:
            reg = find_registration_url(page.html, page.url)
            if reg:
                f["registration_url"] = known(
                    reg[0], snippet=reg[1], reason="FAQ registration link", confidence=0.5
                )
        events = [RawEvent(self.source, f)] if (f.get("title") and f.get("start_date")) else []
        return ExtractionResult(source=self.source, events=events, note=f"{len(qas)} FAQ pairs")
