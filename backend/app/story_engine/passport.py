"""
Digital journey passport — a stamp for every stop a journey actually reaches.

What it is
----------
A paper ticket used to be the only record that someone had made the trip.
The passport is the modern equivalent: one stamp per waypoint the journey's
own telemetry shows it passed, kept server-side and attached to the journey
rather than to a device.

Why it is derived, not recorded
-------------------------------
Stamps are computed from the journey's persisted position history, not
posted by a client. That is deliberate: a client that posts "I reached
Kimberley" is a client that can be lied to, and this is the same product
that refuses to invent an ETA. If the corridor never reported a position
within a stamp radius of a station, the passenger does not get that stamp —
and re-posting cannot change it.

Consequence worth stating plainly: a journey that only starts reporting
telemetry partway down the line gets a passport with a gap in it, not a
backfilled one. That is the honest answer, and it is the same trade the ETA
makes.

No AI anywhere in this path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.story_engine import spatial
from app.story_engine.geofence import haversine_meters
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN, Waypoint

# How close a journey's reported position must be to a station for that
# station to count as reached. Wider than the story trigger radius (5km),
# because a stamp should not be lost to a slightly-off GPS fix on a train
# that has already passed — but far narrower than the ~250km gaps between
# stations, so a train in the middle of the Karoo collects nothing.
STAMP_RADIUS_METERS = 25_000.0

# A station only counts if the journey actually stopped or passed through it.
# Sampled from persisted telemetry, so a journey whose feed merely clipped
# the edge of the radius while heading somewhere else is filtered by
# requiring the closest approach to be within the radius.
MAX_TELEMETRY_POINTS_SCANNED = 5_000


@dataclass(frozen=True)
class Stamp:
    """One station reached by one journey."""

    waypoint_id: str
    name: str
    province: str
    stamped_at: float
    distance_meters: float
    source: str
    ordinal: int

    def as_dict(self) -> dict:
        return {
            "waypoint_id": self.waypoint_id,
            "name": self.name,
            "province": self.province,
            "stamped_at": self.stamped_at,
            "distance_meters": round(self.distance_meters, 1),
            "source": self.source,
            "ordinal": self.ordinal,
        }


def _route_order() -> dict[str, int]:
    return {w.id: index for index, w in enumerate(PRETORIA_TO_CAPE_TOWN)}


def build_passport(journey_id: str, now: float | None = None) -> dict:
    """
    Compute the passport for a journey from its persisted position history.

    Returns the stamps in route order plus completion against the whole
    corridor, so the UI can show "6 of 8 stops" without a second request.
    """
    now = now if now is not None else time.time()
    points = spatial.spatial_store.recent_telemetry(
        journey_id, limit=MAX_TELEMETRY_POINTS_SCANNED
    )

    # Closest approach to every station across the whole feed, kept as
    # (distance, point) so a stamp can cite the report that justified it.
    best: dict[str, tuple[float, object]] = {}
    for point in points:
        for waypoint in PRETORIA_TO_CAPE_TOWN:
            distance = haversine_meters(
                point.latitude, point.longitude, waypoint.latitude, waypoint.longitude
            )
            current = best.get(waypoint.id)
            if current is None or distance < current[0]:
                best[waypoint.id] = (distance, point)

    order = _route_order()
    stamps: list[Stamp] = []
    for waypoint in PRETORIA_TO_CAPE_TOWN:
        entry = best.get(waypoint.id)
        if entry is None or entry[0] > STAMP_RADIUS_METERS:
            continue
        distance, point = entry
        stamps.append(
            Stamp(
                waypoint_id=waypoint.id,
                name=waypoint.name,
                province=waypoint.province,
                stamped_at=point.recorded_at,
                distance_meters=distance,
                source=point.source,
                ordinal=order[waypoint.id],
            )
        )

    total = len(PRETORIA_TO_CAPE_TOWN)
    provinces = []
    for stamp in stamps:
        if stamp.province and (not provinces or provinces[-1] != stamp.province):
            provinces.append(stamp.province)

    if not stamps:
        coverage_note = (
            f"No corridor report has come within {int(STAMP_RADIUS_METERS / 1000)}km "
            "of a station yet, so there is nothing to stamp."
        )
    else:
        # A gap at the *start* of the route means the feed began after the
        # train had already left — which is a different situation from a gap
        # in the middle, and worth distinguishing rather than describing with
        # one vague sentence.
        first_ordinal = min(s.ordinal for s in stamps)
        missed_before = first_ordinal
        if missed_before > 0:
            earliest = PRETORIA_TO_CAPE_TOWN[0].name
            coverage_note = (
                f"This journey's position feed began at {stamps[0].name}, so "
                f"{missed_before} earlier stop(s) — starting at {earliest} — are unstamped. "
                "A stamp is only issued against a corridor position report."
            )
        else:
            coverage_note = "Every station up to the last stamped one is backed by a corridor position report."

    return {
        "journey_id": journey_id,
        "issued_at": now,
        "stamps": [s.as_dict() for s in stamps],
        "stamps_earned": len(stamps),
        "stamps_total": total,
        "completion": round(len(stamps) / total, 3) if total else 0.0,
        "provinces_visited": provinces,
        "complete": len(stamps) == total,
        "coverage_note": coverage_note,
    }


def stamp_for_waypoint(journey_id: str, waypoint_id: str) -> dict | None:
    """The passport's stamp for one station, or None if not reached."""
    for stamp in build_passport(journey_id)["stamps"]:
        if stamp["waypoint_id"] == waypoint_id:
            return stamp
    return None
