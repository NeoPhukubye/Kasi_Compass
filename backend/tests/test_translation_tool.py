"""
Tests for the offline translation tool — specifically the guardrails that keep
AI output from ever reaching a rider unreviewed.

These tests never call the Gemini API. They verify the *policy* the tool
enforces, which is the part that matters for the project's stated design
(README §"Content model: human-sourced first, AI assistive only"):

  1. The running service imports nothing from the translation tool, so an
     AI outage cannot affect the request path.
  2. A draft can't be applied until a human marks it reviewed.
  3. An AI-looking reviewer name is rejected.
  4. Drafting writes to a drafts folder, never into content_store.py.

Run with: pytest backend/tests/test_translation_tool.py
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = BACKEND_ROOT / "tools"
TOOL_PATH = TOOLS_DIR / "translate_stories.py"
API_PATH = BACKEND_ROOT / "app" / "story_engine" / "api.py"


def _load_tool():
    """Import the tool module by path (it lives outside the app package)."""
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    spec = importlib.util.spec_from_file_location("translate_stories", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def test_runtime_api_does_not_import_the_ai_tool():
    """
    The TRL 4 claim is that nothing in the request path depends on an AI
    service. If api.py ever imported the translation tool, that claim would
    be false — so assert it structurally rather than trusting a comment.
    """
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any("translate_stories" in name for name in imported), (
        f"api.py must not import the AI translation tool; found: {imported}"
    )
    assert not any("google" in name.lower() for name in imported), (
        f"api.py must not import a Google/AI SDK; found: {imported}"
    )


def test_tool_does_not_import_google_sdk_at_module_level():
    """
    The tool talks to Gemini over plain HTTP (urllib) so it adds no dependency
    to requirements.txt and cannot break the lean runtime install on Render.
    """
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(
        name.startswith(("google", "openai", "anthropic")) for name in imported
    ), f"tool should use stdlib HTTP, not a vendor SDK; found: {imported}"


def test_missing_api_key_raises_a_helpful_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(tool, "_load_env_file", lambda _path: None)

    with pytest.raises(tool.TranslationError) as excinfo:
        tool._get_api_key()

    message = str(excinfo.value)
    assert "GEMINI_API_KEY" in message
    # The app must keep working without a key — say so in the error itself.
    assert "does not need this" in message


def test_ai_reviewer_names_are_rejected():
    for bad in [
        "Gemini",
        "GPT-4",
        "AI generated",
        "ChatGPT draft",
        "translated by AI",
        "auto-generated",
    ]:
        with pytest.raises(tool.TranslationError):
            tool._reject_ai_reviewer(bad)


def test_human_reviewer_name_is_accepted():
    tool._reject_ai_reviewer("Sipho Ndlovu, first-language Zulu reviewer")


def test_apply_refuses_unreviewed_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "DRAFTS_DIR", tmp_path)
    draft = tmp_path / "kimberley.zu.json"
    draft.write_text(
        json.dumps(
            {
                "waypoint_id": "kimberley",
                "language_code": "zu",
                "draft_text": "Isihloko sendaba...",
                "reviewed": False,
                "reviewed_by": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(tool.TranslationError) as excinfo:
        tool.apply_draft(draft, "Sipho Ndlovu, first-language Zulu reviewer")
    assert "unreviewed" in str(excinfo.value)


def test_apply_refuses_ai_reviewer_even_on_reviewed_draft(tmp_path):
    draft = tmp_path / "kimberley.zu.json"
    draft.write_text(
        json.dumps(
            {
                "waypoint_id": "kimberley",
                "language_code": "zu",
                "draft_text": "Isihloko sendaba...",
                "reviewed": True,
                "reviewed_by": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(tool.TranslationError):
        tool.apply_draft(draft, "Gemini")


def test_apply_accepts_a_reviewed_draft_and_marks_the_human(tmp_path):
    draft = tmp_path / "kimberley.zu.json"
    draft.write_text(
        json.dumps(
            {
                "waypoint_id": "kimberley",
                "language_code": "zu",
                "draft_text": "Ngo-1871, ukutholakala kwedayimane...",
                "reviewed": True,
                "reviewed_by": None,
            }
        ),
        encoding="utf-8",
    )

    suffix = tool.apply_draft(draft, "Sipho Ndlovu, first-language Zulu reviewer")
    assert 'language_code="zu"' in suffix
    assert "Sipho Ndlovu" in suffix
    # The critical guarantee: no AI attribution leaks into the store snippet.
    assert "AI" not in suffix.replace("first-language", "")
    assert "Gemini" not in suffix


def test_drafting_never_writes_to_content_store(monkeypatch, tmp_path):
    """
    drafting must only ever produce a file under translation_drafts/. If it
    touched content_store.py, unreviewed AI text could reach riders.
    """
    monkeypatch.setattr(tool, "DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(tool, "_call_gemini", lambda *a, **k: "Ithransleyishini")

    path = tool.draft_one("kimberley", "af", api_key="fake", model="gemini-2.0-flash")

    assert path.parent == tmp_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["reviewed"] is False
    assert payload["reviewed_by"] is None
    assert payload["draft_text"] == "Ithransleyishini"
    # Source text is retained so a reviewer can check accuracy.
    assert payload["original_en"]


def test_drafting_skips_a_language_that_already_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(tool, "DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(tool, "_call_gemini", lambda *a, **k: "should not be called")

    with pytest.raises(tool.TranslationError) as excinfo:
        # kimberley already has an English source; en is the source language.
        tool.draft_one("kimberley", "en", api_key="fake", model="gemini-2.0-flash")
    assert "source language" in str(excinfo.value)


def test_drafting_unknown_waypoint_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(tool, "DRAFTS_DIR", tmp_path)

    with pytest.raises(tool.TranslationError):
        tool.draft_one("narnia", "zu", api_key="fake", model="gemini-2.0-flash")


def test_stories_only_record_human_reviewers():
    """
    Whatever the tool drafts, the shipped corpus must never carry an AI
    attribution — the same invariant test_integration.py checks through the API.
    """
    from app.story_engine.content_store import STORY_CONTENT

    for waypoint_id, entry in STORY_CONTENT.items():
        for language_code, story in entry.localized.items():
            assert "AI" not in story.reviewed_by.replace("awaiting", ""), (
                f"{waypoint_id}/{language_code} has an AI attribution in reviewed_by"
            )
