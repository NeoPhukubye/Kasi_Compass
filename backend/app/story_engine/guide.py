"""
Companion Mode "Route Guide" — the opt-in tour-guide Q&A behind
POST /story-engine/ask.

Design, written down so it doesn't drift from the project's content
commitments:

- Grounded by default: with no GEMINI_API_KEY configured (the app's normal
  state), the guide answers strictly from the human-sourced corpus in
  content_store.py — matching the stop a question is *about* and composing
  its reviewed narrative, heritage sites, and stalls. No fabricated facts,
  because no model ever wrote the answer.
- Gemini is an assistive, opt-in upgrade, exactly like the offline
  translation tool: if a server-side key is configured, the question and the
  matching corpus context are sent to Gemini to draft a guide-style answer;
  the model's output is a *style* pass over real content. If the call fails
  for any reason (no key, no network, model error), the corpus answer is
  returned instead — the guide never hangs and never silently stops
  answering.
- The key stays server-side. `api.py` reads it from the environment, never
  from a client, so there is no key in browser JS to leak or be billed by
  anyone. This module uses only the Python standard library (urllib),
  mirroring tools/translate_stories.py — no SDK dependency, and nothing that
  touches the core /journey/* story path.

In short: the core story engine has no AI dependency (unchanged); this
module is an explicitly user-invoked, key-gated optional layer on top.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.story_engine.content_store import SHOSHOLOZA_ROUTE_STORIES, get_stop_content

# Gemini's public generateContent REST endpoint — called over plain HTTPS via
# stdlib only, keeping requirements.txt lean (same reason the translation
# tool uses urllib instead of the google-genai SDK).
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.6-flash"

# How a question maps to a stop in the corpus. Keys are the query words and
# name fragments users are likely to type; values are corpus stop ids.
_STOP_ALIASES: dict[str, str] = {
    "pretoria": "pretoria",
    "johannesburg": "johannesburg_park",
    "park station": "johannesburg_park",
    "jozi": "johannesburg_park",
    "germiston": "germiston",
    "kimberley": "kimberley",
    "big hole": "kimberley",
    "klerksdorp": "klerksdorp",
    "de aar": "de_aar",
    "deaar": "de_aar",
    "beaufort": "beaufort_west",
    "matjiesfontein": "matjiesfontein",
    "worcester": "worcester",
    "cape town": "cape_town",
}


def find_matching_stop(question: str) -> str | None:
    """Return the corpus stop id a question is about, or None if no stop is
    clearly mentioned. First alias match wins; idiosyncratic text simply
    falls through to the corridor overview."""
    lowered = question.lower()
    for alias, stop_id in _STOP_ALIASES.items():
        if alias in lowered:
            return stop_id
    return None


def _corpus_answer(question: str, stop_id: str | None) -> str:
    """Compose a grounded, sentence-style answer from human-reviewed
    content. No model, no invented facts."""
    if stop_id is None:
        return (
            "The Kasi Compass corridor runs from Pretoria to Cape Town, joining Johannesburg, "
            "Germiston, Klerksdorp, Kimberley, De Aar, Beaufort West, Matjiesfontein, and "
            "Worcester. Ask about any of these stops and the guide will share their "
            "human-reviewed history, heritage sites, and the local stalls around the station."
        )

    content = get_stop_content(stop_id)
    narrative = content["historical_narrative"].strip().rstrip(".")
    heritage = [site["name"] for site in content["heritage_sites"]]
    stalls = [stall["name"] for stall in content["local_stalls"]]

    if not SHOSHOLOZA_ROUTE_STORIES.get(stop_id):
        return (f"{content['stop_name']}: {narrative}.")

    lines = [f"{content['stop_name']}: {narrative}."]
    if heritage:
        lines.append(f"Heritage to see: {'; '.join(heritage)}.")
    if stalls:
        lines.append(f"Near the station: {'; '.join(stalls)}.")
    return " ".join(lines)


def _call_gemini(question: str, context: str, api_key: str, model: str) -> str:
    """One shot at Gemini for a guide-style answer to the user's question,
    grounded in the human-sourced context. Raises on any failure so the
    caller can fall back to the corpus answer."""
    payload = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "You are the Kasi Compass route guide for the Shosholoza rail corridor. "
                    "Answer the rider's question in 2-4 friendly sentences, grounded ONLY in "
                    "the provided context. Do not invent stations, dates, or facts outside it."
                ),
            }],
        },
        "contents": [{"parts": [{"text": f"Context:\n{context}\n\nQuestion: {question}"}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 300},
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))

    parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise ValueError("Gemini returned an empty answer")
    return text


def answer_question(
    question: str,
    language_code: str = "en",
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Answer a rider's guide question. Returns a dict with the answer, its
    provenance, and the stop it was matched to. `api_key` is read from the
    environment by the API layer — never from the client."""
    stop_id = find_matching_stop(question)
    fallback = _corpus_answer(question, stop_id)

    if not api_key:
        return {
            "answer": fallback,
            "source": "route-corpus",
            "ai_used": False,
            "stop_id": stop_id,
            "stop_name": get_stop_content(stop_id)["stop_name"] if stop_id else None,
        }

    try:
        context = _corpus_answer(question, stop_id)
        drafted = _call_gemini(question, context, api_key, model=model)
        return {
            "answer": drafted,
            "source": "gemini",
            "ai_used": True,
            "stop_id": stop_id,
            "stop_name": get_stop_content(stop_id)["stop_name"] if stop_id else None,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
        # Any Gemini failure degrades gracefully to the grounded corpus
        # answer — the guide keeps working with no key and no network.
        return {
            "answer": fallback,
            "source": "route-corpus",
            "ai_used": False,
            "stop_id": stop_id,
            "stop_name": get_stop_content(stop_id)["stop_name"] if stop_id else None,
            "ai_error": str(exc),
        }