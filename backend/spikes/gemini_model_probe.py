"""Diagnostic: what can this Gemini key actually reach? (spike, not production)"""

from __future__ import annotations

from google import genai

from app.config import get_settings

settings = get_settings()
client = genai.Client(api_key=settings.gemini_api_key)

print("--- models supporting generateContent (first 20) ---")
try:
    names = [
        m.name
        for m in client.models.list()
        if "generateContent" in (getattr(m, "supported_actions", None) or [])
    ]
    for n in names[:20]:
        print("   ", n)
    print(f"   (total: {len(names)})")
except Exception as exc:  # noqa: BLE001
    print("   list failed:", type(exc).__name__, str(exc)[:200])

print("\n--- single-call probe per candidate model ---")
for model in [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]:
    try:
        r = client.models.generate_content(
            model=model,
            contents='Return the JSON {"ok": true} and nothing else.',
            config={"response_mime_type": "application/json"},
        )
        print(f"   {model}: OK -> {(r.text or '').strip()[:60]!r}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        code = "429" if "RESOURCE_EXHAUSTED" in msg else msg[:40]
        print(f"   {model}: FAIL -> {type(exc).__name__} {code}")
