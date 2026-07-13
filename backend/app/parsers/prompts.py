"""Prompt construction for the Gemini query parser.

Isolated here so prompt wording can evolve without touching the parser logic. The
instructions constrain Gemini to pure query understanding: it never searches the
web and never invents events.
"""

from __future__ import annotations

from datetime import date

from app.models.event import EventCategory

_CATEGORIES = ", ".join(c.value for c in EventCategory)


def build_prompt(user_query: str, today: date) -> str:
    return f"""You are the query-understanding component of a SEARCH application for \
professional and technology events in India (workshops, meetups, conferences, \
hackathons, startup events, AI events, webinars).

Your ONLY job is to convert the user's natural-language query into a structured JSON \
search filter. You do NOT search the web. You do NOT invent, list, or describe any \
events. You only extract search parameters.

Today's date is {today.isoformat()}. Resolve any relative dates against it.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly these keys:
- "keywords": array of topical keyword strings (e.g. ["machine learning"]). [] if none.
- "city": Indian city name in common English spelling (e.g. "Bangalore", not \
"Bengaluru"). null if no city is mentioned.
- "categories": array; a subset of [{_CATEGORIES}]. Include a category only if the \
user clearly implies it. [] if unclear.
- "date_from": earliest date as "YYYY-MM-DD", or null.
- "date_to": latest date as "YYYY-MM-DD", or null.
- "free_only": true only if the user asks for free events, otherwise false.

Relative-date guidance (relative to today):
- "this weekend" -> the upcoming Saturday through Sunday.
- "next week" -> Monday through Sunday of next week.
- "next month" -> the first through the last day of next month.
If no timeframe is mentioned, use null for both date fields.

User query: {user_query!r}
JSON:"""


def build_corrective_prompt(user_query: str, previous: str, error: str, today: date) -> str:
    return f"""{build_prompt(user_query, today)}

Your previous response was INVALID and could not be parsed into the required schema.

Previous response:
{previous}

Validation error:
{error}

Return ONLY corrected, valid JSON that matches the schema exactly."""
