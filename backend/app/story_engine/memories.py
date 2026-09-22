"""
Rider-shared memories along the corridor — the "new generation creates new
memories, older generation relives old ones" half of the content model.

The curated `content_store.py` stories are the historical memory of the
route: what a place was, told by people who live there and approved by human
reviewers before it ever reaches a rider. This module holds the *other*
kind of memory: what a rider feels and sees right now, dropped at a
waypoint as they pass it. Together the two make the slogan literal — every
stop tells a story, and every rider can add a verse to it.

Design guardrails, written into the module rather than assumed:

- Valid waypoints only: a memory can only be attached to a waypoint that
  actually exists on the route (route.PRETORIA_TO_CAPE_TOWN). A typo'd id
  is rejected at the store, not silently stored and lost.
- Bounded text: rider text is capped (see MAX_MEMORY_TEXT_LENGTH) so one
  bad actor can't use the store as a free blob store, and so the same bound
  maps to a sane PostGIS column later.
- Anonymous: creators are keyed by the same opaque client-generated UUID
  used by live_share. A memory says "someone at Kimberley shared this" and
  carries the opaque rider_id back so the creator can recognise their own
  contribution — it never carries a name, email, or session.
- Deliberately non-moderated at this scope: memories are first-person
  experience-sharing, not broadcast content. The store is small and bounded
  (see MAX_MEMORIES) so a human can review the whole set in a morning;
  automated moderation is a stated out-of-scope item, not an accident.
- Coordinate-tagged: a memory may carry the exact spot it was dropped at
  (lat/lon, optional — both are required together). Riders passing that
  spot later can "unlock" memories with memories_near(), the geofenced
  relive path: the older generation's memory surfaces only where it was
  left, instead of only at a whole waypoint's 5km trigger radius.
- Audio-ready: a memory may reference a hosted voice-note via audio_url.
  Binary upload/hosting is a stated out-of-scope item for the current no-DB
  build; the field exists so a voice recorder can point at a signed URL
  without a schema change. Written on disk in production: nothing here ever
  stores the bytes.

Persistence plan (in-memory now, PostGIS in production):
- The README architecture shows PostGIS as the production data layer, and
  this store is intentionally the swap target for it. In production this
  module's interface stays identical but the backing becomes a table,
  created roughly as:

      CREATE TABLE rider_memories (
          id            uuid PRIMARY KEY,
          waypoint_id   text    NOT NULL REFERENCES route_waypoints(id),
          rider_id      uuid    NOT NULL,
          body          text    NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
          language_code text    NOT NULL DEFAULT 'en',
          lat           double precision,          -- NULL = not spot-tagged
          lon           double precision,          -- NULL = not spot-tagged
          audio_url     text,                       -- hosted voice note, if any
          created_at    timestamptz NOT NULL DEFAULT now(),
          CHECK ( (lat IS NULL) = (lon IS NULL) )
      );
      CREATE INDEX ON rider_memories (waypoint_id, created_at DESC);
      CREATE INDEX ON rider_memories (lat, lon);  -- geofenced unlock lookups

  A `MemoryStore` implementation backed by this table would implement the
  same methods (add_memory, memories_for, memories_near, count,
  all_memories) and be swapped in at the single `memory_store` instance
  below, leaving api.py untouched. Until then, memories live in an
  in-memory list: lost on process restart and confined to a single server
  process, exactly like live_share's positions — a known, stated limitation
  at MVP scope.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.story_engine.geofence import haversine_meters
from app.story_engine.live_share import RIDER_ID_PATTERN, is_valid_rider_id
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

# A memory can only be attached to a waypoint that exists on the route.
VALID_WAYPOINT_IDS: frozenset[str] = frozenset(w.id for w in PRETORIA_TO_CAPE_TOWN)

# Rider text is capped at 2,000 characters — the same bound the PostGIS
# `body text CHECK (...)` above will enforce in production.
MAX_MEMORY_TEXT_LENGTH = 2_000

# Hard cap on how many memories the in-memory store keeps (oldest evicted),
# so a long-lived demo process can't grow without bound. In production the
# DB owns eviction policy / retention instead.
MAX_MEMORIES = 500

# Default page size for the listing endpoint.
DEFAULT_MEMORIES_LIMIT = 20

# Default radius for the geofenced "unlock memories at this spot" lookup.
# Tighter than the 5km story-trigger radius on purpose: a memory is pinned
# to the exact spot it was dropped, so reliving it means being basically
# *there* — walking the platform, not just passing the town.
DEFAULT_NEARBY_RADIUS_METERS = 1_000


@dataclass(frozen=True)
class Memory:
    memory_id: str
    waypoint_id: str
    rider_id: str
    text: str
    created_at: float  # time.time() epoch, for parity with live_share
    language_code: str = "en"
    lat: float | None = None  # both lat and lon set together, or neither
    lon: float | None = None
    audio_url: str | None = None  # reference to a hosted voice note, never the bytes

    def as_dict(self) -> dict[str, str | float | None]:
        return {
            "memory_id": self.memory_id,
            "waypoint_id": self.waypoint_id,
            "rider_id": self.rider_id,
            "text": self.text,
            "created_at": self.created_at,
            "language_code": self.language_code,
            "lat": self.lat,
            "lon": self.lon,
            "audio_url": self.audio_url,
        }


class MemoryStore:
    """
    Plain in-memory store, single process only — see module docstring for
    the production swap target. Newest memories are served first.
    """

    def __init__(self, max_memories: int = MAX_MEMORIES) -> None:
        self._max_memories = max_memories
        self._memories: list[Memory] = []

    def add_memory(
        self,
        waypoint_id: str,
        rider_id: str,
        text: str,
        language_code: str = "en",
        lat: float | None = None,
        lon: float | None = None,
        audio_url: str | None = None,
        now: float | None = None,
    ) -> Memory:
        """Validate and store a rider memory, evicting the oldest entry if
        the store is at its cap. Raises ValueError on invalid input — the
        API layer turns that into a 422."""
        if waypoint_id not in VALID_WAYPOINT_IDS:
            raise ValueError(f"unknown waypoint_id: {waypoint_id!r}")
        if not is_valid_rider_id(rider_id):
            raise ValueError(f"rider_id must be UUID-shaped, got {rider_id!r}")

        stripped = text.strip()
        if not stripped:
            raise ValueError("memory text must not be empty")
        if len(stripped) > MAX_MEMORY_TEXT_LENGTH:
            raise ValueError(
                f"memory text must be at most {MAX_MEMORY_TEXT_LENGTH} characters, "
                f"got {len(stripped)}"
            )

        if (lat is None) != (lon is None):
            raise ValueError("lat and lon must be provided together, or not at all")
        if lat is not None and not -90.0 <= lat <= 90.0:
            raise ValueError(f"lat must be between -90 and 90, got {lat}")
        if lon is not None and not -180.0 <= lon <= 180.0:
            raise ValueError(f"lon must be between -180 and 180, got {lon}")

        audio = audio_url.strip() if audio_url else None
        if audio is not None and not (audio.startswith("http://") or audio.startswith("https://")):
            raise ValueError("audio_url must be an absolute http(s) URL")

        memory = Memory(
            memory_id=str(uuid.uuid4()),
            waypoint_id=waypoint_id,
            rider_id=rider_id,
            text=stripped,
            created_at=now if now is not None else time.time(),
            language_code=language_code,
            lat=lat,
            lon=lon,
            audio_url=audio,
        )
        self._memories.append(memory)

        if len(self._memories) > self._max_memories:
            # Evict oldest first — self._memories is appended in insertion
            # order, so the head of the list is the oldest memory.
            del self._memories[: len(self._memories) - self._max_memories]

        return memory

    def memories_for(self, waypoint_id: str | None = None, limit: int = DEFAULT_MEMORIES_LIMIT) -> list[Memory]:
        """Return memories for a waypoint (or all waypoints if None),
        newest first, capped at `limit`."""
        newest_first = sorted(self._memories, key=lambda m: m.created_at, reverse=True)
        filtered = newest_first if waypoint_id is None else [m for m in newest_first if m.waypoint_id == waypoint_id]
        return filtered[:limit]

    def memories_near(
        self,
        lat: float,
        lon: float,
        radius_meters: float = DEFAULT_NEARBY_RADIUS_METERS,
        limit: int = DEFAULT_MEMORIES_LIMIT,
    ) -> list[Memory]:
        """Return memories tagged to a spot within `radius_meters` of
        (lat, lon) — the geofenced unlock path. Only memories that carry
        coordinates can match; untagged ones are invisible to this query.
        Newest first, capped at `limit`."""
        nearby = [
            m
            for m in self._memories
            if m.lat is not None
            and m.lon is not None
            and haversine_meters(lat, lon, m.lat, m.lon) <= radius_meters
        ]
        nearby.sort(key=lambda m: m.created_at, reverse=True)
        return nearby[:limit]

    def count(self) -> int:
        return len(self._memories)

    def all_memories(self) -> list[Memory]:
        return list(self._memories)

    def clear(self) -> None:
        """Remove every stored memory. Exists for test isolation; production
        retention is owned by the DB layer per the module docstring."""
        self._memories.clear()


# Single shared instance for the running process — mirrors live_share.py's
# live_position_store and content_store.py's STORY_CONTENT pattern.
memory_store = MemoryStore()