"""
Unit tests for the content_store module — the human-reviewed story lookup
and point-of-interest accessors that api.py serves to riders.

Run with: pytest backend/tests/test_content_store.py
"""

from app.story_engine.content_store import (
    PointOfInterest,
    get_pois,
    get_story,
)


def test_get_story_returns_english_story_for_known_waypoint():
    story = get_story("kimberley", language_code="en")
    assert story is not None
    assert story.language_code == "en"
    assert story.text


def test_get_story_falls_back_to_english_for_unknown_language():
    # Only "en" exists in seed content, so any other language must fall back
    # to the English entry rather than returning None.
    story = get_story("kimberley", language_code="zu")
    assert story is not None
    assert story.language_code == "en"


def test_get_story_returns_none_for_unknown_waypoint():
    assert get_story("does-not-exist") is None


def test_get_pois_returns_list_for_known_waypoint():
    pois = get_pois("kimberley")
    assert isinstance(pois, list)
    assert pois
    assert all(isinstance(p, PointOfInterest) for p in pois)


def test_get_pois_returns_empty_list_for_unknown_waypoint():
    assert get_pois("does-not-exist") == []
