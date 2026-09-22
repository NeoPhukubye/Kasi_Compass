"""
Offline translation drafting tool — the ONE place AI is allowed in this project.

See README.md §"Content model: human-sourced first, AI assistive only" and the
module docstring in app/story_engine/content_store.py. Gemini's only permitted
role is drafting a *first-pass* translation of an already human-approved English
story into another official South African language. A human reviewer (ideally a
first-language speaker) then edits and approves that draft before it is ever
published to riders.

Crucially, this tool is NOT imported by the running service. Nothing in the
FastAPI request path (`app/story_engine/api.py`) touches Gemini, so the app
behaves identically with or without an API key — the core TRL 4 claim that the
runtime has no AI dependency.

Deliberately two-step, so AI output can never reach a rider unreviewed:

    # 1. Draft (calls Gemini; writes JSON to translation_drafts/, NOT the store)
    python3 tools/translate_stories.py draft --waypoint kimberley --language zu

    # 2. After a human edits and approves the draft, bake it into the store
    python3 tools/translate_stories.py apply --draft translation_drafts/kimberley.zu.json \
        --reviewed-by "Sipho N., first-language Zulu reviewer"

`apply` refuses to run unless the draft was explicitly marked reviewed and a
reviewer name that does not look AI-generated is supplied. That is the guard
that keeps the `reviewed_by` field honest and keeps
tests/test_integration.py::test_position_at_kimberley_triggers_human_reviewed_story
(a test that asserts "AI" never appears in a story) passing.

Usage:
    python3 tools/translate_stories.py draft [--waypoint ID] [--language CODE ...]
    python3 tools/translate_stories.py apply --draft FILE --reviewed-by "Name, role"
    python3 tools/translate_stories.py list
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Allow running as a plain script from backend/: make the app package importable.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.story_engine.content_store import STORY_CONTENT  # noqa: E402

DRAFTS_DIR = Path(__file__).resolve().parent / "translation_drafts"

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

LANGUAGE_NAMES = {
    "en": "English",
    "zu": "isiZulu",
    "xh": "isiXhosa",
    "af": "Afrikaans",
    "nso": "Sepedi",
    "tn": "Setswana",
    "st": "Sesotho",
    "ts": "Xitsonga",
    "ss": "siSwati",
    "ve": "Tshivenda",
    "nr": "isiNdebele",
}

# Phrases that betray an AI attribution slipping into the `reviewed_by` field.
# The integration test asserts "AI" never appears in a story's source, so this
# is enforced here rather than only discovered at test time.
AI_MARKERS = ("ai", "gpt", "gemini", "chatgpt", "llm", "bot", "machine", "auto-generated")


class TranslationError(RuntimeError):
    """Raised for any recoverable failure in the drafting pipeline."""


def _load_env_file(path: Path) -> None:
    """Minimal .env loader so the tool needs no extra dependency.

    Real environment variables always win, so this never clobbers a value the
    shell or CI already set.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_api_key() -> str:
    _load_env_file(BACKEND_ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise TranslationError(
            "GEMINI_API_KEY is not set.\n"
            f"Copy {BACKEND_ROOT / '.env.example'} to {BACKEND_ROOT / '.env'} and add your key.\n"
            "Note: the running app does not need this — only this offline tool does."
        )
    return key


def _build_prompt(english_text: str, target_language_code: str) -> str:
    language_name = LANGUAGE_NAMES.get(target_language_code, target_language_code)
    return (
        f"You are drafting a first-pass {language_name} translation of a short "
        "heritage/travel story for a South African train-journey app.\n\n"
        "Requirements:\n"
        f"- Translate into {language_name} ({target_language_code}).\n"
        "- Preserve the factual content exactly: place names, dates, and figures "
        "must stay accurate. Do not add, invent, or embellish any fact.\n"
        "- Keep the register warm and storytelling, suitable for a traveller "
        "reading it as their train passes the place.\n"
        "- Return ONLY the translated text. No preamble, no notes, no quotes, "
        "no markdown.\n\n"
        f"English source:\n{english_text}"
    )


def _call_gemini(prompt: str, api_key: str, model: str, timeout: int = 60) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise TranslationError(f"Gemini API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TranslationError(f"Could not reach the Gemini API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise TranslationError("Gemini API returned a non-JSON response.") from exc

    candidates = body.get("candidates") or []
    if not candidates:
        blocked = (body.get("promptFeedback") or {}).get("blockReason")
        raise TranslationError(
            f"Gemini returned no candidates{f' (blocked: {blocked})' if blocked else ''}."
        )

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise TranslationError("Gemini returned an empty translation.")
    return text


def draft_one(waypoint_id: str, language_code: str, api_key: str, model: str) -> Path:
    """Draft one translation and write it to translation_drafts/ for review.

    Writes a DRAFT only — this never modifies content_store.py.
    """
    entry = STORY_CONTENT.get(waypoint_id)
    if entry is None:
        raise TranslationError(f"No story exists for waypoint '{waypoint_id}'.")
    if language_code == "en":
        raise TranslationError("English is the source language — nothing to translate.")
    if language_code in entry.localized:
        raise TranslationError(
            f"'{waypoint_id}' already has a '{language_code}' story "
            f"(reviewed by {entry.localized[language_code].reviewed_by}). "
            "Delete it from content_store.py first if you intend to replace it."
        )

    source = entry.localized.get("en")
    if source is None:
        raise TranslationError(f"'{waypoint_id}' has no English source text to translate.")

    translated = _call_gemini(_build_prompt(source.text, language_code), api_key, model)

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft_path = DRAFTS_DIR / f"{waypoint_id}.{language_code}.json"
    draft_path.write_text(
        json.dumps(
            {
                "waypoint_id": waypoint_id,
                "language_code": language_code,
                "model": model,
                "original_en": source.text,
                "draft_text": translated,
                "reviewed": False,
                "reviewed_by": None,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return draft_path


def _reject_ai_reviewer(reviewer: str) -> None:
    lowered = reviewer.lower()
    if any(marker in lowered for marker in AI_MARKERS):
        raise TranslationError(
            f"reviewed_by {reviewer!r} looks AI-generated. A human reviewer's name is "
            "required — see README §'Content model: human-sourced first, AI assistive only'."
        )


def apply_draft(draft_path: Path, reviewer: str) -> str:
    """Print the approval-ready snippet for a reviewed draft.

    This intentionally does NOT rewrite content_store.py. That file is the
    human-reviewed corpus and is kept under version control by hand, so the tool
    hands over a ready-to-paste block and the reviewer commits it themselves —
    keeping a human in the loop for the final step, as the design requires.
    """
    if not draft_path.exists():
        raise TranslationError(f"Draft not found: {draft_path}")

    _reject_ai_reviewer(reviewer)

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    waypoint_id = draft["waypoint_id"]
    language_code = draft["language_code"]
    text = draft["draft_text"]

    if draft.get("reviewed") is not True:
        raise TranslationError(
            f"{draft_path} is still marked unreviewed. A human must edit the draft, "
            'set "reviewed": true, then re-run apply.'
        )

    return (
        f'            "{language_code}": LocalizedStory(\n'
        f'                language_code="{language_code}",\n'
        f'                text=(\n'
        f'                    {text!r}\n'
        f'                ),\n'
        f'                reviewed_by="{reviewer}",\n'
        f'            ),\n'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Draft first-pass Gemini translations for human review (offline tool)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draft_cmd = sub.add_parser("draft", help="Draft translations for one or more waypoints.")
    draft_cmd.add_argument("--waypoint", help="Waypoint id, e.g. kimberley. Omit for all.")
    draft_cmd.add_argument(
        "--language",
        action="append",
        help="Target language code, e.g. zu. Repeatable. Defaults to TRANSLATION_TARGET_LANGUAGES.",
    )

    apply_cmd = sub.add_parser("apply", help="Print the store snippet for a reviewed draft.")
    apply_cmd.add_argument("--draft", required=True, type=Path)
    apply_cmd.add_argument("--reviewed-by", required=True, dest="reviewed_by")

    sub.add_parser("list", help="List which waypoints have which languages.")

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for waypoint_id, entry in STORY_CONTENT.items():
                langs = ", ".join(sorted(entry.localized)) or "none"
                print(f"{waypoint_id:20s} {langs}")
            return 0

        if args.command == "draft":
            _load_env_file(BACKEND_ROOT / ".env")
            api_key = _get_api_key()
            model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()

            waypoint_ids = [args.waypoint] if args.waypoint else list(STORY_CONTENT)
            languages = args.language or [
                code.strip()
                for code in os.environ.get("TRANSLATION_TARGET_LANGUAGES", "zu,af,xh").split(",")
                if code.strip()
            ]

            failures = 0
            for waypoint_id in waypoint_ids:
                for language_code in languages:
                    try:
                        path = draft_one(waypoint_id, language_code, api_key, model)
                        print(f"drafted  {waypoint_id}.{language_code}  ->  {path}")
                    except TranslationError as exc:
                        failures += 1
                        print(f"skipped  {waypoint_id}.{language_code}: {exc}", file=sys.stderr)

            print(
                "\nDrafts are UNREVIEWED. Have a first-language speaker edit each one, "
                'set "reviewed": true, then run: apply --draft <file> --reviewed-by "Name, role"'
            )
            # Non-zero only if every single attempt failed; partial skips (e.g. a
            # language that already exists) are expected and not a tool failure.
            return 1 if failures == len(waypoint_ids) * len(languages) else 0

        if args.command == "apply":
            print(apply_draft(args.draft, args.reviewed_by))
            print(
                "\nPaste the block above into the correct waypoint's `localized` dict in "
                "app/story_engine/content_store.py, then run the test suite."
            )
            return 0

    except TranslationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
