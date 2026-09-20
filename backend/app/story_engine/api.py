"""
Integrated journey API.

This is the piece that moves the project from TRL 3 (isolated, tested
components) to TRL 4 (components integrated and validated together in a
lab environment): a single running service that takes a GPS position,
runs it through the geofence engine against the real route, and returns
a human-reviewed story — with no manual wiring, no mocked boundaries
between modules, and no AI call anywhere in the request path.

`backend/tests/test_integration.py` exercises this exact app object
end-to-end via FastAPI's TestClient, which is what makes this a genuine
integration test rather than another unit test in a trenchcoat.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.story_engine.content_store import get_story, get_pois
from app.story_engine.geofence import find_triggered_waypoint, route_progress_fraction
from app.story_engine.live_share import is_valid_rider_id, live_position_store
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

app = FastAPI(title="Kasi Compass — Train Journey Mapper (lab integration)")

# Same UUID shape as live_share.RIDER_ID_PATTERN, exposed as a plain pattern
# string so Pydantic can validate it as part of the request schema.
UUID_RIDER_ID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Frontend (GitHub Pages) and backend (Render) are deployed as separate
# origins, so the browser enforces CORS on every request between them.
# Without this, the deployed frontend gets a silent fetch failure — it
# still works on localhost (same-origin-ish over different ports is also
# blocked by browsers, actually, but a lot of local dev setups relax this
# via browser flags/extensions people forget they have on) which is why
# this gap can go unnoticed until someone opens the *deployed* site.
#
# CORS_ALLOWED_ORIGINS: comma-separated list, e.g.
#   "https://<org>.github.io,http://localhost:3000"
# Defaults to allowing any origin so local dev and first deploys aren't
# blocked out of the box — set this explicitly once you know your real
# GitHub Pages URL, so production isn't wide open.
_cors_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
_allowed_origins = [
    origin.strip()
    for origin in (_cors_raw.split(",") if _cors_raw else ["*"])
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JourneyPositionResponse(BaseModel):
    triggered: bool
    waypoint_id: str | None = None
    waypoint_name: str | None = None
    distance_meters: float | None = None
    route_progress_fraction: float
    story_text: str | None = None
    story_source: str | None = None


def _validate_coordinates(lat: float, lon: float) -> None:
    """Reject coordinates that cannot be a real geographic position.

    Without this, a client sending lat=9999 would silently receive a
    "no trigger" response rather than a clear error.
    """
    if not -90.0 <= lat <= 90.0:
        raise HTTPException(status_code=422, detail=f"lat must be between -90 and 90, got {lat}")
    if not -180.0 <= lon <= 180.0:
        raise HTTPException(status_code=422, detail=f"lon must be between -180 and 180, got {lon}")

@app.get("/journey/position", response_model=JourneyPositionResponse)
def journey_position(lat: float, lon: float, language: str = "en") -> JourneyPositionResponse:
    """
    Given a rider's current position (real GPS in Companion Mode, or a
    simulated position scrubbed along the route in Explorer Mode), return
    whichever waypoint's story should be showing right now.
    """
    _validate_coordinates(lat, lon)

    trigger = find_triggered_waypoint(lat, lon)
    progress = route_progress_fraction(lat, lon)

    if trigger is None:
        return JourneyPositionResponse(triggered=False, route_progress_fraction=progress)

    story = get_story(trigger.waypoint.id, language_code=language)

    return JourneyPositionResponse(
        triggered=True,
        waypoint_id=trigger.waypoint.id,
        waypoint_name=trigger.waypoint.name,
        distance_meters=round(trigger.distance_meters, 1),
        route_progress_fraction=progress,
        story_text=story.text if story else None,
        story_source=story.reviewed_by if story else None,
    )


@app.get("/journey/route")
def journey_route() -> list[dict]:
    """Return the full ordered waypoint list — what the frontend map renders."""
    return [
        {"id": w.id, "name": w.name, "lat": w.latitude, "lon": w.longitude}
        for w in PRETORIA_TO_CAPE_TOWN
    ]


@app.get("/journey/pois")
def journey_pois(waypoint_id: str) -> list[dict]:
    """Return nearby shops, markets, fuel, parking, and tourist sites for a stop."""
    return get_pois(waypoint_id)


class RiderIdQuery(BaseModel):
    # UUID-shaped and nothing more — see live_share.py's module docstring
    # for why rider_id is deliberately opaque (no name, no session, no
    # link to anything else about the rider).
    #
    # The pattern validator makes the UUID shape part of the request schema,
    # so a malformed 36-character id is rejected with a 422 at validation
    # time rather than slipping past a length-only check and only failing
    # later in is_valid_rider_id.
    rider_id: str = Field(pattern=UUID_RIDER_ID_PATTERN)

    @field_validator("rider_id")
    @classmethod
    def _check_rider_id(cls, value: str) -> str:
        if not is_valid_rider_id(value):
            raise ValueError("rider_id must be a UUID")
        return value


class SharePositionRequest(RiderIdQuery):
    lat: float
    lon: float


class SharePositionResponse(BaseModel):
    active_riders: int


class SharedRiderPosition(BaseModel):
    rider_id: str
    lat: float
    lon: float
    seconds_ago: float


def _validate_rider_id(rider_id: str) -> None:
    if not is_valid_rider_id(rider_id):
        raise HTTPException(status_code=422, detail="rider_id must be a UUID")


@app.post("/journey/share-position", response_model=SharePositionResponse)
def share_position(payload: SharePositionRequest) -> SharePositionResponse:
    """
    Opt-in only: the frontend calls this exclusively when a rider has
    explicitly turned on position sharing in Companion Mode. The stored
    position is fuzzed to a ~150m grid cell before it ever touches memory
    — see live_share.fuzz_coordinate. Nothing here is written to disk.
    """
    _validate_rider_id(payload.rider_id)
    _validate_coordinates(payload.lat, payload.lon)

    count = live_position_store.share_position(payload.rider_id, payload.lat, payload.lon)
    return SharePositionResponse(active_riders=count)


@app.get("/journey/shared-positions", response_model=list[SharedRiderPosition])
def shared_positions(
    rider_id: str = Query(pattern=UUID_RIDER_ID_PATTERN),
) -> list[SharedRiderPosition]:
    """
    Return other riders' current fuzzed positions, excluding the caller's
    own. A rider who has never called /journey/share-position simply isn't
    in the store — this endpoint works for any rider_id shape-valid enough
    to identify "not me" in the results, whether or not that rider is
    themselves sharing.
    """
    _validate_rider_id(rider_id)
    positions = live_position_store.get_other_positions(rider_id)
    return [SharedRiderPosition(**p) for p in positions]


@app.post("/journey/share-position/leave", status_code=204)
def leave_shared_position(payload: SharePositionRequest) -> None:
    """
    Explicit opt-out: removes a rider's position immediately rather than
    waiting for TTL expiry. Called when a rider turns sharing off, stops
    Companion Mode, or closes the tab (via navigator.sendBeacon, which
    only supports POST — hence this being a POST rather than DELETE).
    Reuses SharePositionRequest purely for its rider_id field; lat/lon are
    ignored here.
    """
    _validate_rider_id(payload.rider_id)
    live_position_store.leave(payload.rider_id)
