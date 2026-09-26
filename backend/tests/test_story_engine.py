"""
Tests for the geofence story engine.

Run with: pytest backend/tests/test_story_engine.py
"""

from app.story_engine.geofence import (
    check_geofence,
    find_triggered_waypoint,
    haversine_meters,
    next_waypoint_after,
    route_progress_fraction,
)
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN, get_waypoint


def test_route_has_expected_waypoints_in_order():
    ids = [w.id for w in PRETORIA_TO_CAPE_TOWN]
    assert ids == [
        "pretoria",
        "johannesburg_park",
        "kimberley",
        "bloemfontein",
        "de_aar",
        "beaufort_west",
        "matjiesfontein",
        "worcester",
        "cape_town",
    ]


def test_get_waypoint_found_and_not_found():
    assert get_waypoint("kimberley").name == "Kimberley"
    assert get_waypoint("narnia") is None


def test_haversine_pretoria_to_cape_town_is_roughly_correct():
    pretoria = get_waypoint("pretoria")
    cape_town = get_waypoint("cape_town")
    distance_km = haversine_meters(
        pretoria.latitude, pretoria.longitude, cape_town.latitude, cape_town.longitude
    ) / 1000
    # Straight-line distance is shorter than the ~1,600km rail distance
    # (which winds through Kimberley and the Karoo) - expect roughly 1,200km.
    assert 1100 < distance_km < 1350


def test_find_triggered_waypoint_at_exact_station_coordinates():
    kimberley = get_waypoint("kimberley")
    trigger = find_triggered_waypoint(kimberley.latitude, kimberley.longitude)
    assert trigger is not None
    assert trigger.waypoint.id == "kimberley"
    assert trigger.distance_meters < 1.0


def test_find_triggered_waypoint_within_radius_but_not_exact():
    kimberley = get_waypoint("kimberley")
    # ~0.02 degrees latitude is roughly 2.2km - well within the 5km default radius.
    trigger = find_triggered_waypoint(kimberley.latitude + 0.02, kimberley.longitude)
    assert trigger is not None
    assert trigger.waypoint.id == "kimberley"


def test_find_triggered_waypoint_returns_none_far_from_any_waypoint():
    # Middle of the Atlantic - nowhere near this rail corridor.
    trigger = find_triggered_waypoint(-30.0, 0.0)
    assert trigger is None


def test_next_waypoint_after_sequences_correctly():
    assert next_waypoint_after("kimberley").id == "bloemfontein"
    assert next_waypoint_after("cape_town") is None
    assert next_waypoint_after("not_a_real_id") is None


def test_route_progress_fraction_endpoints():
    pretoria = get_waypoint("pretoria")
    cape_town = get_waypoint("cape_town")
    assert route_progress_fraction(pretoria.latitude, pretoria.longitude) == 0.0
    assert route_progress_fraction(cape_town.latitude, cape_town.longitude) == 1.0


def test_route_progress_fraction_midpoint_roughly_central():
    de_aar = get_waypoint("de_aar")
    fraction = route_progress_fraction(de_aar.latitude, de_aar.longitude)
    assert 0.3 < fraction < 0.7


def test_check_geofence_inside_and_outside_radius():
    # ~0.01deg of latitude is ~1.1km.
    assert check_geofence(-28.7353, 24.7697, -28.7353, 24.7697, radius_meters=100.0) is True
    assert check_geofence(-28.7353, 24.7697, -28.7353 + 0.01, 24.7697, radius_meters=100.0) is False
    # A generous radius catches the same offset point.
    assert check_geofence(-28.7353, 24.7697, -28.7353 + 0.01, 24.7697, radius_meters=2_000.0) is True

def test_check_geofence_defaults_to_100m_bundle_radius():
    kimberley = get_waypoint("kimberley")
    # ~0.002deg latitude is ~223m — outside the 100m default radius.
    assert check_geofence(kimberley.latitude, kimberley.longitude,
                          kimberley.latitude + 0.002, kimberley.longitude) is False
