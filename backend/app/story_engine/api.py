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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.story_engine.content_store import get_story
from app.story_engine.geofence import find_triggered_waypoint, route_progress_fraction
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

app = FastAPI(title="Kasi Compass — Train Journey Mapper (lab integration)")


class JourneyPositionResponse(BaseModel):
    triggered: bool
    waypoint_id: str | None = None
    waypoint_name: str | None = None
    distance_meters: float | None = None
    route_progress_fraction: float
    story_text: str | None = None
    story_source: str | None = None


@app.get("/journey/position", response_model=JourneyPositionResponse)
def journey_position(lat: float, lon: float, language: str = "en") -> JourneyPositionResponse:
    """
    Given a rider's current position (real GPS in Companion Mode, or a
    simulated position scrubbed along the route in Explorer Mode), return
    whichever waypoint's story should be showing right now.
    """
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
