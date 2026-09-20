"""
Route data for the Pretoria - Cape Town rail corridor.

Waypoints and their approximate real-world coordinates are based on the
actual stations served by long-distance rail on this corridor (Shosholoza
Meyl's Johannesburg-Cape Town route via Kimberley, extended north to
Pretoria; the same corridor run today by Rovos Rail and the Blue Train).

Coordinates for major stations (Kimberley, De Aar, Worcester, Cape Town)
are sourced from published station records. Coordinates for the remaining
waypoints are town-center approximations suitable for an MVP geofence demo
(a production system would source these from surveyed station locations,
not town centroids) — see the `is_approximate` flag on each waypoint.
"""

from __future__ import annotations
from dataclasses import dataclass
# Shared geospatial constants — defined once here so geofence.py and
# live_share.py can't drift apart on the physical values they assume.
EARTH_RADIUS_METERS = 6_371_000
METERS_PER_DEGREE_LATITUDE = 111_320
@dataclass(frozen=True)
class Waypoint:
    id: str
    name: str
    latitude: float
    longitude: float
    story_theme: str
    is_approximate: bool = False


# Ordered north (Pretoria) to south (Cape Town).
PRETORIA_TO_CAPE_TOWN: list[Waypoint] = [
    Waypoint(
        id="pretoria",
        name="Pretoria",
        latitude=-25.7479,
        longitude=28.2293,
        story_theme="Journey's start: Union Buildings, jacaranda season, and the old Capital Park railway workshops.",
        is_approximate=True,
    ),
    Waypoint(
        id="johannesburg_park",
        name="Johannesburg (Park Station)",
        latitude=-26.1972,
        longitude=28.0419,
        story_theme="Gold-rush origins of Johannesburg and the historic Park Station terminus.",
    ),
    Waypoint(
        id="kimberley",
        name="Kimberley",
        latitude=-28.7353,
        longitude=24.7697,
        story_theme="The 1870s diamond rush, the Big Hole, and the town that built De Beers.",
    ),
    Waypoint(
        id="de_aar",
        name="De Aar",
        latitude=-30.6508,
        longitude=24.0133,
        story_theme="The great Karoo rail junction — where lines to Cape Town, Port Elizabeth, and Namibia once met.",
    ),
    Waypoint(
        id="beaufort_west",
        name="Beaufort West",
        latitude=-32.3568,
        longitude=22.5811,
        story_theme="The Karoo's oldest town and gateway to the Karoo National Park.",
        is_approximate=True,
    ),
    Waypoint(
        id="matjiesfontein",
        name="Matjiesfontein",
        latitude=-33.2167,
        longitude=20.5833,
        story_theme="A perfectly preserved Victorian-era Karoo refreshment stop, still lit by gas lamps.",
        is_approximate=True,
    ),
    Waypoint(
        id="worcester",
        name="Worcester",
        latitude=-33.6464,
        longitude=19.4487,
        story_theme="Gateway to the Cape Winelands and the dramatic Hex River Valley mountain pass.",
    ),
    Waypoint(
        id="cape_town",
        name="Cape Town",
        latitude=-33.9222,
        longitude=18.4264,
        story_theme="Journey's end: Table Mountain, the Atlantic, and 1,600km behind you.",
    ),
]


def get_waypoint(waypoint_id: str) -> Waypoint | None:
    return next((w for w in PRETORIA_TO_CAPE_TOWN if w.id == waypoint_id), None)
