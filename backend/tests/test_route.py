"""
Unit tests for the route module — the ordered waypoint list and the
get_waypoint lookup helper that the rest of the story engine depends on.

Run with: pytest backend/tests/test_route.py
"""

from app.story_engine.route import (
    PRETORIA_TO_CAPE_TOWN,
    Waypoint,
    get_waypoint,
)


def test_get_waypoint_returns_known_waypoint():
    waypoint = get_waypoint("kimberley")
    assert isinstance(waypoint, Waypoint)
    assert waypoint.id == "kimberley"
    assert waypoint.name == "Kimberley"


def test_get_waypoint_returns_none_for_unknown_id():
    assert get_waypoint("does-not-exist") is None


def test_get_waypoint_returns_none_for_empty_string():
    assert get_waypoint("") is None


def test_waypoint_ids_are_unique():
    ids = [w.id for w in PRETORIA_TO_CAPE_TOWN]
    assert len(ids) == len(set(ids))


def test_waypoints_are_ordered_north_to_south():
    # The route runs Pretoria (north) to Cape Town (south), so latitude must
    # strictly decrease along the ordered list.
    latitudes = [w.latitude for w in PRETORIA_TO_CAPE_TOWN]
    assert latitudes == sorted(latitudes, reverse=True)
