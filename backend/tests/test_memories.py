"""
Unit tests for app.story_engine.memories — the rider-shared memories store.

Run with: pytest backend/tests/test_memories.py
"""

from app.story_engine.memories import (
    MAX_MEMORIES,
    MAX_MEMORY_TEXT_LENGTH,
    Memory,
    MemoryStore,
    VALID_WAYPOINT_IDS,
)
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN

VALID_UUID = "11111111-2222-3333-4444-555555555555"
OTHER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_valid_waypoint_ids_cover_every_route_waypoint():
    assert VALID_WAYPOINT_IDS == {w.id for w in PRETORIA_TO_CAPE_TOWN}


def test_add_memory_returns_a_memory_with_id_and_timestamp():
    store = MemoryStore()
    memory = store.add_memory("kimberley", VALID_UUID, "  The Big Hole at sunrise.  ", now=1000.0)
    assert isinstance(memory, Memory)
    assert memory.waypoint_id == "kimberley"
    assert memory.rider_id == VALID_UUID
    assert memory.created_at == 1000.0
    # Input is stored stripped.
    assert memory.text == "The Big Hole at sunrise."
    assert memory.memory_id


def test_add_memory_rejects_unknown_waypoint():
    store = MemoryStore()
    try:
        store.add_memory("narnia", VALID_UUID, "hello", now=1000.0)
    except ValueError:
        return
    raise AssertionError("expected unknown waypoint_id to be rejected")


def test_add_memory_rejects_non_uuid_rider_id():
    store = MemoryStore()
    for bad in ("not-a-uuid", "", "11111111-2222-3333-4444"):
        try:
            store.add_memory("kimberley", bad, "hello", now=1000.0)
        except ValueError:
            continue
        raise AssertionError(f"expected rider_id {bad!r} to be rejected")


def test_add_memory_rejects_blank_text():
    store = MemoryStore()
    for blank in ("", "   ", "\n\t"):
        try:
            store.add_memory("kimberley", VALID_UUID, blank, now=1000.0)
        except ValueError:
            continue
        raise AssertionError("expected blank memory text to be rejected")


def test_add_memory_rejects_oversized_text():
    store = MemoryStore()
    try:
        store.add_memory("kimberley", VALID_UUID, "x" * (MAX_MEMORY_TEXT_LENGTH + 1), now=1000.0)
    except ValueError:
        return
    raise AssertionError("expected oversized memory text to be rejected")


def test_memories_for_returns_newest_first():
    store = MemoryStore()
    store.add_memory("kimberley", VALID_UUID, "first", now=1000.0)
    store.add_memory("kimberley", OTHER_UUID, "second", now=1001.0)
    store.add_memory("kimberley", VALID_UUID, "third", now=1002.0)

    memories = store.memories_for("kimberley")
    assert [m.text for m in memories] == ["third", "second", "first"]


def test_memories_for_filters_by_waypoint():
    store = MemoryStore()
    store.add_memory("kimberley", VALID_UUID, "diamond fields", now=1000.0)
    store.add_memory("de_aar", OTHER_UUID, "karoo junction", now=1001.0)

    only_kimberley = store.memories_for("kimberley")
    assert [m.waypoint_id for m in only_kimberley] == ["kimberley"]
    assert only_kimberley[0].text == "diamond fields"

    all_memories = store.memories_for(None)
    assert {m.waypoint_id for m in all_memories} == {"kimberley", "de_aar"}
    # Every return path is still newest-first.
    assert [m.text for m in all_memories] == ["karoo junction", "diamond fields"]


def test_memories_for_respects_limit():
    store = MemoryStore()
    for i in range(5):
        store.add_memory("kimberley", VALID_UUID, f"memory {i}", now=float(1000 + i))
    assert len(store.memories_for("kimberley", limit=2)) == 2


def test_store_evicts_oldest_when_at_capacity():
    store = MemoryStore(max_memories=3)
    for i in range(5):
        store.add_memory("kimberley", VALID_UUID, f"memory {i}", now=float(1000 + i))

    assert store.count() == 3
    remaining = [m.text for m in store.all_memories()]
    # The two oldest ("memory 0", "memory 1") were evicted.
    assert remaining == ["memory 2", "memory 3", "memory 4"]


def test_clear_removes_every_memory():
    store = MemoryStore()
    store.add_memory("kimberley", VALID_UUID, "hello", now=1000.0)
    store.clear()
    assert store.count() == 0
    assert store.memories_for("kimberley") == []