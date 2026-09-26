"""
Unit tests for the digital journey passport, the Time Machine era data, the
offline story pack, and QR boarding.

Run with: pytest backend/tests/test_passport_and_extras.py
"""

import pytest

from app.story_engine.content_store import (
    ERA_YEARS,
    STATION_ERA_LAYOUT,
    STATIONS_WITHOUT_LAYOUT,
    TIMELINE_EVOLUTION,
    get_era_details,
    get_stop_content,
)
from app.story_engine.eta import simulate_corridor_run
from app.story_engine.passport import STAMP_RADIUS_METERS, build_passport
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN
from app.story_engine.spatial import SpatialStore
import app.story_engine.spatial as spatial_module

JOURNEY_A = "11111111-1111-4111-8111-111111111111"


@pytest.fixture()
def store(monkeypatch):
    s = SpatialStore(sqlite_path=":memory:")
    s.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", s)
    return s


# ---------------------------------------------------------------------
# Time Machine era data
# ---------------------------------------------------------------------

def test_every_stop_with_eras_has_all_three_of_them():
    for stop_id, eras in TIMELINE_EVOLUTION.items():
        assert sorted(eras) == sorted(ERA_YEARS), f"{stop_id} has {sorted(eras)}"


def test_era_details_expose_the_facts_the_schematic_draws():
    details = get_era_details("kimberley")
    for year in ERA_YEARS:
        era = details[year]
        # Everything the SVG renderer reads must be present, or the panel
        # silently draws an empty box.
        assert era["year"] == int(year)
        assert era["traction"]
        assert era["signalling"]
        assert isinstance(era["electrified"], bool)
        assert era["narrative"]
        assert era["layout"]["tracks"] >= 2
        assert era["layout"]["platforms"] >= 1
        assert era["layout"]["change"]


def test_eras_are_flagged_as_reconstructions_not_photographs():
    # The Time Machine used to present a placeholder stock photo as though it
    # were archival comparison imagery. Every era must now carry an explicit
    # reconstruction flag so the client can label it honestly.
    for era in get_era_details("de_aar").values():
        assert era["reconstruction"] is True


def test_electrification_appears_after_1970_and_not_before():
    """
    The single most visible change between the 1970 and 1990 schematics, and
    one grounded in the corridor's actual history: the Hex River
    electrification reached the Cape mainline in the late 1980s.
    """
    details = get_era_details("worcester")
    assert details["1970"]["electrified"] is False
    assert details["1990"]["electrified"] is True
    assert details["2023"]["electrified"] is True


def test_layouts_change_across_eras_where_the_history_says_they_did():
    assert STATION_ERA_LAYOUT["johannesburg_park"]["1970"]["tracks"] < \
        STATION_ERA_LAYOUT["johannesburg_park"]["2023"]["tracks"]


def test_matjiesfontein_stays_a_two_line_passing_loop_for_fifty_years():
    """
    The reason it is a declared heritage site, and the reason its three era
    schematics are identical. If this ever drifts, the historical claim in
    the era narrative is no longer supported by the drawing beside it.
    """
    for year in ERA_YEARS:
        layout = STATION_ERA_LAYOUT["matjiesfontein"][year]
        assert layout["tracks"] == 2
        assert layout["platforms"] == 1


def test_a_stop_with_no_surveyed_layout_reports_it_instead_of_inventing_one():
    for stop_id in STATIONS_WITHOUT_LAYOUT:
        era = get_era_details(stop_id)["1970"]
        assert era["layout"] is None
        assert era["layout_recorded"] is False
        # The narrative is still there — only the drawing is withheld.
        assert era["narrative"]


def test_stop_content_keeps_the_plain_eras_map_the_guide_uses():
    content = get_stop_content("kimberley")
    assert content["eras"]["1970"] == TIMELINE_EVOLUTION["kimberley"]["1970"]
    assert content["era_years"] == sorted(ERA_YEARS)
    assert "era_details" in content


def test_get_stop_content_never_returns_image_fields_anymore():
    # The frontend used to read data.image_past / image_present, which the
    # backend never sent, so both <img> elements kept the same placeholder
    # src. Nothing should reintroduce that shape.
    content = get_stop_content("kimberley")
    for key in ("image_past", "image_present", "image_past_caption", "image_present_caption"):
        assert key not in content


# ---------------------------------------------------------------------
# Journey passport
# ---------------------------------------------------------------------

def test_a_journey_with_no_reports_has_an_empty_passport(store):
    passport = build_passport(JOURNEY_A)
    assert passport["stamps"] == []
    assert passport["stamps_earned"] == 0
    assert passport["stamps_total"] == len(PRETORIA_TO_CAPE_TOWN)
    assert passport["complete"] is False
    assert "nothing to stamp" in passport["coverage_note"]


def test_a_full_corridor_run_stamps_every_station(store):
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=50, step_minutes=30)
    passport = build_passport(JOURNEY_A)
    assert passport["stamps_earned"] == passport["stamps_total"]
    assert passport["complete"] is True
    assert [s["waypoint_id"] for s in passport["stamps"]] == [w.id for w in PRETORIA_TO_CAPE_TOWN]


def test_stamps_are_issued_in_route_order(store):
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=50, step_minutes=30)
    stamps = build_passport(JOURNEY_A)["stamps"]
    assert [s["ordinal"] for s in stamps] == sorted(s["ordinal"] for s in stamps)


def test_stamps_carry_provenance_and_distance(store):
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=50, step_minutes=30)
    for stamp in build_passport(JOURNEY_A)["stamps"]:
        assert stamp["source"] == "corridor-simulation"
        assert stamp["province"]
        # Every stamp is within the radius that authorised it, by construction.
        assert stamp["distance_meters"] <= STAMP_RADIUS_METERS


def test_stamps_record_the_provinces_crossed(store):
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=50, step_minutes=30)
    assert build_passport(JOURNEY_A)["provinces_visited"] == [
        "Gauteng", "Northern Cape", "Western Cape"
    ]


def test_a_late_starting_feed_leaves_an_explicit_gap(store):
    """
    A feed that begins at De Aar cannot honestly stamp Pretoria, Kimberley or
    Park Station. The passport says so specifically rather than showing a
    gap with no explanation.
    """
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="de_aar", steps=20, step_minutes=30)
    passport = build_passport(JOURNEY_A)
    stamped = {s["waypoint_id"] for s in passport["stamps"]}
    assert "pretoria" not in stamped
    assert "de_aar" in stamped
    assert "began at De Aar" in passport["coverage_note"]


def test_a_journey_mid_karoo_stamps_nothing(store):
    # Standing between stations, with nothing within the radius, must not
    # collect a stamp for the station it happens to be nearest to.
    store.record_telemetry(JOURNEY_A, -31.5, 23.3, source="corridor")
    assert build_passport(JOURNEY_A)["stamps_earned"] == 0


def test_the_origin_station_is_reported_before_movement(store):
    """
    The simulator used to take its first sample a full step *past* the
    origin, so a journey departing Pretoria never came within stamping
    distance of Pretoria and its passport always began with a gap.
    """
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=3, step_minutes=30)
    first = store.recent_telemetry(JOURNEY_A)[0]
    pretoria = PRETORIA_TO_CAPE_TOWN[0]
    assert abs(first.latitude - pretoria.latitude) < 0.001


def test_passport_is_json_serialisable(store):
    import json

    simulate_corridor_run(JOURNEY_A, start_waypoint_id="kimberley", steps=8)
    assert json.loads(json.dumps(build_passport(JOURNEY_A)))["journey_id"] == JOURNEY_A


def test_passport_survives_a_store_reopen(tmp_path, monkeypatch):
    # Stamps are derived from persisted telemetry, so they cannot be lost to
    # a redeploy the way an in-process counter would be.
    db = str(tmp_path / "corridor.sqlite")
    first = SpatialStore(sqlite_path=db)
    first.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", first)
    simulate_corridor_run(JOURNEY_A, start_waypoint_id="pretoria", steps=50, step_minutes=30)
    before = build_passport(JOURNEY_A)["stamps_earned"]
    first.close()

    second = SpatialStore(sqlite_path=db)
    second.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", second)
    assert build_passport(JOURNEY_A)["stamps_earned"] == before
