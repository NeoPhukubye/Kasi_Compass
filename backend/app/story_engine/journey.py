"""
Journey Guardian — server-side journey lifecycle and family tracking links.

This is the "Journey Guardian" named in the pitch, and the "direct-to-family
sharing via instant links" named in the distribution channels. It is a
deliberately different thing from live_share.py, and the difference matters:

  live_share.py   — rider-to-rider, opt-in, anonymous, 45s TTL, fuzzed to
                    150m, in-memory, gone on restart. "See each other moving."
  journey.py      — passenger-to-family, link-based, server-side, persisted,
                    survives the passenger's phone dying entirely. "Is my
                    mother okay?"

The privacy model follows from who is watching whom. A family link is a
capability token, not a public profile: it carries no name, no contact
details, no rider id, and grants read-only access to one journey's position,
ETA and milestones. It can be revoked, and revoking it is immediate — the
family member's page stops updating on the next poll rather than after a TTL.

Where the position comes from
-----------------------------
`/guardian/journeys/{id}/position` accepts position reports from the
*corridor* — a wayside beacon, a locomotive GPS unit, an operator feed —
not only from the passenger's device. That is the claim the whole product
rests on: on a 27-hour trip through the Karoo, a phone at 4% with no signal
must not be the thing that decides whether the family knows anything. The
API cannot verify who is reporting, so it is explicit about provenance:
every report carries a `source`, and the family view surfaces the most recent
one, so nobody is misled about how fresh the data is.

No AI anywhere in this path.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field

from app.story_engine import spatial
from app.story_engine.eta import compute_eta

# Journey ids are UUID-shaped, matching live_share's rider-id convention: an
# opaque token that carries no identity of its own.
JOURNEY_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Guardian links are long, random, URL-safe tokens. Deliberately much larger
# than a journey id: these get pasted into WhatsApp messages, so the token
# space has to be big enough that guessing one is not a viable attack, and
# short enough that a family member will actually click it.
GUARDIAN_TOKEN_BYTES = 24
GUARDIAN_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Who is allowed to push position into a journey. `corridor` is the
# infrastructure feed the pitch's moat argument rests on; `passenger` is the
# rider's own device, kept for the case where it happens to have signal.
POSITION_SOURCES = ("corridor", "passenger", "operator", "simulation")


def is_valid_journey_id(journey_id: str) -> bool:
    return bool(JOURNEY_ID_PATTERN.match(journey_id))


def generate_guardian_token() -> str:
    return secrets.token_urlsafe(GUARDIAN_TOKEN_BYTES)


@dataclass
class GuardianLink:
    """A read-only capability token bound to exactly one journey."""

    token: str
    journey_id: str
    created_at: float
    revoked: bool = False
    label: str = "family"
    # A coarse label the family page shows ("Tracking Mpho's journey"). Never
    # a name, phone number, or anything else that would turn this link into
    # an identity record.
    display_name: str = ""

    def as_dict(self) -> dict:
        return {
            "token": self.token,
            "journey_id": self.journey_id,
            "created_at": self.created_at,
            "revoked": self.revoked,
            "label": self.label,
            "display_name": self.display_name,
        }


@dataclass
class Journey:
    """A tracked journey. Holds no passenger identity — only a corridor."""

    journey_id: str
    corridor_id: str
    origin_waypoint_id: str
    destination_waypoint_id: str
    created_at: float
    ticket_id: str | None = None
    guardian_links: dict[str, GuardianLink] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "journey_id": self.journey_id,
            "corridor_id": self.corridor_id,
            "origin_waypoint_id": self.origin_waypoint_id,
            "destination_waypoint_id": self.destination_waypoint_id,
            "created_at": self.created_at,
            "ticket_id": self.ticket_id,
            "guardian_link_count": sum(1 for link in self.guardian_links.values() if not link.revoked),
        }


class JourneyRegistry:
    """
    Registry of journeys and their guardian links, backed by the spatial
    store.

    Everything is written through to the database on mutation, and hydrated
    from it on first use. That is not belt-and-braces: a guardian token is a
    capability somebody has already sent in a WhatsApp message, so losing it
    to a redeploy breaks the promise the product exists to keep — and the
    person who notices is the family, not the operator.

    The in-memory maps stay as a read cache, because the hot path (a family
    page polling every ten seconds) should not hit the database for a token
    lookup it has already resolved this process.
    """

    def __init__(self) -> None:
        self._journeys: dict[str, Journey] = {}
        self._links: dict[str, GuardianLink] = {}
        self._hydrated = False

    def _hydrate(self) -> None:
        """
        Pull journeys and links out of the database once per process.

        Guarded so concurrent first requests don't each do the work, and
        tolerant of a store that hasn't been seeded yet — an empty registry
        is a valid state, not an error.
        """
        if self._hydrated:
            return
        self._hydrated = True

        for record in spatial.spatial_store.load_journeys():
            if record["journey_id"] in self._journeys:
                continue
            journey = Journey(
                journey_id=record["journey_id"],
                corridor_id=record["corridor_id"],
                origin_waypoint_id=record["origin_waypoint_id"],
                destination_waypoint_id=record["destination_waypoint_id"],
                created_at=record["created_at"],
                ticket_id=record["ticket_id"],
            )
            self._journeys[journey.journey_id] = journey

        for record in spatial.spatial_store.load_all_links():
            if record["token"] in self._links:
                continue
            link = GuardianLink(
                token=record["token"],
                journey_id=record["journey_id"],
                created_at=record["created_at"],
                revoked=record["revoked"],
                label=record["label"],
                display_name=record["display_name"],
            )
            self._links[link.token] = link
            journey = self._journeys.get(link.journey_id)
            if journey is not None and not link.revoked:
                journey.guardian_links[link.token] = link

    # ------------------------------------------------------------------
    # Journeys
    # ------------------------------------------------------------------

    def create_journey(
        self,
        journey_id: str,
        origin_waypoint_id: str = "pretoria",
        destination_waypoint_id: str = "cape_town",
        corridor_id: str = "pretoria_cape_town",
        ticket_id: str | None = None,
        now: float | None = None,
    ) -> Journey:
        self._hydrate()
        if not is_valid_journey_id(journey_id):
            raise ValueError("journey_id must be UUID-shaped")
        now = now if now is not None else time.time()
        journey = Journey(
            journey_id=journey_id,
            corridor_id=corridor_id,
            origin_waypoint_id=origin_waypoint_id,
            destination_waypoint_id=destination_waypoint_id,
            created_at=now,
            ticket_id=ticket_id,
        )
        self._journeys[journey_id] = journey
        spatial.spatial_store.save_journey(journey.as_dict())
        return journey

    def get_journey(self, journey_id: str) -> Journey | None:
        self._hydrate()
        return self._journeys.get(journey_id)

    def journeys(self) -> list[Journey]:
        self._hydrate()
        return list(self._journeys.values())

    # ------------------------------------------------------------------
    # Guardian links
    # ------------------------------------------------------------------

    def issue_link(
        self,
        journey_id: str,
        display_name: str = "",
        label: str = "family",
        now: float | None = None,
    ) -> GuardianLink:
        """
        Mint a read-only tracking link for a journey.

        `display_name` is a short free-text label the family page shows
        ("Tracking Ada's journey"). It is stored as-is and never joined to
        anything else, and the API layer caps its length.
        """
        journey = self._journeys.get(journey_id)
        if journey is None:
            raise ValueError(f"unknown journey_id: {journey_id!r}")

        self._hydrate()
        now = now if now is not None else time.time()
        token = generate_guardian_token()
        while token in self._links:  # pragma: no cover - 2^192 space
            token = generate_guardian_token()

        link = GuardianLink(
            token=token,
            journey_id=journey_id,
            created_at=now,
            label=label,
            display_name=display_name,
        )
        self._links[token] = link
        journey.guardian_links[token] = link
        # Written through before it is handed back, so a link that has been
        # sent to someone is never one that only exists in this process.
        spatial.spatial_store.save_link(link.as_dict())
        return link

    def resolve_link(self, token: str) -> GuardianLink | None:
        """Look up a token. Revoked links resolve to None, immediately."""
        self._hydrate()
        if not GUARDIAN_TOKEN_PATTERN.match(token):
            return None
        link = self._links.get(token)
        if link is not None:
            return None if link.revoked else link
        # A token this process has never seen may still be a live link minted
        # before a restart. Check the database before calling it unknown —
        # failing closed here would silently break a family link.
        record = spatial.spatial_store.load_link(token)
        if record is None or record["revoked"]:
            return None
        link = GuardianLink(
            token=record["token"],
            journey_id=record["journey_id"],
            created_at=record["created_at"],
            revoked=False,
            label=record["label"],
            display_name=record["display_name"],
        )
        self._links[link.token] = link
        journey = self._journeys.get(link.journey_id)
        if journey is not None:
            journey.guardian_links[link.token] = link
        return link

    def revoke_link(self, token: str) -> bool:
        """
        Revoke a link now. The family member's next poll gets a 404, rather
        than continuing to receive a position until some TTL lapses.

        The revocation is written to the database, so a restart cannot
        resurrect a link the rider has already cancelled.
        """
        self._hydrate()
        link = self._links.get(token)
        existed_in_db = spatial.spatial_store.revoke_link(token)
        if link is None:
            return existed_in_db
        link.revoked = True
        journey = self._journeys.get(link.journey_id)
        if journey is not None:
            journey.guardian_links.pop(token, None)
        return True

    def links_for(self, journey_id: str) -> list[GuardianLink]:
        self._hydrate()
        journey = self._journeys.get(journey_id)
        if journey is None:
            return []
        return [link for link in journey.guardian_links.values() if not link.revoked]

    # ------------------------------------------------------------------
    # Position ingestion
    # ------------------------------------------------------------------

    def report_position(
        self,
        journey_id: str,
        lat: float,
        lon: float,
        source: str = "corridor",
        speed_mps: float | None = None,
        recorded_at: float | None = None,
    ) -> dict:
        """
        Ingest a position report for a journey, from the corridor or the
        passenger's device.

        Persists to spatial.py rather than to the registry, so the position
        outlives this process. Returns the derived ETA alongside the stored
        point, because a reporter almost always wants both.
        """
        if journey_id not in self._journeys:
            self._hydrate()
        if journey_id not in self._journeys:
            self.create_journey(journey_id)
        point = spatial.spatial_store.record_telemetry(
            journey_id=journey_id,
            lat=lat,
            lon=lon,
            speed_mps=speed_mps,
            source=source,
            recorded_at=recorded_at,
        )
        return {
            "point": point.as_dict(),
            "eta": self.eta_for(journey_id),
        }

    def eta_for(self, journey_id: str, now: float | None = None) -> dict:
        """ETA + milestones for a journey, or a `no_data` envelope."""
        try:
            return compute_eta(journey_id, now=now).as_dict()
        except LookupError:
            return {
                "journey_id": journey_id,
                "status": "no_data",
                "position": None,
                "observed_speed_kmh": 0.0,
                "speed_source": "insufficient",
                "eta": {"next_station": None, "next_station_at": None, "arrival_station": None, "arrival_at": None},
                "delay_hours": 0.0,
                "delay_display": "Waiting for the first corridor report",
                "province": "",
                "next_province": None,
                "distance_to_next_station_km": 0.0,
                "last_report_seconds_ago": None,
                "last_report_source": None,
                "milestones": [],
            }

    def family_view(self, token: str, now: float | None = None) -> dict:
        """
        Everything a family member's page needs, in one payload: who they're
        tracking, where the train is, how late it is, and what has happened
        so far. Raises LookupError for an unknown or revoked token so the API
        layer can turn it into a 404.
        """
        link = self.resolve_link(token)
        if link is None:
            raise LookupError("guardian link is unknown or revoked")
        journey = self._journeys.get(link.journey_id)
        if journey is None:  # pragma: no cover - registry keeps these in step
            raise LookupError("journey for this link no longer exists")

        eta = self.eta_for(link.journey_id, now=now)
        return {
            "tracking": {
                "label": link.label,
                "display_name": link.display_name,
                "issued_at": link.created_at,
            },
            "journey": journey.as_dict(),
            "eta": eta,
            "status": eta["status"],
            "headline": self._headline(eta),
        }

    @staticmethod
    def _headline(eta: dict) -> str:
        """
        One sentence a family member can read at a glance.

        This is the emotional core of the product in a single string: not
        "GPS: -30.6508, 24.0133", but "Stopped outside De Aar — 3h 20m behind
        schedule". Deliberately plain, deliberately pessimistic about what we
        do not know.
        """
        if eta["status"] == "no_data":
            return "Waiting for the first position report from the corridor."
        if eta["status"] == "arrived":
            return f"Arrived at {eta['eta']['arrival_station']}."
        if eta["status"] == "signal_lost":
            # delay_display already carries the "no position report for
            # 3h 20m" phrasing, so it is used verbatim here — wrapping it in
            # another sentence produced "No position report for no position
            # report for 3h 20m".
            return f"Last seen near {eta['position']['nearest_waypoint_name']}. {eta['delay_display']}."

        where = eta["position"]["nearest_waypoint_name"]
        heading_for = eta["eta"]["next_station"]
        if eta["status"] == "stopped":
            return f"Stopped near {where}. {eta['delay_display']}"
        if heading_for and heading_for != where:
            return f"Past {where}, heading for {heading_for}. {eta['delay_display']}"
        if heading_for:
            return f"Approaching {heading_for}. {eta['delay_display']}"
        return f"Past {where}. {eta['delay_display']}"


# Single shared instance for the running process.
journey_registry = JourneyRegistry()
