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
not town centroids) — see the is_approximate flag on each waypoint.

Cultural and tourism metadata
-----------------------------
Every waypoint carries a cultural block describing the local attractions,
indigenous stories, historical waypoints, and cultural touchpoints the
brief asks us to surface. This is the data the story engine, the guide,
and the map popups all draw from — one source of truth so a heritage site
cannot be described differently in three places.
"""

from __future__ import annotations
from dataclasses import dataclass, field

# Shared geospatial constants — defined once here so geofence.py and
# live_share.py cannot drift apart on the physical values they assume.
EARTH_RADIUS_METERS = 6_371_000
METERS_PER_DEGREE_LATITUDE = 111_320


@dataclass(frozen=True)
class CulturalMetadata:
    """Local attractions, stories, and touchpoints for one station.

    Fields are deliberately optional: not every stop has a museum, and not
    every museum has an audio guide. The story engine composes what exists
    rather than inventing gaps.
    """

    summary: str = ""
    heritage_sites: tuple[str, ...] = ()
    cultural_touchpoints: tuple[str, ...] = ()
    indigenous_stories: tuple[str, ...] = ()
    local_cuisine: tuple[str, ...] = ()
    festivals: tuple[str, ...] = ()
    visitor_notes: str = ""


@dataclass(frozen=True)
class Waypoint:
    id: str
    name: str
    latitude: float
    longitude: float
    story_theme: str
    is_approximate: bool = False
    province: str = ""
    cultural: CulturalMetadata = field(default_factory=CulturalMetadata)


# Ordered north (Pretoria) to south (Cape Town).
# The Free State is included explicitly — the brief names it as a province
# the corridor must cover, and the earlier draft skipped it entirely.
PRETORIA_TO_CAPE_TOWN: list[Waypoint] = [
    Waypoint(
        id="pretoria",
        name="Pretoria",
        latitude=-25.7479,
        longitude=28.2293,
        story_theme="Journey start: Union Buildings, jacaranda season, and the old Capital Park railway workshops.",
        is_approximate=True,
        province="Gauteng",
        cultural=CulturalMetadata(
            summary="South Africa's administrative capital, famous for its purple jacaranda trees and the Voortrekker Monument.",
            heritage_sites=("Union Buildings", "Voortrekker Monument", "Capital Park Station"),
            cultural_touchpoints=("Pretoria Art Museum", "Jacaranda City Festival"),
            indigenous_stories=("The Mamelodi township's role in the anti-apartheid struggle.",),
            local_cuisine=("Biltong and boerewors from Capital Park vendors",),
            festivals=("Jacaranda Day, every November",),
            visitor_notes="Free entry to the Union Buildings; jacarandas peak in late October.",
        ),
    ),
    Waypoint(
        id="johannesburg_park",
        name="Johannesburg (Park Station)",
        latitude=-26.1972,
        longitude=28.0419,
        story_theme="Gold-rush origins of Johannesburg and the historic Park Station terminus.",
        province="Gauteng",
    ),
    Waypoint(
        id="kimberley",
        name="Kimberley",
        latitude=-28.7353,
        longitude=24.7697,
        story_theme="The 1870s diamond rush, the Big Hole, and the town that built De Beers.",
        province="Northern Cape",
    ),
    Waypoint(
        id="bloemfontein",
        name="Bloemfontein",
        latitude=-29.0852,
        longitude=26.1596,
        story_theme="Judicial capital of South Africa and the heart of the Free State — the National Women's Monument and the Anglo-Boer War concentration camp memorial.",
        is_approximate=True,
        province="Free State",
        cultural=CulturalMetadata(
            summary="The judicial capital of South Africa, in the middle of the Free State. Known for its rose-growing industry and the Naval Hill viewpoint.",
            heritage_sites=("National Women's Monument", "Naval Hill", "Bloemfontein National Museum"),
            cultural_touchpoints=("Free State Zulu Community", "Rose Valley Festival"),
            indigenous_stories=("The Free State's role in the Anglo-Boer War and the story of the Basotho people.",),
            local_cuisine=("Potjiekos and braai from the surrounding townships",),
            festivals=("Bloemfontein Rose Festival, every October",),
            visitor_notes="Naval Hill offers a panoramic view of the city and is home to a small game reserve.",
        ),
    ),
    Waypoint(
        id="de_aar",
        name="De Aar",
        latitude=-30.6508,
        longitude=24.0133,
        story_theme="The great Karoo rail junction — where lines to Cape Town, Port Elizabeth, and Namibia once met.",
        province="Northern Cape",
    ),
    Waypoint(
        id="beaufort_west",
        name="Beaufort West",
        latitude=-32.3568,
        longitude=22.5811,
        story_theme="The Karoo's oldest town and gateway to the Karoo National Park.",
        is_approximate=True,
        province="Western Cape",
    ),
    Waypoint(
        id="matjiesfontein",
        name="Matjiesfontein",
        latitude=-33.2167,
        longitude=20.5833,
        story_theme="A perfectly preserved Victorian-era Karoo refreshment stop, still lit by gas lamps.",
        is_approximate=True,
        province="Western Cape",
    ),
    Waypoint(
        id="worcester",
        name="Worcester",
        latitude=-33.6464,
        longitude=19.4487,
        story_theme="Gateway to the Cape Winelands and the dramatic Hex River Valley mountain pass.",
        province="Western Cape",
    ),
    Waypoint(
        id="cape_town",
        name="Cape Town",
        latitude=-33.9222,
        longitude=18.4264,
        story_theme="Journey's end: Table Mountain, the Atlantic, and 1,600km behind you.",
        province="Western Cape",
    ),
]

# Every province the corridor touches, in the order a northbound-to-southbound
# rider first enters them. Used by eta.py to drive the "you have now entered
# the Karoo" milestone that the Journey Guardian pushes to a family link.
CORRIDOR_PROVINCES: list[str] = []
for _waypoint in PRETORIA_TO_CAPE_TOWN:
    if _waypoint.province and (not CORRIDOR_PROVINCES or CORRIDOR_PROVINCES[-1] != _waypoint.province):
        CORRIDOR_PROVINCES.append(_waypoint.province)


def get_waypoint(waypoint_id: str) -> Waypoint | None:
    return next((w for w in PRETORIA_TO_CAPE_TOWN if w.id == waypoint_id), None)
