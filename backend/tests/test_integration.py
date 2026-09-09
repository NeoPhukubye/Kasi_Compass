"""
Integration test for the journey API.

Unlike test_story_engine.py (which tests each component in isolation —
the TRL 3 evidence), this test drives the actual FastAPI app end-to-end:
HTTP request in, geofence + content lookup happen for real inside the
running app, JSON response out. This is the evidence for the TRL 4 claim
in README.md — components integrated and validated together, not just
individually correct.

Run with: pytest backend/tests/test_integration.py
"""

from fastapi.testclient import TestClient

from app.story_engine.api import app
from app.story_engine.route import get_waypoint

client = TestClient(app)


def test_route_endpoint_returns_all_waypoints_in_order():
    response = client.get("/journey/route")
    assert response.status_code == 200
    body = response.json()
    assert [w["id"] for w in body] == [
        "pretoria",
        "johannesburg_park",
        "kimberley",
        "de_aar",
        "beaufort_west",
        "matjiesfontein",
        "worcester",
        "cape_town",
    ]


def test_position_at_kimberley_triggers_human_reviewed_story():
    kimberley = get_waypoint("kimberley")
    response = client.get(
        "/journey/position", params={"lat": kimberley.latitude, "lon": kimberley.longitude}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["triggered"] is True
    assert body["waypoint_id"] == "kimberley"
    assert body["story_text"] is not None
    assert "Big Hole" in body["story_text"]
    # Every story must carry a human reviewer, not an AI attribution.
    assert body["story_source"] is not None
    assert "AI" not in body["story_source"]


def test_position_far_from_route_does_not_trigger():
    response = client.get("/journey/position", params={"lat": -30.0, "lon": 0.0})
    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] is False
    assert body["waypoint_id"] is None


def test_position_at_waypoint_without_seeded_story_still_triggers_without_error():
    # de_aar is a real waypoint but has no seeded story yet (see content_store.py) -
    # the API should still report the trigger cleanly, with story_text as None,
    # rather than erroring out. This matters because story coverage will grow
    # incrementally (see consumer-phasing plan) and the app must not break on
    # waypoints that haven't been storied yet.
    de_aar = get_waypoint("de_aar")
    response = client.get(
        "/journey/position", params={"lat": de_aar.latitude, "lon": de_aar.longitude}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] is True
    assert body["waypoint_id"] == "de_aar"
    assert body["story_text"] is None


def test_route_progress_fraction_present_on_every_response():
    pretoria = get_waypoint("pretoria")
    response = client.get(
        "/journey/position", params={"lat": pretoria.latitude, "lon": pretoria.longitude}
    )
    body = response.json()
    assert body["route_progress_fraction"] == 0.0
