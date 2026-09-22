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

import pytest

from app.story_engine.api import app
from app.story_engine.memories import memory_store
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
# A 36-character string that is the right *length* but not UUID-shaped must
# still be rejected — previously a length-only constraint let it through to
# the store before is_valid_rider_id caught it.
# 36 characters, but the segments are non-hex — the right length yet not
# UUID-shaped.
MALFORMED_36_CHAR_RIDER_ID = "not-a-uuid-but-exactly-36-characters"


def test_share_position_rejects_36_char_non_uuid_rider_id():
    assert len(MALFORMED_36_CHAR_RIDER_ID) == 36
    response = client.post(
        "/journey/share-position",
        json={"rider_id": MALFORMED_36_CHAR_RIDER_ID, "lat": -30.0, "lon": 24.0},
    )
    assert response.status_code == 422

def test_shared_positions_rejects_36_char_non_uuid_rider_id():
    response = client.get(
        "/journey/shared-positions", params={"rider_id": MALFORMED_36_CHAR_RIDER_ID}
    )
    assert response.status_code == 422

def test_leave_rejects_36_char_non_uuid_rider_id():
    response = client.post(
        "/journey/share-position/leave",
        json={"rider_id": MALFORMED_36_CHAR_RIDER_ID, "lat": 0.0, "lon": 0.0},
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

# ---------------------------------------------------------------------
# Rider memories — "new generation creates new memories, older generation
# relives old ones" — end-to-end through the actual API.
# ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def empty_memory_store():
    memory_store.clear()
    yield
    memory_store.clear()


def test_create_memory_then_relive_it_for_the_waypoint():
    create = client.post(
        "/journey/memories",
        json={
            "rider_id": RIDER_A,
            "waypoint_id": "kimberley",
            "text": " The Big Hole at sunrise — my grandmother worked nearby in the sixties.",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["waypoint_id"] == "kimberley"
    assert body["rider_id"] == RIDER_A
    # Input is stripped by the store.
    assert body["text"].startswith("The Big Hole")
    assert body["memory_id"]
    assert body["created_at"] > 0

    # The "older generation relives old memories" path: the memory comes back
    # through GET for that stop, newest first.
    listed = client.get("/journey/memories", params={"waypoint_id": "kimberley"})
    assert listed.status_code == 200
    bodies = listed.json()
    assert len(bodies) == 1
    assert bodies[0]["text"].startswith("The Big Hole")


def test_list_memories_is_newest_first_and_filters_by_waypoint():
    client.post("/journey/memories", json={"rider_id": RIDER_A, "waypoint_id": "kimberley", "text": "first"})
    client.post("/journey/memories", json={"rider_id": RIDER_B, "waypoint_id": "de_aar", "text": "karoo"})

    all_memories = client.get("/journey/memories")
    assert [m["text"] for m in all_memories.json()] == ["karoo", "first"]

    kimberley_only = client.get("/journey/memories", params={"waypoint_id": "kimberley"})
    assert [m["text"] for m in kimberley_only.json()] == ["first"]


def test_create_memory_validations_return_422():
    # Unknown waypoint.
    response = client.post(
        "/journey/memories",
        json={"rider_id": RIDER_A, "waypoint_id": "narnia", "text": "hello"},
    )
    assert response.status_code == 422

    # Blank text.
    response = client.post(
        "/journey/memories",
        json={"rider_id": RIDER_A, "waypoint_id": "kimberley", "text": "   "},
    )
    assert response.status_code == 422

    # Non-UUID rider id — rejected at schema validation before the store.
    response = client.post(
        "/journey/memories",
        json={"rider_id": "not-a-uuid", "waypoint_id": "kimberley", "text": "hello"},
    )
    assert response.status_code == 422


def test_list_memories_rejects_unknown_waypoint():
    response = client.get("/journey/memories", params={"waypoint_id": "narnia"})
    assert response.status_code == 422


def test_create_and_unlock_a_coordinate_tagged_memory():
    # An older-generation rider leaves a memory pinned to the Big Hole.
    create = client.post(
        "/journey/memories",
        json={
            "rider_id": RIDER_A,
            "waypoint_id": "kimberley",
            "text": "My grandmother sold vetkoek at this fence in the sixties.",
            "lat": -28.7353,
            "lon": 24.7697,
        },
    )
    assert create.status_code == 201
    created = create.json()
    assert created["lat"] == -28.7353
    assert created["lon"] == 24.7697

    # A new-generation rider passing the exact spot unlocks it dynamically.
    nearby = client.get(
        "/journey/memories/nearby",
        params={"lat": -28.7353, "lon": 24.7697, "radius": 500.0},
    )
    assert nearby.status_code == 200
    unlocked = nearby.json()
    assert any("vetkoek" in m["text"] for m in unlocked)

    # The same rider 30km away unlocks nothing — memories are pinned, not broad.
    far_away = client.get(
        "/journey/memories/nearby",
        params={"lat": -29.1, "lon": 24.7, "radius": 500.0},
    )
    assert far_away.json() == []


def test_nearby_memories_ignores_untagged_memories():
    client.post("/journey/memories", json={"rider_id": RIDER_A, "waypoint_id": "kimberley", "text": "no pin"})
    nearby = client.get(
        "/journey/memories/nearby",
        params={"lat": -28.7353, "lon": 24.7697, "radius": 5000.0},
    )
    assert nearby.json() == []


def test_nearby_memories_rejects_invalid_coordinates_and_radius():
    response = client.get("/journey/memories/nearby", params={"lat": 999.0, "lon": 24.7697})
    assert response.status_code == 422

    response = client.get(
        "/journey/memories/nearby", params={"lat": -28.7353, "lon": 24.7697, "radius": 0}
    )
    assert response.status_code == 422


def test_create_memory_echoes_audio_url_and_rejects_invalid_one():
    create = client.post(
        "/journey/memories",
        json={
            "rider_id": RIDER_A,
            "waypoint_id": "kimberley",
            "text": "Listen to Gogo's story.",
            "audio_url": "https://cdn.example.com/voice/gogo-kimberley.mp3",
        },
    )
    assert create.status_code == 201
    assert create.json()["audio_url"] == "https://cdn.example.com/voice/gogo-kimberley.mp3"

    response = client.post(
        "/journey/memories",
        json={"rider_id": RIDER_A, "waypoint_id": "kimberley", "text": "bad", "audio_url": "file:///etc/passwd"},
    )
    assert response.status_code == 422

# ---------------------------------------------------------------------
# Stop discovery + geofence verification (/story-engine) — the CLI and
# frontend surfaces for looking up a stop and checking live telemetry.
# ---------------------------------------------------------------------

def test_stop_discovery_returns_narrative_sites_stalls_and_coordinates():
    response = client.get("/story-engine/stop/kimberley")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["stop_name"] == "Kimberley Station"
    assert "diamond" in data["historical_narrative"].lower()
    assert any(s["name"] == "Kimberley Big Hole" for s in data["heritage_sites"])
    assert data["local_stalls"]
    assert data["lat"] == -28.7353
    assert data["lon"] == 24.7697


def test_stop_discovery_falls_back_to_generic_profile_for_unknown_stop():
    response = client.get("/story-engine/stop/nowhere")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stop_name"] == "Shosholoza Corridor Stop"
    assert data["lat"] is None
    assert data["lon"] is None


def test_geofence_verify_inside_and_outside():
    # Rider just off Kimberley station, within the default 100m radius.
    inside = client.get(
        "/story-engine/geofence/verify",
        params={
            "user_lat": -28.7353,
            "user_lon": 24.7697,
            "target_lat": -28.73532,
            "target_lon": 24.76972,
        },
    )
    assert inside.status_code == 200
    assert inside.json()["inside_geofence"] is True
    assert inside.json()["metrics"]["threshold_radius_m"] == 100.0

    # ~2km out — outside the default radius, inside a generous one.
    outside = client.get(
        "/story-engine/geofence/verify",
        params={
            "user_lat": -28.7353,
            "user_lon": 24.7697,
            "target_lat": -28.7510,
            "target_lon": 24.7697,
        },
    )
    assert outside.status_code == 200
    assert outside.json()["inside_geofence"] is False


def test_geofence_verify_rejects_invalid_coordinates_and_radius():
    bad_lat = client.get(
        "/story-engine/geofence/verify",
        params={"user_lat": 999.0, "user_lon": 24.7, "target_lat": -28.7, "target_lon": 24.7},
    )
    assert bad_lat.status_code == 422

    zero_radius = client.get(
        "/story-engine/geofence/verify",
        params={
            "user_lat": -28.7, "user_lon": 24.7,
            "target_lat": -28.7, "target_lon": 24.7, "radius": 0,
        },
    )
    assert zero_radius.status_code == 422


def test_story_source_is_the_contributor_not_the_reviewer():
    kimberley = get_waypoint("kimberley")
    response = client.get(
        "/journey/position", params={"lat": kimberley.latitude, "lon": kimberley.longitude}
    )
    body = response.json()
    # The seeded story's contributor is the heritage-site partner, not the
    # pending reviewer — story_source must never be the reviewer attribution.
    assert body["story_source"] == "Kimberley Big Hole & Diamond Museum (pilot partner outreach pending)"
