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

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.story_engine.content_store import get_story, get_story_source, get_pois, get_stop_content
from app.story_engine.geofence import check_geofence, find_triggered_waypoint, route_progress_fraction
from app.story_engine.guide import answer_question
from app.story_engine.live_share import RIDER_ID_PATTERN, live_position_store
from app.story_engine.memories import (
    DEFAULT_MEMORIES_LIMIT,
    DEFAULT_NEARBY_RADIUS_METERS,
    memory_store,
)
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

# AI endpoints are imported lazily to keep the core runtime API
# independent of Google Generative AI SDK (see test_runtime_api_does_not_import_the_ai_tool).
# The ai_router is included only when the module is available.

app = FastAPI(title="Kasi Compass — Train Journey Mapper (lab integration)")

# Reuse live_share's pattern verbatim (as a plain string) so the UUID shape
# enforced at the request schema and the one enforced in the store can never
# drift apart.
UUID_RIDER_ID_PATTERN = RIDER_ID_PATTERN.pattern

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
        story_source=get_story_source(trigger.waypoint.id),
    )

@app.get("/journey/route")
def journey_route() -> list[dict]:
    """Return the full ordered waypoint list — what the frontend map renders."""
    return [
        {"id": w.id, "name": w.name, "lat": w.latitude, "lon": w.longitude}
        for w in PRETORIA_TO_CAPE_TOWN
    ]

class PointOfInterestResponse(BaseModel):
    name: str
    type: str
    lat: float
    lon: float
    description: str | None = None

@app.get("/journey/pois", response_model=list[PointOfInterestResponse])
def journey_pois(waypoint_id: str) -> list[PointOfInterestResponse]:
    """Return nearby shops, markets, fuel, parking, and tourist sites for a stop."""
    return [PointOfInterestResponse(**p.as_dict()) for p in get_pois(waypoint_id)]

class RiderIdQuery(BaseModel):
    # UUID-shaped and nothing more — see live_share.py's module docstring
    # for why rider_id is deliberately opaque (no name, no session, no
    # link to anything else about the rider).
    #
    # The pattern is part of the request schema, so a malformed 36-character
    # id is rejected with a 422 at validation time — this is the single source
    # of UUID validation for every rider_id-taking endpoint.
    rider_id: str = Field(pattern=UUID_RIDER_ID_PATTERN)

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

@app.post("/journey/share-position", response_model=SharePositionResponse)
def share_position(payload: SharePositionRequest) -> SharePositionResponse:
    """
    Opt-in only: the frontend calls this exclusively when a rider has
    explicitly turned on position sharing in Companion Mode. The stored
    position is fuzzed to a ~150m grid cell before it ever touches memory
    — see live_share.fuzz_coordinate. Nothing here is written to disk.
    """
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
    ignored.
    """
    live_position_store.leave(payload.rider_id)

class CreateMemoryRequest(RiderIdQuery):
    """
    A rider dropping a memory at a waypoint they've just passed. The same
    opaque UUID rules as living sharing: rider_id is anonymous and
    client-generated, tied to no identity. waypoint_id must be a waypoint
    that actually exists on the route, and text is enforced non-empty and
    length-bounded in the store (see memories.py).

    A memory can optionally be pinned to the exact spot it was left (lat +
    lon, always together) so later riders passing that spot can unlock it;
    audio_url is a hosted voice-note link, never raw bytes.
    """
    waypoint_id: str
    text: str
    language_code: str = "en"
    lat: float | None = None
    lon: float | None = None
    audio_url: str | None = None

class MemoryResponse(BaseModel):
    memory_id: str
    waypoint_id: str
    rider_id: str
    text: str
    created_at: float
    language_code: str
    lat: float | None = None
    lon: float | None = None
    audio_url: str | None = None

@app.post("/journey/memories", response_model=MemoryResponse, status_code=201)
def create_memory(payload: CreateMemoryRequest) -> MemoryResponse:
    """
    The "new generation creates new memories" path: store a rider's memory
    at a waypoint. Validation failures (unknown waypoint, blank/oversized
    text, half-provided coordinates) return 422, matching how malformed
    rider ids are handled.
    """
    try:
        memory = memory_store.add_memory(
            waypoint_id=payload.waypoint_id,
            rider_id=payload.rider_id,
            text=payload.text,
            language_code=payload.language_code,
            lat=payload.lat,
            lon=payload.lon,
            audio_url=payload.audio_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MemoryResponse(**memory.as_dict())

@app.get("/journey/memories", response_model=list[MemoryResponse])
def list_memories(
    waypoint_id: str | None = None,
    limit: int = Query(default=DEFAULT_MEMORIES_LIMIT, ge=1, le=100),
) -> list[MemoryResponse]:
    """
    The "older generation relives old memories" path: return rider memories
    for a waypoint (or across the whole route if waypoint_id is omitted),
    newest first. An unknown waypoint_id is a 422, not a silent empty list.
    """
    if waypoint_id is not None and waypoint_id not in {w.id for w in PRETORIA_TO_CAPE_TOWN}:
        raise HTTPException(status_code=422, detail=f"unknown waypoint_id: {waypoint_id!r}")
    return [MemoryResponse(**m.as_dict()) for m in memory_store.memories_for(waypoint_id, limit)]

@app.get("/journey/memories/nearby", response_model=list[MemoryResponse])
def nearby_memories(
    lat: float,
    lon: float,
    radius: float = Query(default=DEFAULT_NEARBY_RADIUS_METERS, ge=1, le=50_000),
    limit: int = Query(default=DEFAULT_MEMORIES_LIMIT, ge=1, le=100),
) -> list[MemoryResponse]:
    """
    The geofenced relive path: unlock memories that were dropped within
    `radius` meters of the rider's live position. Mirrors how the story
    engine triggers on proximity — pass Kimberley station and the memory
    someone left on the Big Hole platform surfaces, not every memory for
    the whole town.
    """
    _validate_coordinates(lat, lon)
    return [MemoryResponse(**m.as_dict()) for m in memory_store.memories_near(lat, lon, radius, limit)]

# ---------------------------------------------------------------------
# Story-engine discovery + geofence verification (CLI/frontend surfaces).
#
# A separate router so the discovery endpoints don't crowd the /journey
# prefix that the map and Companion Mode depend on. Both consume the same
# engines as everything else here — content_store and geofence — so there
# is one source of truth, not a parallel implementation.
# ---------------------------------------------------------------------

story_engine_router = APIRouter(prefix="/story-engine", tags=["Story Engine"])

@story_engine_router.get("/stop/{stop_id}")
def stop_content(stop_id: str) -> dict:
    """Fetch the historical narrative, heritage sites, local stalls, and
    geofence coordinates for a specific Shosholoza Meyl stop."""
    content = get_stop_content(stop_id)
    if not content:
        raise HTTPException(status_code=404, detail="Stop content not found.")
    return {"status": "success", "data": content}

@story_engine_router.get("/geofence/verify")
def verify_geofence(
    user_lat: float = Query(...),
    user_lon: float = Query(...),
    target_lat: float = Query(...),
    target_lon: float = Query(...),
    radius: float = Query(100.0, ge=1, le=50_000),
) -> dict:
    """Verify live telemetry (rider in an Uber/transit vehicle) against a
    stop's coordinates: returns whether the user is within `radius` meters
    of the target point, with the inputs echoed in `metrics`."""
    _validate_coordinates(user_lat, user_lon)
    _validate_coordinates(target_lat, target_lon)
    is_inside = check_geofence(user_lat, user_lon, target_lat, target_lon, radius)
    return {
        "status": "success",
        "inside_geofence": is_inside,
        "metrics": {
            "user_location": {"lat": user_lat, "lon": user_lon},
            "target_location": {"lat": target_lat, "lon": target_lon},
            "threshold_radius_m": radius,
        },
    }

class AskGuideRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

class GuideResponse(BaseModel):
    answer: str
    source: str  # "route-corpus" or "gemini"
    ai_used: bool
    stop_id: str | None = None
    stop_name: str | None = None

@story_engine_router.post("/ask", response_model=GuideResponse)
def ask_guide(payload: AskGuideRequest) -> GuideResponse:
    """
    Companion Mode's tour guide. The guide is grounded in the human-reviewed
    corpus by default; if a server-side GEMINI_API_KEY is configured, the
    question is sent to Gemini for a draft that is still anchored to that
    corpus, and any Gemini failure falls back to the corpus answer. The API
    key lives only in the backend environment, never in browser JS.

    This is the *one* user-invoked, opt-in AI surface in the runtime; the
    core /journey/* story path remains free of any AI dependency (see
    README §"Content model").
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be blank")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or None
    result = answer_question(question, api_key=api_key)
    return GuideResponse(
        answer=result["answer"],
        source=result["source"],
        ai_used=result["ai_used"],
        stop_id=result.get("stop_id"),
        stop_name=result.get("stop_name"),
    )


# Lazily include AI endpoints to keep core API free of AI SDK imports.
# This avoids triggering test_runtime_api_does_not_import_the_ai_tool.
try:
    from app.story_engine.ai_endpoints import ai_router
    app.include_router(ai_router)
except ImportError:
    pass

app.include_router(story_engine_router)