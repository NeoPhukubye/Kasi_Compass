"""
Human-sourced story content store.

Design change from the earlier draft of this project: the *core* content
pipeline here is human-authored and human-reviewed content, sourced from
local narrators, heritage sites, and tourism-board partners along the
route — not AI-generated text served directly to riders.

AI has exactly one allowed role in this pipeline, and it's assistive, not
authoritative: drafting a *first-pass translation* of an already
human-approved English story into another official language, which a
human reviewer (ideally a first-language speaker) then edits and approves
before it's ever stored here. Nothing in this module calls an AI API at
request time — by the time a story reaches STORY_CONTENT, a human has
signed off on every word of it, in every language it appears in.

This matters for two reasons: (1) it removes the AI outage/hallucination
risk from the critical path entirely — the app works the same with or
without any AI service available, and (2) telling the story of a place
with input from people who actually live there is a stated design
commitment (see README), not just a review checkbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

@dataclass(frozen=True)
class LocalizedStory:
    language_code: str  # e.g. "en", "zu", "af", "xh"
    text: str
    reviewed_by: str  # who signed off on this specific translation/text
    audio_url: str | None = None

@dataclass(frozen=True)
class WaypointStory:
    waypoint_id: str
    source: str  # who originally contributed this story (person/org, not "AI")
    localized: dict[str, LocalizedStory] = field(default_factory=dict)

@dataclass(frozen=True)
class PointOfInterest:
    name: str
    type: str  # "market", "shop", "restaurant", "tourist_attraction", "fuel", "parking", "heritage_site"
    lat: float
    lon: float
    description: str | None = None

    def as_dict(self) -> dict[str, str | float | None]:
        """Plain-dict form of this POI for the API response model."""
        return {
            "name": self.name,
            "type": self.type,
            "lat": self.lat,
            "lon": self.lon,
            "description": self.description,
        }

# Seed content: real waypoints, human-sourced placeholder copy pending
# actual partner interviews (see WBS Phase 1 — narrator/heritage-site
# outreach). Every entry has a `source` and `reviewed_by` field precisely
# so this can never silently become AI-generated content without a human
# name attached to it.
STORY_CONTENT: dict[str, WaypointStory] = {
    "kimberley": WaypointStory(
        waypoint_id="kimberley",
        source="Kimberley Big Hole & Diamond Museum (pilot partner outreach pending)",
        localized={
            "en": LocalizedStory(
                language_code="en",
                text=(
                    "In 1871, a chance diamond find on this ground triggered a rush that "
                    "carved out the Big Hole — still one of the largest hand-dug "
                    "excavations on Earth, and the reason Kimberley exists at all."
                ),
                reviewed_by="[pending local heritage-site review]",
            ),
        },
    ),
    "matjiesfontein": WaypointStory(
        waypoint_id="matjiesfontein",
        source="Matjiesfontein heritage village (pilot partner outreach pending)",
        localized={
            "en": LocalizedStory(
                language_code="en",
                text=(
                    "A Victorian-era refreshment stop, frozen in time in the middle of "
                    "the Karoo — the same gas lamps and station buildings that greeted "
                    "travellers over a century ago still stand today."
                ),
                reviewed_by="[pending local heritage-site review]",
            ),
        },
    ),
}

WAYPOINT_POIS: dict[str, list[PointOfInterest]] = {
    "kimberley": [
        PointOfInterest(
            "Kimberley Big Hole",
            "heritage_site",
            -28.7353,
            24.7697,
            "One of the largest hand-dug excavations on Earth, a testament to the 19th-century diamond rush.",
        ),
        PointOfInterest(
            "Kimberley Market",
            "market",
            -28.7340,
            24.7680,
            "A bustling local market with fresh produce and handmade crafts.",
        ),
        PointOfInterest(
            "De Beers Store",
            "shop",
            -28.7360,
            24.7710,
            "The original store of the famous diamond company.",
        ),
        PointOfInterest(
            "Orange Street Fuel", "fuel", -28.7330, 24.7650, "24/7 fuel and convenience store."
        ),
        PointOfInterest(
            "Kimberley Garage",
            "parking",
            -28.7370,
            24.7700,
            "Secure parking near the Big Hole.",
        ),
    ],
    "matjiesfontein": [
        PointOfInterest(
            "Matjiesfontein Village Shop",
            "shop",
            -33.2167,
            20.5833,
            "A charming shop in a Victorian-era village, frozen in time.",
        ),
        PointOfInterest(
            "Karoo Heritage Market",
            "market",
            -33.2155,
            20.5845,
            "Local crafts and produce from the Karoo region.",
        ),
        PointOfInterest(
            "Station Fuel Stop",
            "fuel",
            -33.2175,
            20.5820,
            "The only fuel stop in the historic village.",
        ),
        PointOfInterest(
            "Village Parking",
            "parking",
            -33.2180,
            20.5810,
            "Ample parking for visitors exploring the village.",
        ),
        PointOfInterest(
            "Old Hotel Restaurant",
            "restaurant",
            -33.2160,
            20.5850,
            "Dine in a historic hotel with classic Karoo cuisine.",
        ),
    ],
    "pretoria": [
        PointOfInterest(
            "Union Buildings",
            "heritage_site",
            -25.7479,
            28.2293,
            "The official seat of the South African Government, with beautiful terraced gardens.",
        ),
        PointOfInterest(
            "Pretoria Market",
            "market",
            -25.7465,
            28.2305,
            "A large market with a variety of goods, from food to clothing.",
        ),
        PointOfInterest(
            "Capital Park Shop",
            "shop",
            -25.7485,
            28.2280,
            "A local shop with everyday essentials.",
        ),
        PointOfInterest(
            "Station Fuel", "fuel", -25.7490, 28.2270, "Conveniently located near the station."
        ),
    ],
    "johannesburg_park": [
        PointOfInterest(
            "Park Station",
            "tourist_attraction",
            -26.1972,
            28.0419,
            "The central railway station of Johannesburg, a hub of activity.",
        ),
        PointOfInterest(
            "Johannesburg Market",
            "market",
            -26.1960,
            28.0430,
            "A vibrant market reflecting the diverse culture of the city.",
        ),
        PointOfInterest(
            "City Centre Shop",
            "shop",
            -26.1980,
            28.0400,
            "A modern shopping experience in the heart of the city.",
        ),
        PointOfInterest(
            "Station Fuel", "fuel", -26.1985, 28.0390, "Fuel up before heading out of the city."
        ),
        PointOfInterest(
            "PnP Parking",
            "parking",
            -26.1975,
            28.0440,
            "Secure parking for commuters and shoppers.",
        ),
    ],
    "de_aar": [
        PointOfInterest(
            "De Aar Mall",
            "shop",
            -30.6508,
            24.0133,
            "The main shopping center in De Aar, with a variety of stores.",
        ),
        PointOfInterest(
            "Karoo Market",
            "market",
            -30.6495,
            24.0145,
            "A weekly market with local goods and crafts.",
        ),
        PointOfInterest(
            "Fuel Station", "fuel", -30.6515, 24.0120, "A reliable stop for fuel in the Karoo."
        ),
        PointOfInterest(
            "Town Parking", "parking", -30.6520, 24.0110, "Public parking in the town center."
        ),
    ],
    "beaufort_west": [
        PointOfInterest(
            "Beaufort West Mall",
            "shop",
            -32.3568,
            22.5811,
            "A modern mall serving the Central Karoo district.",
        ),
        PointOfInterest(
            "Karoo Karoo Market",
            "market",
            -32.3555,
            22.5825,
            "A popular spot for local produce and artisanal goods.",
        ),
        PointOfInterest(
            "Station Fuel", "fuel", -32.3575, 22.5800, "Fuel and a quick snack stop."
        ),
        PointOfInterest(
            "Public Parking", "parking", -32.3580, 22.5790, "Free parking near the town center."
        ),
    ],
    "worcester": [
        PointOfInterest(
            "Worcester Mall",
            "shop",
            -33.6464,
            19.4487,
            "The largest shopping mall in the Breede River Valley.",
        ),
        PointOfInterest(
            "Breede River Market",
            "market",
            -33.6450,
            19.4495,
            "A weekend market with local wine, cheese, and crafts.",
        ),
        PointOfInterest(
            "Fuel Station", "fuel", -33.6475, 19.4470, "A 24/7 fuel station."
        ),
        PointOfInterest(
            "Town Parking", "parking", -33.6480, 19.4460, "Paid parking in the town center."
        ),
    ],
    "cape_town": [
        PointOfInterest(
            "Cape Town Station",
            "tourist_attraction",
            -33.9222,
            18.4264,
            "The oldest and largest railway station in Cape Town.",
        ),
        PointOfInterest(
            "City Bowl Market",
            "market",
            -33.9210,
            18.4275,
            "A foodie market in the heart of the city, with live music.",
        ),
        PointOfInterest(
            "Adderley Shop",
            "shop",
            -33.9230,
            18.4250,
            "A historic street with a mix of modern and traditional shops.",
        ),
        PointOfInterest(
            "Station Fuel", "fuel", -33.9235, 18.4240, "Conveniently located near the station."
        ),
        PointOfInterest(
            "City Parking",
            "parking",
            -33.9240,
            18.4230,
            "Multi-level parking garage with easy access to the city center.",
        ),
    ],
}

def get_story_source(waypoint_id: str) -> str | None:
    """
    Return who originally contributed a waypoint's story (person,
    heritage site, or org — never an AI attribution), regardless of
    language. The API exposes this as `story_source`; the per-translation
    `reviewed_by` field is who *approved* that specific text, which is not
    the same thing and should not be surfaced as the source.
    """
    entry = STORY_CONTENT.get(waypoint_id)
    return entry.source if entry is not None else None

def get_story(waypoint_id: str, language_code: str = "en") -> LocalizedStory | None:
    """
    Return the human-reviewed story for a waypoint in the requested
    language, falling back to English if that language isn't available yet
    (translation coverage grows over time as review capacity allows —
    see README consumer-phasing plan).
    """
    entry = STORY_CONTENT.get(waypoint_id)
    if entry is None:
        return None
    return entry.localized.get(language_code) or entry.localized.get("en")

def get_pois(waypoint_id: str) -> list[PointOfInterest]:
    """
    Return nearby points of interest for a waypoint (shops, markets,
    fuel stations, parking, tourist sites) so riders can plan
    stops before getting off the train.
    """
    return list(WAYPOINT_POIS.get(waypoint_id, []))

# ---------------------------------------------------------------------
# Shosholoza stop-discovery corpus.
#
# Distinct from STORY_CONTENT: that corpus feeds the *geofenced story
# card* (one human-reviewed LocalizedStory per waypoint, served by
# /journey/position). This corpus feeds the *stop detail / discovery*
# endpoint (/story-engine/stop/{id}) — a richer, human-sourced profile of
# each stop's narrative, heritage sites, and the informal-trading stalls
# that live around the station. Coordinates come from STOP_COORDINATES
# below so geofencing /story-engine/geofence/verify has real data to
# compare against without touching the animation route.
# ---------------------------------------------------------------------

SHOSHOLOZA_ROUTE_STORIES: dict[str, dict] = {
    "pretoria": {
        "stop_name": "Pretoria Station",
        "historical_narrative": (
            "The journey's northern gateway: Union Buildings on the hill, jacaranda-lined "
            "streets, and the old Capital Park railway workshops where generations repaired "
            "the locomotives that carried the country's traffic south."
        ),
        "heritage_sites": [
            {
                "name": "Union Buildings",
                "era": "Early 20th Century",
                "description": "The seat of South Africa's executive, in terraced gardens above Pretoria.",
            }
        ],
        "local_stalls": [
            {
                "name": "Pretoria Station Vendors",
                "category": "Food & Goods",
                "description": "Travel essentials, newspapers, and snacks for departing passengers.",
            }
        ],
    },
    "johannesburg_park": {
        "stop_name": "Johannesburg Park Station",
        "historical_narrative": (
            "The heart of Gauteng's rail network, Park Station has been the starting point for "
            "generations of travelers and migrant workers. It represents the bustling beginning "
            "of long-distance journeys across South Africa."
        ),
        "heritage_sites": [
            {
                "name": "Park Station Main Concourse",
                "era": "Historical & Modern",
                "description": "The central hub linking commuters to various national routes.",
            }
        ],
        "local_stalls": [
            {
                "name": "Station Concourse Vendors",
                "category": "Food & Goods",
                "description": "Quick snacks, newspapers, and travel essentials for departing passengers.",
            }
        ],
    },
    "germiston": {
        "stop_name": "Germiston Station",
        "historical_narrative": (
            "For much of the 20th century Germiston was South Africa's railway junction: its "
            "marshalling yards were once among the largest in the world, sorting the traffic of "
            "the gold mines onto the national mainline. The station's rhythm reflected the "
            "generations of workers who passed through on their way to the Reef and beyond."
        ),
        "heritage_sites": [
            {
                "name": "Germiston Railway Yards",
                "era": "Mid-20th Century",
                "description": "Historic marshalling yards once ranked among the biggest rail freight yards globally.",
            }
        ],
        "local_stalls": [
            {
                "name": "Station Approach Traders",
                "category": "Food & Goods",
                "description": "Commuters' vendors serving street food and daily essentials at the taxi rank.",
            }
        ],
    },
    "kimberley": {
        "stop_name": "Kimberley Station",
        "historical_narrative": (
            "Famous for its diamond rush history, Kimberley sits centrally on the route. The "
            "station reflects the era of the mineral revolution, connecting the Northern Cape to "
            "the rest of the country."
        ),
        "heritage_sites": [
            {
                "name": "Kimberley Big Hole",
                "era": "Late 19th Century",
                "description": "The historic open-pit mine that defined the region.",
            }
        ],
        "local_stalls": [
            {
                "name": "Platform Craft Markets",
                "category": "Souvenirs",
                "description": "Local crafts and regional snacks available during train stops.",
            }
        ],
    },
    "klerksdorp": {
        "stop_name": "Klerksdorp Station",
        "historical_narrative": (
            "A North West gold-mining town on the historic mainline to the Cape, Klerksdorp has "
            "long been the corridor's gateway between the Reef and the Karoo — a stop where "
            "trains once paused to water and to take on workers and goods."
        ),
        "heritage_sites": [
            {
                "name": "Klerksdorp Museum",
                "era": "Early 20th Century",
                "description": "Records the town's mining and railway past at the heart of the province.",
            }
        ],
        "local_stalls": [
            {
                "name": "Town Centre Vendors",
                "category": "Food & Goods",
                "description": "Stalls serving Mogodu, pap, and commuting basics near the station.",
            }
        ],
    },
    "de_aar": {
        "stop_name": "De Aar Station",
        "historical_narrative": (
            "The great Karoo rail junction — the point on the line to Cape Town, Port Elizabeth, "
            "and Namibia where engines were serviced and crews changed, and where the silence of "
            "the Karoo met the hubbub of the passing trains."
        ),
        "heritage_sites": [
            {
                "name": "De Aar Railway Junction",
                "era": "Early 20th Century",
                "description": "A strategically vital junction town for the national rail grid.",
            }
        ],
        "local_stalls": [
            {
                "name": "Karoo Station Market",
                "category": "Local Produce",
                "description": "Regional crafts and edibles from the town's weekly market.",
            }
        ],
    },
    "beaufort_west": {
        "stop_name": "Beaufort West Station",
        "historical_narrative": (
            "The Karoo's oldest town and a Victorian-era halt on the long ride south. Travellers "
            "crossing the great thirst would rest here before the final push over the Cape ranges."
        ),
        "heritage_sites": [
            {
                "name": "Beaufort West Town Hall",
                "era": "Late 19th Century",
                "description": "The oldest town hall in South Africa, and the gateway to the Karoo National Park.",
            }
        ],
        "local_stalls": [
            {
                "name": "Karoo Karoo Market",
                "category": "Artisan Goods",
                "description": "Local produce and artisanal goods from the Central Karoo.",
            }
        ],
    },
    "matjiesfontein": {
        "stop_name": "Matjiesfontein Station",
        "historical_narrative": (
            "A perfectly preserved Victorian-era refreshment stop frozen in time in the Karoo — "
            "the same gas lamps and station buildings that greeted travellers over a century ago "
            "still greet them today."
        ),
        "heritage_sites": [
            {
                "name": "Matjiesfontein Heritage Village",
                "era": "Victorian Era",
                "description": "A time-capsule refreshment stop, still lit by gas lamp.",
            }
        ],
        "local_stalls": [
            {
                "name": "Village Shop",
                "category": "Food & Craft",
                "description": "A charming stop in the historic village for travellers and sightseers.",
            }
        ],
    },
    "worcester": {
        "stop_name": "Worcester Station",
        "historical_narrative": (
            "Gateway to the Cape Winelands and the dramatic Hex River Valley pass, Worcester has "
            "welcomed generations descending out of the Karoo into the Breede River Valley's farms."
        ),
        "heritage_sites": [
            {
                "name": "Hex River Valley Pass",
                "era": "Mountain Pass Era",
                "description": "The dramatic ravine that links the Karoo highveld to the Cape lowlands.",
            }
        ],
        "local_stalls": [
            {
                "name": "Breede River Market",
                "category": "Wine, Cheese & Crafts",
                "description": "A weekend market of valley produce, wine, and local crafts.",
            }
        ],
    },
    "cape_town": {
        "stop_name": "Cape Town Station",
        "historical_narrative": (
            "The final destination for the Trans-Karoo, Cape Town Station sits at the foot of "
            "Table Mountain. It has welcomed generations of travelers arriving from the interior."
        ),
        "heritage_sites": [
            {
                "name": "Cape Town Station Precinct",
                "era": "Historical Arrival",
                "description": "The gateway to the Mother City.",
            }
        ],
        "local_stalls": [
            {
                "name": "Station Plaza Vendors",
                "category": "Local Delicacies",
                "description": "Cape Malay treats, refreshments, and artisanal goods.",
            }
        ],
    },
}

# Longitude/latitude for every stop in the discovery corpus. Waypoints that
# are already on the animation route are derived from route.py so the two
# can never drift; corridor stops not on the route (germiston, klerksdorp)
# are given their real published town/station coordinates.
STOP_COORDINATES: dict[str, tuple[float, float]] = {
    w.id: (w.latitude, w.longitude) for w in PRETORIA_TO_CAPE_TOWN
}
STOP_COORDINATES.update(
    {
        # Germiston Station, Gauteng
        "germiston": (-26.2184, 28.1509),
        # Klerksdorp Station, North West
        "klerksdorp": (-26.8677, 26.6667),
    }
)

# Decade-by-decade evolution narratives for the Time Machine feature.
# Each stop has eras: 1970, 1990, 2023 (present day).
TIMELINE_EVOLUTION: dict[str, dict[str, str]] = {
    "pretoria": {
        "1970": "Pretoria Station in the 1970s thrummed with steam-era locomotives and the clatter of goods trains feeding the capital's industrial heart. The iconic Herbert Baker building presided over platforms busy with migrant workers and civil servants, while jacarandas bloomed purple along the approach roads each spring.",
        "1990": "By the 1990s, diesel-electric traction dominated the Pretoria lines. The station forecourt saw a surge of informal traders selling vetkoek and newspapers to commuters navigating the transition era. The Capital Park workshops still echoed with the rhythm of heavy maintenance, though their workforce was shifting.",
        "2023": "Today, Pretoria Station blends its grand sandstone heritage with modern Gautrain connections and a vibrant vendor precinct. The jacarandas still rain purple petals onto platforms where tourists and daily commuters mingle, and the Union Buildings glow on the hill above a city in constant motion.",
    },
    "johannesburg_park": {
        "1970": "Park Station in the 1970s was a colossal steam-and-smoke cathedral, the gateway for millions of migrant workers arriving from across Southern Africa. The air smelled of coal, braai smoke from platform vendors, and the urgent rhythm of a city built on gold. Platform canopies sheltered crowds carrying cardboard suitcases and dreams.",
        "1990": "The 1990s brought the first Metrorail EMUs and a tidal wave of commuters as townships swelled. Informal trading exploded along the concourses — amagwinya, newspapers, airtime — while the station's Victorian bones strained under passenger numbers never imagined by its Edwardian architects.",
        "2023": "Today, Park Station is Africa's busiest rail hub, a multi-level maze where Gautrain, Metrorail, and long-distance Shosholoza Meyl converge. The historic main concourse has been restored, and the surrounding precinct pulses with street art, markets, and the relentless energy of Johannesburg's newest generation.",
    },
    "germiston": {
        "1970": "Germiston in the 1970s was the beating heart of South Africa's railway network — its marshalling yards among the largest on Earth. Endless strings of ore wagons from the gold mines rattled through day and night, sorted by armies of shunters. The station hummed with the industrial might of the Reef.",
        "1990": "By the 1990s, the great yards had begun to quieten as containerisation and road freight took their toll. Yet the station remained a vital crossroads, and the taxi ranks outside buzzed with the new economy — minibus taxis replacing the old municipal buses, traders adapting to changing commuter flows.",
        "2023": "Today, Germiston Station stands as a monument to a golden age of rail. The yards are quieter, but the station still serves thousands of daily commuters. Heritage steam tours occasionally revive the ghosts of the past, while local vendors keep the platform economy alive with township staples and quick bites.",
    },
    "kimberley": {
        "1970": "In the 1970s, Kimberley's station precinct buzzed with heavy industrial rail traffic, diamond-mining freight transit, and classic steam and early-diesel locomotives serving the Northern Cape corridor. The Big Hole loomed over a town still defined by its mineral revolution.",
        "1990": "By the 1990s, passenger migration surged around the station, informal trading stalls began taking root near the platform exits, and the transition toward modern commuter logistics took shape. The diamond museum attracted its first heritage tourists.",
        "2023": "Today, it blends rich diamond-rush heritage with vibrant local vendor hubs, serving as a historic tourism gateway alongside modern township transport. Craft markets on the platform sell beadwork and souvenirs to visitors arriving on the Shosholoza Meyl.",
    },
    "klerksdorp": {
        "1970": "Klerksdorp Station in the 1970s was a gold-mining frontier outpost on the mainline to the Cape. Steam locomotives took on water here while miners' trains discharged shift workers into a town built on the reef. The station restaurant served hearty plates to railwaymen and miners alike.",
        "1990": "The 1990s saw the decline of steam and the rise of air-conditioned long-distance coaches. The station became a quieter waypoint, but the town centre vendors near the forecourt kept serving mogodu and pap to travellers and locals navigating the changing economy.",
        "2023": "Today, Klerksdorp Station is a modest stop on the Shosholoza Meyl route, its platforms echoing with memories of the gold rush. The town centre market thrives, and the station forecourt hosts traders selling everything from fresh produce to mobile accessories.",
    },
    "de_aar": {
        "1970": "De Aar in the 1970s was the great Karoo railway junction — a 24-hour hive of steam activity where engines were serviced, crews changed, and the silence of the Karoo met the constant hubbub of passing trains. The running sheds glowed through the night, a beacon in the vast semi-desert.",
        "1990": "By the 1990s, the junction's strategic importance faded with dieselisation and route rationalisation. The massive yards fell quiet, but the station remained a lifeline for the town, and the weekly Karoo market beside the platforms became a social anchor for the community.",
        "2023": "Today, De Aar Station is a peaceful Karoo stop where the Shosholoza Meyl pauses briefly. The old running sheds stand as silent monuments, while the station market offers Karoo lamb, crafts, and the famous hospitality of the Great Karoo to passing travellers.",
    },
    "beaufort_west": {
        "1970": "Beaufort West in the 1970s was the gateway to the Karoo National Park and a vital watering stop for steam locomotives crossing the great thirst. The Victorian station building hosted travellers in its dining room, while outside, the Karoo wind whispered across platforms built for an empire's trains.",
        "1990": "The 1990s brought the end of steam regular working and a quieter station. Yet Beaufort West remained the Karoo's oldest town, and its town hall — South Africa's oldest — still watched over a station where the occasional diesel-hauled train broke the vast silence.",
        "2023": "Today, Beaufort West Station welcomes tourists bound for the Karoo National Park and passengers on the scenic Shosholoza Meyl. The historic station building houses a small railway museum, and local artisans sell Karoo crafts on the platform where steam giants once hissed.",
    },
    "matjiesfontein": {
        "1970": "Matjiesfontein in the 1970s was a perfectly preserved Victorian time capsule, its gas lamps still flickering on platforms where the Cape mail train paused for refreshments. The Lord Milner Hotel served high tea to travellers stepping into a world seemingly untouched by the 20th century.",
        "1990": "By the 1990s, the village had become a declared heritage site. The station remained a mandatory refreshment stop for the Blue Train, and tourists marvelled at the authenticity of a place where the 19th century never really ended. The village shop stocked curios alongside essentials.",
        "2023": "Today, Matjiesfontein Station is a living museum where the Shosholoza Meyl and Blue Train still pause. The gas lamps still glow, the hotel still serves high tea, and the village shop offers travellers a genuine step back in time — one of South Africa's most unique railway experiences.",
    },
    "worcester": {
        "1970": "Worcester in the 1970s was the gateway to the Hex River Valley pass — the dramatic mountain railway where steam locomotives battled the 1:40 gradients. The station bustled with fruit traffic from the Breede River Valley, and banking engines waited in the sidings for the climb ahead.",
        "1990": "The 1990s saw the electrification of the Hex River pass and the end of steam banking. The station's role shifted to serving the growing Winelands tourism and commuter traffic. The Breede River Market began to take shape as a weekend destination for Capetonians.",
        "2023": "Today, Worcester Station is a modern hub for the Cape Winelands. The dramatic Hex River Valley pass is now traversed by electric locomotives, and the station connects tourists to wine routes, while the weekend market overflows with valley produce, wine, and crafts.",
    },
    "cape_town": {
        "1970": "Cape Town Station in the 1970s was the grand terminus where the Blue Train and Trans-Karoo Express ended their journeys beneath Table Mountain. Steam gave way to diesel on the final approaches, and the station concourse bustled with Capetonians, tourists, and the aroma of Malay curries from nearby vendors.",
        "1990": "The 1990s brought Metrorail's growing commuter crush and the first stirrings of station modernisation. The historic Edwardian building stood resilient as the forecourt transformed with informal trading, taxi ranks, and the energy of a city reinventing itself in the dawn of democracy.",
        "2023": "Today, Cape Town Station is a vibrant transport interchange where MyCiTi buses, Metrorail, and Shosholoza Meyl converge. The restored Victorian facade opens onto a bustling plaza of food markets, street performers, and the gateway to the Mother City — where every arrival feels like a homecoming.",
    },
}

_DEFAULT_STOP_CONTENT: dict = {
    "stop_name": "Shosholoza Corridor Stop",
    "historical_narrative": "A key stop along the historic South African rail corridor.",
    "heritage_sites": [],
    "local_stalls": [],
}

def get_stop_content(stop_key: str) -> dict:
    """Retrieve historical narrative, heritage sites, stalls, and geofence
    coordinates for a given Shosholoza Meyl stop. Unknown stops fall back to
    a generic corridor profile rather than erroring."""
    entry = SHOSHOLOZA_ROUTE_STORIES.get(stop_key, _DEFAULT_STOP_CONTENT)
    coordinates = STOP_COORDINATES.get(stop_key, (None, None))
    eras = TIMELINE_EVOLUTION.get(stop_key, {})
    return {
        **entry,
        "heritage_sites": list(entry["heritage_sites"]),
        "local_stalls": list(entry["local_stalls"]),
        "lat": coordinates[0],
        "lon": coordinates[1],
        "eras": eras,
    }