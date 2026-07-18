"""Prompt templates for a FUTURE real LLM reasoner (Phase 8E) — not executed here.

8E ships `MockAIReasoner` (deterministic, no network). This is the exact contract a real Gemini/
OpenAI reasoner will be given: reason ONLY over the provided hydration summary + endpoints + HTML
excerpt, cite evidence for every claim, return UNKNOWN when the signals don't support a field, and
recommend a provider type. `build_reasoning_prompt` fills a page in; nothing here calls a model.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a discovery reasoner for a professional-tech-event platform. You are
given the machine-extracted signals from ONE web page (hydration/state blobs, discovered API
endpoints, the detected framework, and an HTML excerpt) — NOT the rendered page. Reason only over
these signals.

HARD RULES:
- NEVER fabricate. Every claim must be grounded in a provided signal; cite it as evidence.
- If a field (date, location, organizer, registration, recurring, community) is not supported by the
  signals, return "unknown" — do not guess.
- Do not instruct any action that logs in, authenticates, bypasses robots, executes JS, or calls an
  endpoint. Endpoints are recorded as leads, never invoked.
- Output valid JSON only, matching the requested schema."""

_REASONING_TEMPLATE = """Decide whether this page is an event source and could become a provider.

URL: {url}
FRAMEWORK: {framework}
HYDRATION SIGNALS:
{hydration}
DISCOVERED ENDPOINTS (leads only — never call them):
{endpoints}
HTML EXCERPT (truncated):
\"\"\"
{html}
\"\"\"

Return JSON: {{"is_event_source": bool, "confidence": 0..1, "recommended_provider_type": str,
"expected_events": int, "evidence": [str], "missing_fields": [str],
"answers": {{"is_event": bool, "recurring": str, "organizer": str, "location": str,
"registration_url": str, "technology": [str], "community": str, "can_be_provider": bool}}}}"""

_MAX_HTML = 6000


def build_reasoning_prompt(url, framework, hydration_lines, endpoint_lines, html) -> str:
    return _REASONING_TEMPLATE.format(
        url=url,
        framework=framework or "unknown",
        hydration="\n".join(hydration_lines) or "(none)",
        endpoints="\n".join(endpoint_lines) or "(none)",
        html=html[:_MAX_HTML],
    )
