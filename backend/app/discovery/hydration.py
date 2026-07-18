"""HydrationExtractor / NextDataParser / StateParser / EmbeddedJSONExtractor.

Extracts embedded hydration/state payloads from raw HTML and finds event-shaped objects inside
them — deterministically, without executing JavaScript. Payloads that are valid JSON are parsed;
JS assignments (window.__X__ = {...}) are best-effort; unparseable payloads (Nuxt2 functions,
RSC Flight) fall back to a deterministic text-signature count so nothing is silently missed.
"""

from __future__ import annotations

import json
import re

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_NUXT3_DATA = re.compile(
    r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_APP_JSON = re.compile(
    r'<script[^>]+type="application/json"[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_FLIGHT = re.compile(r'self\.__next_f\.push\(\[\d+,\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)

# event-shaped object detection
_NAME_KEYS = {"name", "title", "event_name", "eventname", "summary"}
_DATE_KEYS = {
    "start_date",
    "start_at",
    "startdate",
    "startdatetime",
    "start_time",
    "starttime",
    "start",
    "date",
    "datetime",
    "start_date_time",
}
_EVENT_SIG = re.compile(
    r'"(?:start_at|start_date|startDate|startTime|start_time|startDateTime)"\s*:', re.IGNORECASE
)


def extract_next_data(html: str) -> object | None:
    for pattern in (_NEXT_DATA, _NUXT3_DATA):
        m = pattern.search(html)
        if m:
            try:
                return json.loads(m.group(1))
            except ValueError:
                continue
    return None


def _balanced_after(text: str, start: int) -> str | None:
    """Return the balanced {…}/[…] literal beginning at index `start`, or None."""
    if start >= len(text) or text[start] not in "{[":
        return None
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(start, min(len(text), start + 2_000_000)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_window_state(html: str, var: str) -> object | None:
    """Best-effort parse of `window.<var> = {…}` (or a JSON string script)."""
    m = re.search(re.escape(f"window.{var}") + r"\s*=\s*", html)
    if not m:
        return None
    literal = _balanced_after(html, m.end())
    if literal is None:
        return None
    try:
        return json.loads(literal)
    except ValueError:
        return None


def extract_embedded_json(html: str) -> list[object]:
    """Every parseable <script type="application/json"> blob (excludes ld+json — D1 handles it)."""
    out: list[object] = []
    for block in _APP_JSON.findall(html):
        try:
            out.append(json.loads(block))
        except ValueError:
            continue
    return out


def extract_flight_strings(html: str) -> list[str]:
    """Decoded RSC Flight payload strings pushed via self.__next_f.push([...])."""
    out: list[str] = []
    for raw in _FLIGHT.findall(html):
        try:
            out.append(json.loads(f'"{raw}"'))
        except ValueError:
            out.append(raw)
    return out


def _looks_like_event(node: dict) -> bool:
    keys = {k.lower() for k in node}
    type_ = str(node.get("@type") or node.get("type") or "").lower()
    return (bool(keys & _NAME_KEYS) and bool(keys & _DATE_KEYS)) or type_ == "event"


def find_event_objects(obj: object) -> tuple[int, str | None]:
    """Recursively count event-shaped objects (bounded), returning (count, sample title)."""
    count, title, seen, stack = 0, None, 0, [obj]
    while stack and seen < 200_000:
        node = stack.pop()
        seen += 1
        if isinstance(node, dict):
            if _looks_like_event(node):
                count += 1
                if title is None:
                    for k in ("name", "title", "event_name", "summary"):
                        if isinstance(node.get(k), str):
                            title = node[k]
                            break
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return count, title


def count_event_signatures(text: str) -> int:
    """Deterministic text proxy for embedded events when a payload can't be parsed."""
    return len(_EVENT_SIG.findall(text))
