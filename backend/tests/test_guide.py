"""
Unit tests for app.story_engine.guide — the opt-in Route Guide behind
POST /story-engine/ask.

The core guarantees tested here:
  1. The guide matches a stop from free-text questions using corpus aliases.
  2. With no Gemini key (the app's normal state) it answers *only* from the
     human-reviewed corpus — nothing invented.
  3. With a key, a Gemini draft is used only when it succeeds; any failure
     (network, model, empty answer) degrades to the corpus answer.
Run with: pytest backend/tests/test_guide.py
"""

import pytest

from app.story_engine import guide


def test_find_matching_stop_matches_by_alias():
    assert guide.find_matching_stop("What happened near the Big Hole?") == "kimberley"
    assert guide.find_matching_stop("tell me about Cape Town station") == "cape_town"
    assert guide.find_matching_stop("jozi food stalls") == "johannesburg_park"


def test_find_matching_stop_returns_none_for_unrelated_question():
    assert guide.find_matching_stop("what is the best curry recipe?") is None
    assert guide.find_matching_stop("") is None


def test_corpus_answer_is_grounded_for_a_known_stop():
    answer = guide._corpus_answer("kimberley history", "kimberley")
    assert "Kimberley Station" in answer
    assert "Big Hole" in answer
    assert "Platform Craft Markets" in answer


def test_corpus_answer_gives_route_overview_for_unknown_stop():
    answer = guide._corpus_answer("anything", None)
    assert "Pretoria" in answer
    assert "Cape Town" in answer
    assert "Kimberley" in answer


def test_answer_without_key_is_purely_corpus():
    result = guide.answer_question("What happened at kimberley?", api_key=None)
    assert result["ai_used"] is False
    assert result["source"] == "route-corpus"
    assert result["stop_id"] == "kimberley"
    assert "Big Hole" in result["answer"]


def test_answer_with_key_uses_gemini_draft(monkeypatch):
    monkeypatch.setattr(
        guide, "_call_gemini",
        lambda question, context, api_key, model: "Kimberley's diamond rush shaped the town.",
    )
    result = guide.answer_question("What happened at kimberley?", api_key="FAKE-KEY")
    assert result["ai_used"] is True
    assert result["source"] == "gemini"
    assert "diamond rush" in result["answer"]


@pytest.mark.parametrize(
    "exc",
    [guide.urllib.error.URLError("no network"), ValueError("Gemini returned an empty answer")],
)
def test_answer_falls_back_to_corpus_when_gemini_fails(monkeypatch, exc):
    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(guide, "_call_gemini", boom)
    result = guide.answer_question("What happened at kimberley?", api_key="FAKE-KEY")
    assert result["ai_used"] is False
    assert result["source"] == "route-corpus"
    assert "Big Hole" in result["answer"]