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
          created_at    timestamptz NOT NULL DEFAULT now()
      );
      CREATE INDEX ON rider_memories (waypoint_id, created_at DESC);

  A `MemoryStore` implementation backed by this table would implement the
  same four methods (add_memory, memories_for, count, all_memories) and be
  swapped in at the single `memory_store` instance below, leaving api.py
  untouched. Until then, memories live in an in-memory list: lost on
  process restart and confined to a single server process, exactly like
  live_share's positions — a known, stated limitation at MVP scope.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Memory:
    memory_id: str
    waypoint_id: str
    rider_id: str
    text: str
    created_at: float  # time.time() epoch, for parity with live_share
    language_code: str = "en"

    def as_dict(self) -> dict[str, str | float]:
        return {
            "memory_id": self.memory_id,
            "waypoint_id": self.waypoint_id,
            "rider_id": self.rider_id,
            "text": self.text,
            "created_at": self.created_at,
            "language_code": self.language_code,
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

        memory = Memory(
            memory_id=str(uuid.uuid4()),
            waypoint_id=waypoint_id,
            rider_id=rider_id,
            text=stripped,
            created_at=now if now is not None else time.time(),
            language_code=language_code,
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