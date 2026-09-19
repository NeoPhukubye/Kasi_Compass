"""
Live position sharing between riders — the "see each other moving" half of
"tracks in real time" (the self-tracking half already existed via
navigator.geolocation.watchPosition in Companion Mode; this module is the
new part).

Design constraints, deliberately stricter than the geofence trigger engine,
because this is a different privacy category: geofence.py only ever checks
a rider's own position against 8 fixed, public station points, and nothing
is ever shared with anyone else. This module broadcasts one rider's live
location to other riders, which needs real guardrails:

- Opt-in only: a position is never shared unless the frontend explicitly
  calls share_position() — there is no passive collection anywhere in this
  module or api.py.
- Coarse, not exact: every position is snapped to a ~150m grid cell before
  it is stored (see fuzz_coordinate). Raw device GPS coordinates are never
  persisted, even in memory.
- Anonymous: riders are keyed by a random client-generated id (a UUID with
  no relationship to any identity, story-language preference, or other
  field). This module has no concept of a rider's name, device, or session
  beyond that opaque id.
- Non-persistent: positions live in a plain in-memory dict with a TTL and
  are never written to disk or an external store. Restarting the backend
  process clears all of it. This also means sharing does not scale past a
  single server process — acceptable for this project's current scope, and
  called out explicitly rather than silently assumed.
- Explicit leave: a rider can remove their own position immediately
  (leave_position) rather than waiting out the TTL, so turning sharing off
  in the UI actually takes effect right away.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

RIDER_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# How long a shared position stays visible to other riders after its last
# update. Long enough to survive a patchy-signal gap through the Karoo
# without every rider blinking in and out; short enough that someone who
# closed the tab or lost connection doesn't show up as a ghost for long.
POSITION_TTL_SECONDS = 45.0

# Grid resolution for coordinate fuzzing. Coarse enough that a shared
# position can't be used to pinpoint which seat or carriage someone is in;
# tight enough to still be a meaningful "another rider is near this stretch
# of the route" signal over an ~1,800km corridor.
FUZZ_PRECISION_METERS = 150.0

_EARTH_RADIUS_METERS = 6_371_000


def is_valid_rider_id(rider_id: str) -> bool:
    """Rider ids must be UUID-shaped — an opaque, client-generated token,
    never a name, session id, or anything else that could carry meaning."""
    return bool(RIDER_ID_PATTERN.match(rider_id))


def fuzz_coordinate(lat: float, lon: float, precision_meters: float = FUZZ_PRECISION_METERS) -> tuple[float, float]:
    """
    Snap a coordinate to the nearest `precision_meters` grid cell, rather
    than merely rounding decimal degrees (which distorts unevenly with
    latitude — rounding longitude the same way you round latitude makes
    the fuzzing radius shrink toward the poles).
    """
    lat_step_deg = precision_meters / 111_320
    fuzzed_lat = round(lat / lat_step_deg) * lat_step_deg

    # Longitude step is derived from the *fuzzed* latitude, not the raw
    # one — two nearby raw points that snap to the same latitude cell must
    # also get an identical longitude step, or they can round to adjacent
    # longitude cells near a boundary purely from float noise in `lat`.
    lon_step_deg = precision_meters / (111_320 * max(math.cos(math.radians(fuzzed_lat)), 1e-6))
    fuzzed_lon = round(lon / lon_step_deg) * lon_step_deg
    return fuzzed_lat, fuzzed_lon


@dataclass
class SharedPosition:
    lat: float
    lon: float
    last_seen: float  # time.time() of the most recent update


class LivePositionStore:
    """
    Plain in-memory store, single process only — see module docstring.
    Not thread-safe beyond what CPython's GIL gives dict operations for
    free, which is sufficient for a single-worker uvicorn/Render setup.
    """

    def __init__(self, ttl_seconds: float = POSITION_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._positions: dict[str, SharedPosition] = {}

    def _purge_expired(self, now: float) -> None:
        expired = [
            rider_id
            for rider_id, pos in self._positions.items()
            if now - pos.last_seen > self._ttl_seconds
        ]
        for rider_id in expired:
            del self._positions[rider_id]

    def share_position(self, rider_id: str, lat: float, lon: float, now: float | None = None) -> int:
        """Store a fuzzed position for rider_id, purge stale entries, and
        return the current count of active (non-expired) riders."""
        now = now if now is not None else time.time()
        self._purge_expired(now)

        fuzzed_lat, fuzzed_lon = fuzz_coordinate(lat, lon)
        self._positions[rider_id] = SharedPosition(lat=fuzzed_lat, lon=fuzzed_lon, last_seen=now)
        return len(self._positions)

    def get_other_positions(self, requesting_rider_id: str, now: float | None = None) -> list[dict]:
        """Return every active rider's fuzzed position except the caller's own."""
        now = now if now is not None else time.time()
        self._purge_expired(now)

        return [
            {
                "rider_id": rider_id,
                "lat": pos.lat,
                "lon": pos.lon,
                "seconds_ago": round(now - pos.last_seen, 1),
            }
            for rider_id, pos in self._positions.items()
            if rider_id != requesting_rider_id
        ]

    def leave(self, rider_id: str) -> bool:
        """Remove a rider's position immediately (explicit opt-out), rather
        than waiting for TTL expiry. Returns True if a position was removed."""
        return self._positions.pop(rider_id, None) is not None

    def active_count(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        self._purge_expired(now)
        return len(self._positions)


# Single shared instance for the running process — mirrors how
# content_store.py's STORY_CONTENT is a single module-level store rather
# than something the API layer constructs per-request.
live_position_store = LivePositionStore()
