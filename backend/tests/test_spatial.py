"""
Unit tests for the spatial layer — corridor geometry, along-track position
resolution, and telemetry persistence.

Run with: pytest backend/tests/test_spatial.py

Every test builds its own in-memory SQLite SpatialStore rather than sharing
the module-level singleton, so ordering between tests cannot matter and a
test that writes telemetry cannot leak into one that reads it.
"""

import pytest

from app.story_engine.route import PRETORIA_TO_CAPE_TOWN
from app.story_engine.spatial import (
    SpatialStore,
    _project_on_segment,
    haversine_km,
)


@pytest.fixture()
def store():
    s = SpatialStore(sqlite_path=":memory:")
    s.ensure_schema()
    return s


def test_corridor_has_one_node_per_waypoint(store):
    nodes = store.corridor_nodes()
    assert len(nodes) == len(PRETORIA_TO_CAPE_TOWN)
    assert [n.waypoint_id for n in nodes] == [w.id for w in PRETORIA_TO_CAPE_TOWN]


def test_corridor_nodes_are_ordered_and_cumulative_km_increases(store):
    nodes = store.corridor_nodes()
    assert [n.sequence for n in nodes] == list(range(len(nodes)))
    cumulative = [n.cumulative_km for n in nodes]
    assert cumulative[0] == 0.0
    assert cumulative == sorted(cumulative)


def test_corridor_total_is_plausible_for_a_1365km_corridor(store):
    # Pretoria to Cape Town is roughly 1,300-1,450km by rail. A much smaller
    # number means the unit maths broke; a much larger one means the haversine
    # is being fed degrees where it expects radians or vice versa.
    assert 1300.0 < store.total_km() < 1450.0


def test_every_node_carries_a_province(store):
    # Provincial milestone tracking is meaningless if a station has no
    # province, and the pitch names the province crossings explicitly.
    assert all(node.province for node in store.corridor_nodes())


def test_resolve_position_snaps_to_the_station_it_is_given(store):
    for waypoint in PRETORIA_TO_CAPE_TOWN:
        resolved = store.resolve_position(waypoint.latitude, waypoint.longitude)
        assert resolved.nearest_waypoint_id == waypoint.id, (
            f"{waypoint.name} resolved to {resolved.nearest_waypoint_name}"
        )
        assert resolved.distance_to_corridor_m < 1.0


def test_resolve_position_preserves_lat_lon_orientation(store):
    # Guards a real bug that shipped during development: the equirectangular
    # projection scales longitude by cos(latitude), and mixing the two axes up
    # silently returned Kimberley's coordinates transposed — a plausible-looking
    # position on the wrong side of the country.
    resolved = store.resolve_position(-28.7353, 24.7697)
    assert resolved.latitude == pytest.approx(-28.7353, abs=0.001)
    assert resolved.longitude == pytest.approx(24.7697, abs=0.001)


def test_resolve_position_progress_is_monotonic_along_the_corridor(store):
    fractions = [store.resolve_position(w.latitude, w.longitude).progress_fraction
                 for w in PRETORIA_TO_CAPE_TOWN]
    assert fractions == sorted(fractions)
    assert fractions[0] == pytest.approx(0.0, abs=0.01)
    assert fractions[-1] == pytest.approx(1.0, abs=0.01)


def test_resolve_position_uses_distance_not_index_to_pick_nearest_station(store):
    """
    The stations are not evenly spaced, so a train standing at De Aar (707km
    along) is much closer to De Aar than to Beaufort West. Picking the nearest
    by sequence number instead reports the wrong station by a couple of hours'
    worth of corridor.
    """
    de_aar = next(w for w in PRETORIA_TO_CAPE_TOWN if w.id == "de_aar")
    resolved = store.resolve_position(de_aar.latitude, de_aar.longitude)
    assert resolved.nearest_waypoint_id == "de_aar"
    assert resolved.distance_to_corridor_m < 1.0


def test_resolve_position_reports_off_corridor_distance(store):
    # Half a degree east of De Aar's longitude, on the same latitude. The
    # corridor there runs north-west/south-east, so this is tens of km clear
    # of the line rather than on it.
    resolved = store.resolve_position(-30.6508, 24.5)
    assert resolved.distance_to_corridor_m > 20_000.0
    # ...but it still resolves to a sensible place on the line rather than
    # erroring, because a rider's GPS is frequently nowhere near a station.
    assert 0.0 <= resolved.progress_fraction <= 1.0


def test_resolve_position_reports_which_driver_answered(store):
    assert store.resolve_position(-28.7353, 24.7697).driver == "sqlite"


def test_corridor_geometry_payload_is_frontend_ready(store):
    geometry = store.corridor_geometry()
    assert geometry["corridor_id"] == "pretoria_cape_town"
    # MapLibre wants [longitude, latitude] pairs.
    first = geometry["coordinates"][0]
    assert first == pytest.approx([PRETORIA_TO_CAPE_TOWN[0].longitude,
                                   PRETORIA_TO_CAPE_TOWN[0].latitude])
    assert len(geometry["coordinates"]) == len(PRETORIA_TO_CAPE_TOWN)
    assert all("province" in node for node in geometry["nodes"])


def test_telemetry_round_trips_oldest_first(store):
    for step, (lat, lon) in enumerate([(-26.0, 28.0), (-27.0, 27.0), (-28.0, 25.0)]):
        store.record_telemetry("j1", lat, lon, speed_mps=15.0, recorded_at=1000.0 + step)

    points = store.recent_telemetry("j1")
    assert [p.latitude for p in points] == [-26.0, -27.0, -28.0]


def test_telemetry_is_scoped_per_journey(store):
    store.record_telemetry("journey-a", -26.0, 28.0, recorded_at=1000.0)
    store.record_telemetry("journey-b", -30.0, 24.0, recorded_at=1000.0)
    assert len(store.recent_telemetry("journey-a")) == 1
    assert store.recent_telemetry("journey-a")[0].latitude == -26.0
    assert store.recent_telemetry("journey-b")[0].latitude == -30.0


def test_latest_telemetry_is_none_for_an_unknown_journey(store):
    assert store.latest_telemetry("never-seen") is None


def test_journey_count_counts_distinct_journeys(store):
    store.record_telemetry("journey-a", -26.0, 28.0, recorded_at=1000.0)
    store.record_telemetry("journey-a", -27.0, 27.0, recorded_at=1001.0)
    store.record_telemetry("journey-b", -30.0, 24.0, recorded_at=1002.0)
    assert store.journey_count() == 2


def test_telemetry_source_is_preserved_for_provenance(store):
    # The family view surfaces this, so a corridor-fed position and a
    # phone-fed one must never be indistinguishable.
    store.record_telemetry("j1", -26.0, 28.0, source="corridor", recorded_at=1000.0)
    store.record_telemetry("j1", -27.0, 27.0, source="passenger", recorded_at=1001.0)
    assert [p.source for p in store.recent_telemetry("j1")] == ["corridor", "passenger"]


def test_corridor_is_longer_than_the_straight_line_between_its_endpoints(store):
    """
    The polyline through Kimberley and De Aar is necessarily longer than the
    1,310km great-circle distance from Pretoria to Cape Town. If these came
    out equal, the cumulative-distance maths would be summing the wrong pair
    of stations and the ETA would be measuring the wrong thing.
    """
    direct = haversine_km(
        PRETORIA_TO_CAPE_TOWN[0].latitude,
        PRETORIA_TO_CAPE_TOWN[0].longitude,
        PRETORIA_TO_CAPE_TOWN[-1].latitude,
        PRETORIA_TO_CAPE_TOWN[-1].longitude,
    )
    assert direct == pytest.approx(1310, abs=15)
    assert store.total_km() > direct


def test_haversine_km_known_distance():
    # Pretoria to Cape Town as the crow flies. Checks the unit conversion
    # from the metres-returning geofence helper.
    assert haversine_km(-25.7479, 28.2293, -33.9222, 18.4264) == pytest.approx(1310, abs=15)


def test_project_on_segment_lands_on_the_midpoint():
    # Inputs are (longitude, latitude) pairs. A->B runs east along the
    # equator; P sits 1 degree north of its midpoint, so it projects to
    # t=0.5 at a perpendicular distance of one degree of latitude.
    t, distance, lat, lon = _project_on_segment(1.0, 1.0, 0.0, 0.0, 2.0, 0.0)
    assert t == pytest.approx(0.5, abs=0.01)
    assert distance == pytest.approx(111_320, rel=0.01)
    assert lat == pytest.approx(0.0, abs=0.001)
    assert lon == pytest.approx(1.0, abs=0.001)


def test_project_on_segment_returns_latitude_before_longitude():
    # The axis order is the single easiest thing to get wrong here, and
    # getting it wrong produces a valid-looking point on the wrong side of
    # the country rather than an error.
    _, _, lat, lon = _project_on_segment(1.0, 1.0, 0.0, 0.0, 2.0, 0.0)
    assert lat == pytest.approx(0.0, abs=0.001)   # the segment is on the equator
    assert lon == pytest.approx(1.0, abs=0.001)   # the projection is halfway east


def test_project_on_segment_clamps_beyond_the_ends():
    # A point past B clamps to t=1 rather than extrapolating off the end.
    t, _, _, _ = _project_on_segment(5.0, 0.0, 0.0, 0.0, 2.0, 0.0)
    assert t == 1.0


def test_seeding_is_idempotent(store):
    # ensure_schema() runs on every connect, so a restart must not duplicate
    # stations or change the corridor's measured length.
    before = store.total_km()
    store.ensure_schema()
    store.ensure_schema()
    assert len(store.corridor_nodes(refresh=True)) == len(PRETORIA_TO_CAPE_TOWN)
    assert store.total_km() == pytest.approx(before)
