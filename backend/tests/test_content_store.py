"""
Unit tests for the content_store module — the human-reviewed story lookup
and point-of-interest accessors that api.py serves to riders.

Run with: pytest backend/tests/test_content_store.py
"""

from app.story_engine.content_store import (
    PointOfInterest,
    SHOSHOLOZA_ROUTE_STORIES,
    get_pois,
    get_stop_content,
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


def test_get_stop_content_returns_narrative_sites_stalls_and_coordinates():
    content = get_stop_content("kimberley")
    assert content["stop_name"] == "Kimberley Station"
    assert "diamond" in content["historical_narrative"].lower()
    assert any(s["name"] == "Kimberley Big Hole" for s in content["heritage_sites"])
    assert content["local_stalls"]
    # Coordinates come from the route so the geofence has real data.
    assert content["lat"] == -28.7353
    assert content["lon"] == 24.7697


def test_get_stop_content_falls_back_to_generic_profile_for_unknown_stop():
    content = get_stop_content("nonexistent-stop")
    assert content["stop_name"] == "Shosholoza Corridor Stop"
    assert content["heritage_sites"] == []
    assert content["local_stalls"] == []
    assert content["lat"] is None
    assert content["lon"] is None


def test_stop_discovery_corpus_covers_every_route_waypoint():
    from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

    route_ids = {w.id for w in PRETORIA_TO_CAPE_TOWN}
    assert route_ids.issubset(SHOSHOLOZA_ROUTE_STORIES)
    # Extra corridor stops carry explicit coordinates so geofencing works.
    assert "germiston" in SHOSHOLOZA_ROUTE_STORIES
    assert "klerksdorp" in SHOSHOLOZA_ROUTE_STORIES
