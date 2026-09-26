"""
Unit tests for the ETA and provincial milestone engine.

Run with: pytest backend/tests/test_eta.py

The interesting property here is not that the arithmetic runs — it is that
the engine refuses to produce a confident number when it does not have one.
A stopped train and a dead telemetry feed both yield "no ETA", because
inventing one is the exact failure mode this product exists to eliminate.
"""

import pytest

from app.story_engine.eta import (
    SCHEDULED_SPEED_KMH,
    STALE_TELEMETRY_SECONDS,
    build_milestones,
    compute_eta,
    estimate_speed,
    simulate_corridor_run,
)
from app.story_engine.spatial import SpatialStore, TelemetryPoint
import app.story_engine.spatial as spatial_module


@pytest.fixture()
def store(monkeypatch):
    """
    Point the ETA engine at a private in-memory store.

    eta.py reaches the store through the spatial module rather than binding
    the name itself, so replacing `spatial.spatial_store` is enough.
    """
    s = SpatialStore(sqlite_path=":memory:")
    s.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", s)
    return s


def test_estimate_speed_reports_insufficient_for_one_sample():
    speed, source = estimate_speed([TelemetryPoint("j", -26.0, 28.0, None, 1000.0, "corridor")])
    assert source == "insufficient"
    assert speed == SCHEDULED_SPEED_KMH


def test_estimate_speed_derives_observed_speed_from_real_movement():
    # Two points 111.32km apart (1 degree of latitude) one hour apart.
    points = [
        TelemetryPoint("j", -26.0, 28.0, None, 1000.0, "corridor"),
        TelemetryPoint("j", -27.0, 28.0, None, 4600.0, "corridor"),
    ]
    speed, source = estimate_speed(points)
    assert source == "observed"
    assert speed == pytest.approx(111.32, rel=0.02)


def test_estimate_speed_reports_stationary_rather_than_a_division_by_zero():
    points = [
        TelemetryPoint("j", -26.0, 28.0, None, 1000.0, "corridor"),
        TelemetryPoint("j", -26.0, 28.0, None, 4600.0, "corridor"),
    ]
    speed, source = estimate_speed(points)
    assert source == "stationary"
    assert speed == 0.0


def test_estimate_speed_ignores_non_increasing_timestamps():
    # A clock that jumped backwards must not produce a negative or infinite
    # speed that then poisons the ETA.
    points = [
        TelemetryPoint("j", -26.0, 28.0, None, 5000.0, "corridor"),
        TelemetryPoint("j", -27.0, 28.0, None, 1000.0, "corridor"),
    ]
    speed, source = estimate_speed(points)
    assert source == "insufficient"
    assert speed == SCHEDULED_SPEED_KMH


def test_simulated_run_lands_on_the_corridor_and_reports_observed_speed(store):
    simulate_corridor_run("sim-1", start_waypoint_id="johannesburg_park", steps=5, speed_kmh=62)
    result = compute_eta("sim-1")
    assert result.status in ("on_time", "delayed")
    assert result.observed_speed_kmh == pytest.approx(62, rel=0.05)
    assert result.speed_source == "observed"
    # The final sample must be stamped "now", or a fresh run immediately reads
    # as a stale feed and the demo shows "no position report" on arrival.
    assert result.last_report_seconds_ago == pytest.approx(0.0, abs=5.0)


def test_simulated_run_moves_south_along_the_corridor(store):
    simulate_corridor_run("sim-2", start_waypoint_id="pretoria", steps=4, speed_kmh=62)
    points = store.recent_telemetry("sim-2")
    # One report of the origin station, then one per step of movement.
    assert len(points) == 5
    latitudes = [p.latitude for p in points]
    assert latitudes == sorted(latitudes, reverse=True)


def test_simulated_run_timestamps_strictly_increase(store):
    # A tie between two samples makes "which is the latest position?" depend
    # on row order rather than on the data.
    simulate_corridor_run("sim-ts", start_waypoint_id="pretoria", steps=6, step_minutes=30)
    stamps = [p.recorded_at for p in store.recent_telemetry("sim-ts")]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_a_fresh_run_is_not_reported_as_stale(store):
    """Regression guard: the simulator used to back-date every sample."""
    simulate_corridor_run("sim-3", start_waypoint_id="kimberley", steps=2, step_minutes=30)
    result = compute_eta("sim-3")
    assert result.status != "signal_lost"
    assert result.last_report_seconds_ago < STALE_TELEMETRY_SECONDS


def test_a_stale_feed_says_so_instead_of_confidently_guessing(store):
    old = 1_000_000.0
    for step, (lat, lon) in enumerate([(-26.0, 28.0), (-27.0, 27.0), (-28.0, 25.0)]):
        store.record_telemetry("stale", lat, lon, speed_mps=17.0, recorded_at=old + step * 1800)
    result = compute_eta("stale", now=old + 40_000)
    assert result.status == "signal_lost"
    # No ETA at all when we cannot know one.
    assert result.eta_arrival_epoch is None
    assert result.eta_next_station_epoch is None
    assert "no position report" in result.delay_display.lower()


def test_a_stopped_train_gets_no_eta_but_keeps_its_position(store):
    now = 1_000_000.0
    for step in range(4):
        store.record_telemetry("stopped", -27.0, 27.0, speed_mps=0.0, recorded_at=now + step * 60)
    result = compute_eta("stopped", now=now + 300)
    assert result.status == "stopped"
    assert result.observed_speed_kmh == 0.0
    assert result.eta_arrival_epoch is None
    # The position is still reported — "we don't know when" must not become
    # "we don't know where".
    assert result.position.nearest_waypoint_id != ""
    assert "stopped" in result.delay_display.lower()


def test_a_slow_train_is_reported_as_delayed(store):
    simulate_corridor_run("slow", start_waypoint_id="pretoria", steps=5, speed_kmh=20)
    result = compute_eta("slow")
    assert result.status == "delayed"
    assert result.delay_hours > 0
    assert "behind schedule" in result.delay_display


def test_eta_for_a_journey_with_no_telemetry_raises(store):
    with pytest.raises(LookupError):
        compute_eta("never-reported")


def test_milestones_include_every_station_and_every_province(store):
    position = store.resolve_position(-28.7353, 24.7697)
    labels = [m.label for m in build_milestones(position)]

    # The origin reads as "Departed X" rather than a bare station name,
    # because leaving is the event a family actually cares about.
    for expected in ("Departed Pretoria", "Kimberley", "Cape Town", "De Aar",
                     "Worcester", "Matjiesfontein"):
        assert expected in labels, f"{expected} missing from milestones"

    provinces = {m.label for m in build_milestones(position) if m.kind == "province_entry"}
    assert provinces == {"Entered Northern Cape", "Entered Western Cape"}


def test_milestones_keep_the_station_on_a_province_boundary(store):
    """
    A province crossing and the station it happens at are two different events.
    An earlier version emitted only the crossing, so a family member watching
    the list could see "Entered the Western Cape" and never once see
    "Beaufort West" — the two stations standing on that boundary vanished
    from the timeline entirely.
    """
    milestones = build_milestones(store.resolve_position(-28.7353, 24.7697))
    labels = [m.label for m in milestones]
    assert "Entered Western Cape" in labels
    assert "Beaufort West" in labels
    crossing = labels.index("Entered Western Cape")
    assert labels[crossing + 1] == "Beaufort West"


def test_milestones_mark_what_has_been_passed(store):
    at_kimberley = build_milestones(store.resolve_position(-28.7353, 24.7697))
    by_label = {m.label: m.reached for m in at_kimberley}
    assert by_label["Departed Pretoria"] is True
    assert by_label["Kimberley"] is True
    assert by_label["Entered Northern Cape"] is True
    assert by_label["Cape Town"] is False
    assert by_label["Arrived Cape Town"] is False


def test_milestone_distances_increase_monotonically(store):
    milestones = build_milestones(store.resolve_position(-28.7353, 24.7697))
    distances = [m.at_km for m in milestones]
    assert distances == sorted(distances)


def test_eta_serialises_to_a_json_safe_payload(store):
    simulate_corridor_run("json-1", start_waypoint_id="de_aar", steps=3)
    payload = compute_eta("json-1").as_dict()
    import json

    # The family page renders this directly; a datetime object here would
    # blow up the response with a 500 rather than a useful error.
    assert json.loads(json.dumps(payload))["journey_id"] == "json-1"
    assert set(payload["eta"]) == {"next_station", "next_station_at", "arrival_station", "arrival_at"}
