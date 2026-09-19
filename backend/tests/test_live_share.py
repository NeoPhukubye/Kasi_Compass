"""
Unit tests for app.story_engine.live_share.

Run with: pytest backend/tests/test_live_share.py
"""

import math

from app.story_engine.live_share import (
    LivePositionStore,
    fuzz_coordinate,
    is_valid_rider_id,
)
from app.story_engine.geofence import haversine_meters

VALID_UUID = "11111111-2222-3333-4444-555555555555"
OTHER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_is_valid_rider_id_accepts_uuid_shape():
    assert is_valid_rider_id(VALID_UUID)


def test_is_valid_rider_id_rejects_non_uuid():
    assert not is_valid_rider_id("not-a-uuid")
    assert not is_valid_rider_id("")
    assert not is_valid_rider_id("11111111-2222-3333-4444")  # too short


def test_fuzz_coordinate_snaps_nearby_points_to_same_cell():
    # A tiny jitter (~3m) that stays well clear of any 150m grid-cell
    # boundary, unlike a jitter approaching half the cell width, which can
    # legitimately land in an adjacent cell if the base point sits near a
    # boundary — that's correct grid-snapping behavior, not a bug.
    lat, lon = -30.6508, 24.0133  # De Aar
    fuzzed_1 = fuzz_coordinate(lat, lon)
    fuzzed_2 = fuzz_coordinate(lat + 0.00003, lon + 0.00003)
    assert fuzzed_1 == fuzzed_2


def test_fuzz_coordinate_displacement_is_bounded():
    lat, lon = -33.9222, 18.4264  # Cape Town
    fuzzed_lat, fuzzed_lon = fuzz_coordinate(lat, lon)
    displacement = haversine_meters(lat, lon, fuzzed_lat, fuzzed_lon)
    assert displacement < 150.0 * math.sqrt(2)


def test_share_position_returns_active_count():
    store = LivePositionStore()
    count = store.share_position(VALID_UUID, -30.65, 24.01, now=1000.0)
    assert count == 1
    count = store.share_position(OTHER_UUID, -32.35, 22.58, now=1001.0)
    assert count == 2


def test_get_other_positions_excludes_caller():
    store = LivePositionStore()
    store.share_position(VALID_UUID, -30.65, 24.01, now=1000.0)
    store.share_position(OTHER_UUID, -32.35, 22.58, now=1000.0)

    others = store.get_other_positions(VALID_UUID, now=1000.0)
    assert len(others) == 1
    assert others[0]["rider_id"] == OTHER_UUID


def test_get_other_positions_never_returns_raw_coordinates():
    store = LivePositionStore()
    raw_lat, raw_lon = -30.650812345, 24.013312345
    store.share_position(VALID_UUID, raw_lat, raw_lon, now=1000.0)

    others = store.get_other_positions(OTHER_UUID, now=1000.0)
    assert len(others) == 1
    # The stored/returned position must be the fuzzed one, never the exact input.
    assert others[0]["lat"] != raw_lat
    assert others[0]["lon"] != raw_lon
    expected_lat, expected_lon = fuzz_coordinate(raw_lat, raw_lon)
    assert others[0]["lat"] == expected_lat
    assert others[0]["lon"] == expected_lon


def test_positions_expire_after_ttl():
    store = LivePositionStore(ttl_seconds=45.0)
    store.share_position(VALID_UUID, -30.65, 24.01, now=1000.0)

    # Still fresh at 44s.
    others = store.get_other_positions(OTHER_UUID, now=1044.0)
    assert len(others) == 1

    # Expired at 46s.
    others = store.get_other_positions(OTHER_UUID, now=1046.0)
    assert len(others) == 0


def test_leave_removes_position_immediately_without_waiting_for_ttl():
    store = LivePositionStore(ttl_seconds=45.0)
    store.share_position(VALID_UUID, -30.65, 24.01, now=1000.0)
    assert store.active_count(now=1000.0) == 1

    removed = store.leave(VALID_UUID)
    assert removed is True
    assert store.active_count(now=1000.0) == 0


def test_leave_on_unknown_rider_id_returns_false_without_error():
    store = LivePositionStore()
    assert store.leave(VALID_UUID) is False


def test_updating_position_refreshes_ttl():
    store = LivePositionStore(ttl_seconds=45.0)
    store.share_position(VALID_UUID, -30.65, 24.01, now=1000.0)
    # Re-share at 1040 (before original TTL would expire at 1045).
    store.share_position(VALID_UUID, -30.66, 24.02, now=1040.0)

    # At 1070 — 30s after the *refreshed* share, well within TTL — still active.
    others = store.get_other_positions(OTHER_UUID, now=1070.0)
    assert len(others) == 1
