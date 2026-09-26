"""
Integration tests for the spatial layer, Journey Guardian, and ticket
validation, driven through the real FastAPI app.

Same rationale as test_integration.py: HTTP request in, database and ETA
engine run for real inside the app, JSON response out. What a judge sees at
the pitch is this contract, so it is worth testing at exactly this boundary.

Run with: pytest backend/tests/test_guardian_api.py
"""

import pytest
from fastapi.testclient import TestClient

from app.story_engine.api import app
from app.story_engine.journey import journey_registry
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN
from app.story_engine.spatial import SpatialStore
import app.story_engine.spatial as spatial_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    """
    Give every test its own on-disk spatial store.

    A file rather than :memory: so the persistence claim is exercised for
    real, and autouse so no test can see another's journeys.
    """
    store = SpatialStore(sqlite_path=str(tmp_path / "corridor.sqlite"))
    store.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", store)
    return store


# ---------------------------------------------------------------------
# Spatial layer
# ---------------------------------------------------------------------

def test_health_reports_which_spatial_driver_is_live():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["spatial_driver"] in ("sqlite", "postgis")
    assert body["corridor_km"] > 1000


def test_corridor_endpoint_returns_geojson_ordered_lon_lat():
    body = client.get("/spatial/corridor").json()
    assert body["corridor_id"] == "pretoria_cape_town"
    assert len(body["coordinates"]) == len(PRETORIA_TO_CAPE_TOWN)
    first = body["coordinates"][0]
    assert first[0] == pytest.approx(PRETORIA_TO_CAPE_TOWN[0].longitude)
    assert first[1] == pytest.approx(PRETORIA_TO_CAPE_TOWN[0].latitude)


def test_corridor_nodes_expose_province_and_sequence():
    nodes = client.get("/spatial/corridor").json()["nodes"]
    assert [n["sequence"] for n in nodes] == list(range(len(nodes)))
    assert all(n["province"] for n in nodes)


def test_resolve_position_snaps_to_the_named_station():
    for waypoint in PRETORIA_TO_CAPE_TOWN:
        body = client.post(
            "/spatial/resolve", json={"lat": waypoint.latitude, "lon": waypoint.longitude}
        ).json()
        assert body["nearest_waypoint_id"] == waypoint.id


def test_resolve_position_rejects_impossible_coordinates():
    assert client.post("/spatial/resolve", json={"lat": 999, "lon": 24}).status_code == 422
    assert client.post("/spatial/resolve", json={"lat": -30.6, "lon": 999}).status_code == 422


# ---------------------------------------------------------------------
# Journey Guardian
# ---------------------------------------------------------------------

def test_a_journey_that_never_reported_reads_as_waiting_not_missing():
    journey_id = "33333333-3333-4333-8333-333333333333"
    response = client.get(f"/guardian/journeys/{journey_id}/eta")
    assert response.status_code == 200
    body = response.json()
    # A family link opened for a train that has not started moving should
    # say "waiting", not 404.
    assert body["status"] == "no_data"
    assert body["position"] is None


def test_eta_endpoint_rejects_a_non_uuid_journey_id():
    assert client.get("/guardian/journeys/mthabo/eta").status_code == 422


def test_create_journey_returns_the_handle():
    response = client.post(
        "/guardian/journeys", json={"origin_waypoint_id": "pretoria", "destination_waypoint_id": "cape_town"}
    )
    assert response.status_code == 201
    assert response.json()["guardian_link_count"] == 0


def test_create_journey_rejects_an_unknown_stop():
    response = client.post("/guardian/journeys", json={"origin_waypoint_id": "atlantis"})
    assert response.status_code == 422
    assert "origin_waypoint_id" in response.json()["detail"]


def test_a_corpus_position_report_is_persisted_and_answers_with_an_eta():
    journey_id = "44444444-4444-4444-8444-444444444444"
    for step, (lat, lon) in enumerate([(-26.0, 28.0), (-27.0, 27.0), (-28.0, 25.0)]):
        response = client.post(
            f"/guardian/journeys/{journey_id}/position",
            json={
                "journey_id": journey_id,
                "lat": lat,
                "lon": lon,
                "source": "corridor",
                "speed_mps": 17.0,
                "recorded_at": 1_000.0 + step * 1800,
            },
        )
        assert response.status_code == 200

    body = response.json()
    assert body["last_report_source"] == "corridor"
    assert body["position"]["distance_along_km"] > 0


def test_position_report_rejects_an_unrecognised_source():
    journey_id = "55555555-5555-4555-8555-555555555555"
    response = client.post(
        f"/guardian/journeys/{journey_id}/position",
        json={"journey_id": journey_id, "lat": -26.0, "lon": 28.0, "source": "gossip"},
    )
    assert response.status_code == 422
    assert "source must be one of" in response.json()["detail"]


def test_position_report_rejects_a_mismatched_journey_id():
    response = client.post(
        "/guardian/journeys/66666666-6666-4666-8666-666666666666/position",
        json={"journey_id": "77777777-7777-4777-8777-777777777777", "lat": -26.0, "lon": 28.0},
    )
    assert response.status_code == 422


def test_telemetry_endpoint_returns_the_audit_trail():
    journey_id = "88888888-8888-4888-8888-888888888888"
    for step, (lat, lon) in enumerate([(-26.0, 28.0), (-27.0, 27.0)]):
        client.post(
            f"/guardian/journeys/{journey_id}/position",
            json={
                "journey_id": journey_id, "lat": lat, "lon": lon,
                "source": "corridor", "recorded_at": 1_000.0 + step * 1800,
            },
        )
    body = client.get(f"/guardian/telemetry/{journey_id}").json()
    assert body["count"] == 2
    # Oldest first, with timestamps and sources — a rider who disputes the
    # delay gets the actual reports, not just a conclusion.
    assert body["points"][0]["lat"] == -26.0
    assert all(p["source"] == "corridor" for p in body["points"])


def test_simulate_run_produces_a_usable_journey_and_link():
    response = client.post(
        "/guardian/simulate-run",
        json={"start_waypoint_id": "johannesburg_park", "steps": 6, "speed_kmh": 62},
    )
    assert response.status_code == 201
    body = response.json()
    # One report of the origin station, then one per step of movement.
    assert body["points_recorded"] == 7
    assert body["eta"]["observed_speed_kmh"] == pytest.approx(62, rel=0.05)
    # A freshly simulated run must not immediately read as a dead feed.
    assert body["eta"]["status"] != "signal_lost"


def test_a_full_corridor_run_completes_the_passport():
    run = client.post(
        "/guardian/simulate-run",
        json={"start_waypoint_id": "pretoria", "steps": 50, "step_minutes": 30},
    ).json()
    passport = client.get(f"/guardian/journeys/{run['journey_id']}/passport").json()
    assert passport["stamps_earned"] == passport["stamps_total"] == 9
    assert passport["complete"] is True
    assert passport["provinces_visited"] == ["Gauteng", "Northern Cape", "Free State", "Northern Cape", "Western Cape"]


def test_passport_endpoint_rejects_a_non_uuid_journey_id():
    assert client.get("/guardian/journeys/mthabo/passport").status_code == 422


def test_passport_for_a_journey_that_never_reported_is_empty_not_an_error():
    body = client.get("/guardian/journeys/99999999-9999-4999-8999-999999999999/passport").json()
    assert body["stamps"] == []
    assert body["complete"] is False


# ---------------------------------------------------------------------
# Offline story pack
# ---------------------------------------------------------------------

def test_offline_pack_is_self_contained():
    pack = client.get("/journey/offline-pack?waypoint_id=matjiesfontein").json()
    # Everything a rider needs at a stop, in one response, because a dead
    # zone means a four-request story never loads.
    assert pack["waypoint_id"] == "matjiesfontein"
    assert pack["story"]["text"]
    assert pack["pois"]
    assert pack["stop_content"]["historical_narrative"]
    assert pack["stop_content"]["era_years"] == ["1970", "1990", "2023"]
    assert pack["next_waypoint"]["waypoint_id"] == "worcester"


def test_every_stop_has_a_story_in_its_offline_pack():
    """
    Only two of the eight corridor stations have a written ride-along story.
    The pack falls back to the stop's historical narrative rather than
    shipping an empty field, because a rider reaching a stop in a dead zone
    with no story at all is the failure this whole feature exists to prevent.
    """
    for stop_id in ["pretoria", "johannesburg_park", "de_aar", "worcester", "cape_town"]:
        pack = client.get(f"/journey/offline-pack?waypoint_id={stop_id}").json()
        assert pack["story"]["text"], f"{stop_id} has no story"
        assert pack["story"]["kind"] in ("ride-along story", "stop narrative")


def test_the_story_fallback_is_labelled_rather_than_passed_off_as_fuller_content():
    pack = client.get("/journey/offline-pack?waypoint_id=de_aar").json()
    # de Aar has no ride-along story written yet; the UI must be able to tell
    # the rider which kind of text they are reading.
    assert pack["story"]["kind"] == "stop narrative"
    assert pack["story"]["text"] == pack["stop_content"]["historical_narrative"]


def test_a_written_ride_along_story_takes_precedence_over_the_narrative():
    pack = client.get("/journey/offline-pack?waypoint_id=kimberley").json()
    assert pack["story"]["kind"] == "ride-along story"
    assert pack["story"]["text"] != pack["stop_content"]["historical_narrative"]


def test_offline_pack_rejects_an_unknown_stop():
    assert client.get("/journey/offline-pack?waypoint_id=atlantis").status_code == 422


def test_offline_pack_carries_a_waypoint_position():
    pack = client.get("/journey/offline-pack?waypoint_id=kimberley").json()
    assert pack["position"]["lat"] == pytest.approx(-28.7353)
    assert pack["progress_fraction"] > 0


# ---------------------------------------------------------------------
# QR boarding
# ---------------------------------------------------------------------

def test_ticket_qr_encodes_a_payload_with_no_personal_data():
    reference = client.post("/tickets", json={"holder_label": "Ms Ndlovu"}).json()["booking_reference"]
    body = client.get(f"/tickets/{reference}/qr").json()
    assert body["booking_reference"] == reference
    assert reference in body["payload"]
    assert "pretoria_cape_town" in body["payload"]
    # A boarding code is readable by anyone who points a phone at it, so it
    # must not carry the holder's label.
    assert "Ms Ndlovu" not in body["payload"]


def test_ticket_qr_renders_an_actual_qr_when_segno_is_installed():
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    body = client.get(f"/tickets/{reference}/qr").json()
    if not body["qr_available"]:
        assert body["reason"]
        return
    assert body["qr_svg"].lstrip().startswith("<?xml")
    assert "<svg" in body["qr_svg"]


def test_scan_accepts_a_valid_ticket_and_refuses_a_voided_one():
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    code = client.get(f"/tickets/{reference}/qr").json()
    assert client.get(code["scan_path"]).json()["admissible"] is True

    client.post("/tickets/void", json={"booking_reference": reference})
    refused = client.get(code["scan_path"]).json()
    assert refused["admissible"] is False
    assert "voided" in refused["reason"].lower()


def test_scan_of_an_unknown_reference_is_a_404():
    assert client.get("/scan/ZZ99%20XXX").status_code == 404


def test_qr_for_an_unknown_ticket_is_a_404():
    assert client.get("/tickets/ZZ99%20XXX/qr").status_code == 404


def test_health_reports_whether_qr_is_available():
    assert isinstance(client.get("/health").json()["qr_available"], bool)


def test_simulate_run_rejects_an_unknown_start():
    assert client.post("/guardian/simulate-run", json={"start_waypoint_id": "atlantis"}).status_code == 422


# ---------------------------------------------------------------------
# Guardian links
# ---------------------------------------------------------------------

def test_a_family_link_resolves_to_a_read_only_view():
    run = client.post("/guardian/simulate-run", json={"start_waypoint_id": "de_aar", "steps": 4}).json()
    journey_id = run["journey_id"]

    link = client.post(
        f"/guardian/journeys/{journey_id}/links", json={"display_name": "Ada's journey"}
    )
    assert link.status_code == 201
    token = link.json()["token"]

    view = client.get(f"/guardian/track/{token}")
    assert view.status_code == 200
    body = view.json()
    assert body["tracking"]["display_name"] == "Ada's journey"
    assert body["journey"]["journey_id"] == journey_id
    assert body["headline"]
    assert body["eta"]["milestones"]


def test_a_revoked_link_stops_working_at_once():
    run = client.post("/guardian/simulate-run", json={"start_waypoint_id": "de_aar", "steps": 3}).json()
    journey_id = run["journey_id"]
    token = client.post(f"/guardian/journeys/{journey_id}/links", json={}).json()["token"]

    assert client.get(f"/guardian/track/{token}").status_code == 200
    assert client.delete(f"/guardian/links/{token}").status_code == 204
    assert client.get(f"/guardian/track/{token}").status_code == 404


def test_issuing_a_link_for_an_unknown_journey_is_a_404():
    assert client.post("/guardian/journeys/99999999-9999-4999-8999-999999999999/links", json={}).status_code == 404


def test_an_unknown_or_malformed_token_is_a_404():
    for bad in ("unknown-token-value", "short", "a" * 100):
        assert client.get(f"/guardian/track/{bad}").status_code == 404


def test_revoking_an_unknown_token_is_a_404():
    assert client.delete("/guardian/links/never-existed").status_code == 404


# ---------------------------------------------------------------------
# Ticket validation
# ---------------------------------------------------------------------

def test_ticket_lifecycle_issue_validate_board():
    ticket = client.post(
        "/tickets", json={"origin_waypoint_id": "pretoria", "destination_waypoint_id": "cape_town"}
    )
    assert ticket.status_code == 201
    reference = ticket.json()["booking_reference"]

    assert client.post("/tickets/validate", json={"booking_reference": reference}).json()["admissible"] is True
    assert client.post("/tickets/board", json={"booking_reference": reference}).json()["status"] == "boarded"
    # A used ticket cannot be boarded twice.
    assert client.post("/tickets/board", json={"booking_reference": reference}).status_code == 422


def test_ticket_reference_lookup_is_forgiving_of_case_and_spacing():
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    assert client.get(f"/tickets/{reference.lower().replace(' ', '')}").status_code == 200
    assert client.post("/tickets/validate", json={"booking_reference": reference.replace(" ", "")}).status_code == 200


def test_an_unknown_ticket_is_a_404():
    assert client.get("/tickets/ZZ99 XXX").status_code == 404
    assert client.post("/tickets/validate", json={"booking_reference": "ZZ99 XXX"}).status_code == 404


def test_a_malformed_reference_is_rejected_at_issue_time():
    response = client.post("/tickets", json={"booking_reference": "not-a-reference"})
    assert response.status_code == 422
    assert "operator format" in response.json()["detail"]


def test_a_voided_ticket_is_refused_with_a_reason_a_human_can_read():
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    client.post("/tickets/void", json={"booking_reference": reference, "reason": "cancelled"})

    body = client.post("/tickets/validate", json={"booking_reference": reference}).json()
    assert body["admissible"] is False
    assert "voided" in body["reason"].lower()
    assert client.post("/tickets/board", json={"booking_reference": reference}).status_code == 422


def test_boarding_a_ticket_binds_it_to_a_new_journey():
    """
    The claim behind the unfair-advantage section: once a ticket is boarded,
    the journey exists server-side, independently of any device the
    passenger is carrying.
    """
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    journey = client.post("/guardian/journeys", json={"ticket_reference": reference})
    assert journey.status_code == 201
    journey_id = journey.json()["journey_id"]
    assert journey.json()["ticket_id"] is not None

    # A position report on that journey needs no device and no ticket again.
    body = client.post(
        f"/guardian/journeys/{journey_id}/position",
        json={"journey_id": journey_id, "lat": -26.0, "lon": 28.0, "source": "corridor"},
    ).json()
    assert body["position"] is not None


def test_creating_a_journey_with_an_already_used_ticket_is_refused():
    reference = client.post("/tickets", json={}).json()["booking_reference"]
    client.post("/tickets/board", json={"booking_reference": reference})
    response = client.post("/guardian/journeys", json={"ticket_reference": reference})
    assert response.status_code == 422


def test_creating_a_journey_with_a_malformed_reference_is_a_422():
    assert client.post("/guardian/journeys", json={"ticket_reference": "nope"}).status_code == 422
