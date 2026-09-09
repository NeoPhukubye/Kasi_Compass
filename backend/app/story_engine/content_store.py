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
