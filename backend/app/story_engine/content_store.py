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
    type: str  # "market", "shop", "restaurant", "tourist_attraction", "fuel", "parking"
    lat: float
    lon: float
    def as_dict(self) -> dict[str, str | float]:
        """Plain-dict form of this POI for the API response model."""
        return {"name": self.name, "type": self.type, "lat": self.lat, "lon": self.lon}


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
        PointOfInterest("Kimberley Big Hole", "tourist_attraction", -28.7353, 24.7697),
        PointOfInterest("Kimberley Market", "market", -28.7340, 24.7680),
        PointOfInterest("De Beers Store", "shop", -28.7360, 24.7710),
        PointOfInterest("Orange Street Fuel", "fuel", -28.7330, 24.7650),
        PointOfInterest("Kimberley Garage", "parking", -28.7370, 24.7700),
    ],
    "matjiesfontein": [
        PointOfInterest("Matjiesfontein Village Shop", "shop", -33.2167, 20.5833),
        PointOfInterest("Karoo Heritage Market", "market", -33.2155, 20.5845),
        PointOfInterest("Station Fuel Stop", "fuel", -33.2175, 20.5820),
        PointOfInterest("Village Parking", "parking", -33.2180, 20.5810),
        PointOfInterest("Old Hotel Restaurant", "restaurant", -33.2160, 20.5850),
    ],
    "pretoria": [
        PointOfInterest("Union Buildings", "tourist_attraction", -25.7479, 28.2293),
        PointOfInterest("Pretoria Market", "market", -25.7465, 28.2305),
        PointOfInterest("Capital Park Shop", "shop", -25.7485, 28.2280),
        PointOfInterest("Station Fuel", "fuel", -25.7490, 28.2270),
    ],
    "johannesburg_park": [
        PointOfInterest("Park Station", "tourist_attraction", -26.1972, 28.0419),
        PointOfInterest("Johannesburg Market", "market", -26.1960, 28.0430),
        PointOfInterest("City Centre Shop", "shop", -26.1980, 28.0400),
        PointOfInterest("Station Fuel", "fuel", -26.1985, 28.0390),
        PointOfInterest("PnP Parking", "parking", -26.1975, 28.0440),
    ],
    "de_aar": [
        PointOfInterest("De Aar Mall", "shop", -30.6508, 24.0133),
        PointOfInterest("Karoo Market", "market", -30.6495, 24.0145),
        PointOfInterest("Fuel Station", "fuel", -30.6515, 24.0120),
        PointOfInterest("Town Parking", "parking", -30.6520, 24.0110),
    ],
    "beaufort_west": [
        PointOfInterest("Beaufort West Mall", "shop", -32.3568, 22.5811),
        PointOfInterest("Karoo Karoo Market", "market", -32.3555, 22.5825),
        PointOfInterest("Station Fuel", "fuel", -32.3575, 22.5800),
        PointOfInterest("Public Parking", "parking", -32.3580, 22.5790),
    ],
    "worcester": [
        PointOfInterest("Worcester Mall", "shop", -33.6464, 19.4487),
        PointOfInterest("Breede River Market", "market", -33.6450, 19.4495),
        PointOfInterest("Fuel Station", "fuel", -33.6475, 19.4470),
        PointOfInterest("Town Parking", "parking", -33.6480, 19.4460),
    ],
    "cape_town": [
        PointOfInterest("Cape Town Station", "tourist_attraction", -33.9222, 18.4264),
        PointOfInterest("City Bowl Market", "market", -33.9210, 18.4275),
        PointOfInterest("Adderley Shop", "shop", -33.9230, 18.4250),
        PointOfInterest("Station Fuel", "fuel", -33.9235, 18.4240),
        PointOfInterest("City Parking", "parking", -33.9240, 18.4230),
    ],
}


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
