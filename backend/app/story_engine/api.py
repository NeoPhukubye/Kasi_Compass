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

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.story_engine.content_store import get_story, get_pois
from app.story_engine.geofence import find_triggered_waypoint, route_progress_fraction
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

app = FastAPI(title="Kasi Compass — Train Journey Mapper (lab integration)")

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
