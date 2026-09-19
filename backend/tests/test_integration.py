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


# ---------------------------------------------------------------------
# Live position sharing — end-to-end through the actual API, not just
# the store in isolation (see test_live_share.py for that).
# ---------------------------------------------------------------------

RIDER_A = "11111111-2222-3333-4444-555555555555"
RIDER_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_share_position_end_to_end_then_visible_to_other_rider():
    de_aar = get_waypoint("de_aar")
    share = client.post(
        "/journey/share-position",
        json={"rider_id": RIDER_A, "lat": de_aar.latitude, "lon": de_aar.longitude},
    )
    assert share.status_code == 200
    assert share.json()["active_riders"] >= 1

    seen_by_b = client.get("/journey/shared-positions", params={"rider_id": RIDER_B})
    assert seen_by_b.status_code == 200
    rider_ids = [p["rider_id"] for p in seen_by_b.json()]
    assert RIDER_A in rider_ids

    # A rider never sees their own position in the "other riders" list.
    seen_by_a = client.get("/journey/shared-positions", params={"rider_id": RIDER_A})
    rider_ids_for_a = [p["rider_id"] for p in seen_by_a.json()]
    assert RIDER_A not in rider_ids_for_a


def test_share_position_rejects_non_uuid_rider_id():
    response = client.post(
        "/journey/share-position",
        json={"rider_id": "not-a-uuid", "lat": -30.0, "lon": 24.0},
    )
    assert response.status_code == 422


def test_share_position_rejects_invalid_coordinates():
    response = client.post(
        "/journey/share-position",
        json={"rider_id": RIDER_A, "lat": 999.0, "lon": 24.0},
    )
    assert response.status_code == 422


def test_leave_endpoint_removes_rider_from_shared_positions():
    de_aar = get_waypoint("de_aar")
    client.post(
        "/journey/share-position",
        json={"rider_id": RIDER_A, "lat": de_aar.latitude, "lon": de_aar.longitude},
    )
    leave = client.post(
        "/journey/share-position/leave",
        json={"rider_id": RIDER_A, "lat": 0.0, "lon": 0.0},
    )
    assert leave.status_code == 204

    seen_by_b = client.get("/journey/shared-positions", params={"rider_id": RIDER_B})
    rider_ids = [p["rider_id"] for p in seen_by_b.json()]
    assert RIDER_A not in rider_ids
