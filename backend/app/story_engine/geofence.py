"""
Geofence-triggered story engine — the core proof-of-concept behind the
TRL 3 claim in README.md.

Given a rider's current GPS position (real, in Companion Mode; simulated,
in Explorer Mode), this determines which waypoint's story should trigger,
based on proximity along the real Pretoria-Cape Town route.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.story_engine.route import EARTH_RADIUS_METERS, PRETORIA_TO_CAPE_TOWN, Waypoint

# How close a rider needs to be to a waypoint's coordinates before its story
# triggers. Real stations sprawl a bit (yards, platforms, approach roads),
# so this is deliberately generous rather than pinpoint-precise.
DEFAULT_TRIGGER_RADIUS_METERS = 5_000


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class StoryTrigger:
    waypoint: Waypoint
    distance_meters: float


def nearest_waypoint(current_lat: float, current_lon: float) -> Waypoint:
    """Return the waypoint on the route closest to the given position."""
    return min(
        PRETORIA_TO_CAPE_TOWN,
        key=lambda w: haversine_meters(current_lat, current_lon, w.latitude, w.longitude),
    )



def find_triggered_waypoint(
    current_lat: float,
    current_lon: float,
    trigger_radius_meters: float = DEFAULT_TRIGGER_RADIUS_METERS,
) -> StoryTrigger | None:
    """
    Return the nearest waypoint whose story should trigger for a rider at
    (current_lat, current_lon), or None if the rider isn't within range of
    any waypoint on the route.

    If a rider is within range of more than one waypoint (unlikely given
    real inter-station distances, but possible near a dense cluster), the
    closest one wins.
    """
    candidates = []
    for waypoint in PRETORIA_TO_CAPE_TOWN:
        distance = haversine_meters(current_lat, current_lon, waypoint.latitude, waypoint.longitude)
        if distance <= trigger_radius_meters:
            candidates.append(StoryTrigger(waypoint=waypoint, distance_meters=distance))

    if not candidates:
        return None

    return min(candidates, key=lambda c: c.distance_meters)


def next_waypoint_after(waypoint_id: str) -> Waypoint | None:
    """
    Given the id of the waypoint a rider just triggered, return the next
    waypoint south along the route — used to pre-cache the next story pack
    for offline playback before connectivity drops (e.g. through the Karoo).
    """
    ids = [w.id for w in PRETORIA_TO_CAPE_TOWN]
    try:
        idx = ids.index(waypoint_id)
    except ValueError:
        return None
    if idx + 1 >= len(PRETORIA_TO_CAPE_TOWN):
        return None
    return PRETORIA_TO_CAPE_TOWN[idx + 1]


def route_progress_fraction(current_lat: float, current_lon: float) -> float:
    """
    Estimate how far along the Pretoria -> Cape Town route a rider is, as a
    fraction in [0, 1], by finding the nearest waypoint and using its
    position in the ordered route list. Used to animate the train's icon
    position on the Explorer/Companion Mode map.

    This is a coarse approximation (nearest-waypoint, not true along-track
    distance) — sufficient for an animated map at MVP fidelity, not for
    precision navigation.
    """
    nearest = nearest_waypoint(current_lat, current_lon)
    idx = PRETORIA_TO_CAPE_TOWN.index(nearest)
    return idx / (len(PRETORIA_TO_CAPE_TOWN) - 1)
