"""Structured extractors (Phase 10B) — JSON-LD, OpenGraph, Microdata.

The strongest signals: schema.org/Event JSON-LD (full field set), OpenGraph meta (page-level, often
an event landing page), and inline microdata (`itemtype=schema.org/Event`). Each is isolated and
returns provenance-bearing `RawEvent`s. JSON-LD/microdata are high-confidence structured; OpenGraph
is medium (it describes the page, which *may* be an event) and is enriched from its own text.
"""

from __future__ import annotations

import json
import re

from app.universal.extractors.base import enrich_from_text
from app.universal.models import ExtractedField, ExtractionResult, ExtractionSource, Page, RawEvent
from app.universal.provenance import inferred, known
from app.universal.text_utils import find_date

_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'(property|name|content)\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _first_str(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    if isinstance(value, dict):
        return value.get("name") or value.get("url")
    return None


def _walk_events(node, out: list[dict]) -> None:
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            t = cur.get("@type")
            if (
                t == "Event"
                or (isinstance(t, str) and t.endswith("Event"))
                or (isinstance(t, list) and any(str(x).endswith("Event") for x in t))
            ):
                out.append(cur)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def _event_from_ld(node: dict) -> RawEvent:
    f: dict[str, ExtractedField] = {}
    snip = json.dumps(node)[:200]

    def put(name, value, reason, conf=0.9, inf=False):
        if value in (None, "", []):
            return
        f[name] = (inferred if inf else known)(value, snippet=snip, reason=reason, confidence=conf)

    put("title", _first_str(node.get("name")), "JSON-LD Event.name")
    put("description", _first_str(node.get("description")), "JSON-LD Event.description", 0.8)
    put("start_date", _first_str(node.get("startDate")), "JSON-LD Event.startDate")
    put("end_date", _first_str(node.get("endDate")), "JSON-LD Event.endDate")
    put("registration_url", _first_str(node.get("url")), "JSON-LD Event.url", 0.7)

    loc = node.get("location")
    if isinstance(loc, dict):
        put("venue", _first_str(loc.get("name")), "JSON-LD location.name", 0.85)
        addr = loc.get("address")
        if isinstance(addr, dict):
            put("city", addr.get("addressLocality"), "JSON-LD address.addressLocality")
            put("state", addr.get("addressRegion"), "JSON-LD address.addressRegion", 0.85)
            put("country", addr.get("addressCountry"), "JSON-LD address.addressCountry", 0.85)
        if str(loc.get("@type", "")).lower() == "virtuallocation":
            put("mode", "online", "JSON-LD VirtualLocation", 0.9, inf=True)
    elif isinstance(loc, str):
        put("venue", loc, "JSON-LD location string", 0.7)

    mode = str(node.get("eventAttendanceMode", "")).lower()
    if "online" in mode:
        put("mode", "online", "JSON-LD eventAttendanceMode", 0.85, inf=True)
    elif "offline" in mode:
        put("mode", "offline", "JSON-LD eventAttendanceMode", 0.85, inf=True)

    org = node.get("organizer")
    put("organizer", _first_str(org), "JSON-LD Event.organizer", 0.85)

    offers = node.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        if price in (0, "0", "0.00"):
            put("fee", "Free", "JSON-LD offers.price=0", 0.85, inf=True)
        elif price:
            put("fee", str(price), "JSON-LD offers.price", 0.85)
        put("registration_url", _first_str(offers.get("url")), "JSON-LD offers.url", 0.75)

    perf = node.get("performer")
    speakers = [_first_str(p) for p in perf] if isinstance(perf, list) else [_first_str(perf)]
    speakers = [s for s in speakers if s]
    if speakers:
        put("speakers", speakers, "JSON-LD Event.performer", 0.8)

    img = node.get("image")
    imgs = img if isinstance(img, list) else ([img] if img else [])
    imgs = [i for i in imgs if isinstance(i, str)]
    if imgs:
        put("images", imgs, "JSON-LD Event.image", 0.7)

    return RawEvent(source=ExtractionSource.JSONLD, fields=f)


class JsonLdExtractor:
    source = ExtractionSource.JSONLD

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for block in _LD_BLOCK.findall(page.html):
            try:
                data = json.loads(block)
            except ValueError:
                continue
            nodes: list[dict] = []
            _walk_events(data, nodes)
            for node in nodes:
                ev = _event_from_ld(node)
                if ev.fields:
                    events.append(ev)
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} ld+json events"
        )


class OpenGraphExtractor:
    source = ExtractionSource.OPENGRAPH

    def extract(self, page: Page) -> ExtractionResult:
        og: dict[str, str] = {}
        for tag in _META.findall(page.html):
            attrs = {k.lower(): v for k, v in _ATTR.findall(tag)}
            key = attrs.get("property") or attrs.get("name")
            content = attrs.get("content")
            if key and content:
                og[key.lower()] = content
        title = og.get("og:title")
        if not title:
            return ExtractionResult(source=self.source, note="no og:title")
        f: dict[str, ExtractedField] = {
            "title": known(
                title, snippet=f'og:title="{title}"', reason="OpenGraph og:title", confidence=0.55
            )
        }
        if og.get("og:description"):
            f["description"] = known(
                og["og:description"][:400],
                snippet="og:description",
                reason="OpenGraph og:description",
                confidence=0.5,
            )
        if og.get("og:site_name"):
            f["organizer"] = inferred(
                og["og:site_name"],
                snippet=f'og:site_name="{og["og:site_name"]}"',
                reason="OpenGraph og:site_name",
                confidence=0.4,
            )
        if og.get("og:image"):
            f["images"] = known(
                [og["og:image"]], snippet="og:image", reason="OpenGraph og:image", confidence=0.5
            )
        for k in ("event:start_time", "article:published_time"):
            if og.get(k):
                f["start_date"] = known(
                    og[k][:10], snippet=f"{k}={og[k]}", reason=f"OpenGraph {k}", confidence=0.5
                )
                break
        text = f"{title}. {og.get('og:description', '')}"
        enrich_from_text(f, text, base_url=page.url, conf=0.45, html=page.html)
        return ExtractionResult(
            source=self.source, events=[RawEvent(self.source, f)], note="og event"
        )


_ITEM = re.compile(
    r'itemscope[^>]*itemtype=["\'][^"\']*schema\.org/Event["\'](.*?)(?=itemscope|</body>|$)',
    re.IGNORECASE | re.DOTALL,
)
# capture the whole opening tag so content=/datetime= are found regardless of attribute order
_PROP = re.compile(r'<\w+\b([^>]*\bitemprop=["\'](\w+)["\'][^>]*)>([^<]*)', re.IGNORECASE)
_ATTR_VAL = re.compile(r'(?:content|datetime)=["\']([^"\']*)["\']', re.IGNORECASE)


def _date_val(raw: str) -> str:
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    d = find_date(raw)
    return d[0] if d else raw[:10]


class MicrodataExtractor:
    source = ExtractionSource.MICRODATA

    def extract(self, page: Page) -> ExtractionResult:
        events: list[RawEvent] = []
        for body in _ITEM.findall(page.html):
            props: dict[str, str] = {}
            for attrs, name, inner in _PROP.findall(body):
                m = _ATTR_VAL.search(attrs)
                val = ((m.group(1) if m else "") or inner or "").strip()
                if name and val and name.lower() not in props:
                    props[name.lower()] = val
            if not props:
                continue
            f: dict[str, ExtractedField] = {}
            snip = "microdata itemtype=schema.org/Event"
            if props.get("name"):
                f["title"] = known(
                    props["name"], snippet=snip, reason="microdata itemprop=name", confidence=0.8
                )
            if props.get("startdate"):
                f["start_date"] = known(
                    _date_val(props["startdate"]),
                    snippet=snip,
                    reason="microdata startDate",
                    confidence=0.8,
                )
            if props.get("enddate"):
                f["end_date"] = known(
                    _date_val(props["enddate"]),
                    snippet=snip,
                    reason="microdata endDate",
                    confidence=0.8,
                )
            if props.get("location"):
                f["venue"] = known(
                    props["location"], snippet=snip, reason="microdata location", confidence=0.75
                )
            if props.get("organizer"):
                f["organizer"] = known(
                    props["organizer"], snippet=snip, reason="microdata organizer", confidence=0.75
                )
            if f:
                enrich_from_text(f, " ".join(props.values()), base_url=page.url, conf=0.6)
                events.append(RawEvent(self.source, f))
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} microdata events"
        )
