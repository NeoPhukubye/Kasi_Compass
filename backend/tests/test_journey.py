"""
Unit tests for the Journey Guardian and the ticket validation store.

Run with: pytest backend/tests/test_journey.py

These cover the two modules behind the pitch's load-bearing claims: a
journey that keeps reporting itself from the corridor, and a tracking link
a family member can open without an app.
"""

import pytest

from app.story_engine.eta import compute_eta
from app.story_engine.journey import (
    GUARDIAN_TOKEN_PATTERN,
    JourneyRegistry,
    generate_guardian_token,
    is_valid_journey_id,
)
from app.story_engine.spatial import SpatialStore
from app.story_engine.tickets import (
    TicketStore,
    TicketValidationError,
    is_valid_reference,
    normalize_reference,
)
import app.story_engine.spatial as spatial_module

JOURNEY_A = "11111111-1111-4111-8111-111111111111"
JOURNEY_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture()
def store(monkeypatch):
    """
    Point the ETA engine and the guardian at a private in-memory store.

    Only `spatial.spatial_store` needs replacing: eta.py and journey.py both
    reach the store through the spatial module rather than binding the name
    themselves, so there is exactly one binding to swap.
    """
    s = SpatialStore(sqlite_path=":memory:")
    s.ensure_schema()
    monkeypatch.setattr(spatial_module, "spatial_store", s)
    return s


@pytest.fixture()
def registry(store):
    return JourneyRegistry()


# ---------------------------------------------------------------------
# Journey ids and tokens
# ---------------------------------------------------------------------

def test_journey_id_must_be_uuid_shaped():
    assert is_valid_journey_id(JOURNEY_A)
    assert not is_valid_journey_id("not-a-uuid")
    # A journey id is a handle, not a profile: anything carrying structure
    # (a name, an email, a sequential number) is rejected outright.
    assert not is_valid_journey_id("mthabo-ndlovu")
    assert not is_valid_journey_id("12345")


def test_generated_guardian_tokens_are_url_safe_and_distinct():
    tokens = {generate_guardian_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(GUARDIAN_TOKEN_PATTERN.match(t) for t in tokens)


# ---------------------------------------------------------------------
# Journeys
# ---------------------------------------------------------------------

def test_create_journey_rejects_a_non_uuid_id(registry):
    with pytest.raises(ValueError):
        registry.create_journey("mthabo")


def test_reporting_a_position_creates_the_journey_implicitly(registry, store):
    # The corridor is the source of truth. If a wayside beacon reports a
    # position for a journey the API has never heard of, the journey should
    # exist afterwards rather than the report being dropped.
    registry.report_position(JOURNEY_A, -26.0, 28.0, source="corridor")
    assert registry.get_journey(JOURNEY_A) is not None
    assert store.latest_telemetry(JOURNEY_A).source == "corridor"


def test_reported_position_produces_an_eta(store, registry):
    registry.report_position(JOURNEY_A, -26.0, 28.0, speed_mps=17.0, source="corridor")
    result = registry.report_position(JOURNEY_A, -27.0, 27.0, speed_mps=17.0, source="corridor")
    assert result["eta"]["position"]["nearest_waypoint_id"] != ""
    assert result["eta"]["last_report_source"] == "corridor"


def test_position_survives_a_process_restart(tmp_path, monkeypatch):
    """
    The whole moat argument, tested properly.

    The journey's position lives in the database, not in the process, so a
    brand-new store over the same file — a cold start, a redeploy, a
    horizontal scale-out — still resolves where the train is. Without this,
    a family link would go blank the moment the backend recycled.
    """
    db_path = str(tmp_path / "corridor.sqlite")
    first = SpatialStore(sqlite_path=db_path)
    first.ensure_schema()
    first.record_telemetry(JOURNEY_A, -27.0, 27.0, source="corridor", recorded_at=1_000.0)
    first.close()

    second = SpatialStore(sqlite_path=db_path)
    second.ensure_schema()
    recovered = second.latest_telemetry(JOURNEY_A)
    assert recovered is not None
    assert recovered.latitude == pytest.approx(-27.0)
    assert recovered.source == "corridor"

    # And a fresh ETA can be computed from the database alone, with no
    # in-process journey object having been carried over.
    monkeypatch.setattr(spatial_module, "spatial_store", second)
    result = compute_eta(JOURNEY_A, now=1_060.0)
    assert result.position is not None
    assert result.last_report_source == "corridor"


def test_eta_for_a_journey_that_never_reported_says_waiting(registry):
    result = registry.eta_for(JOURNEY_B)
    assert result["status"] == "no_data"
    assert result["position"] is None
    assert "waiting" in result["delay_display"].lower()


# ---------------------------------------------------------------------
# Guardian links
# ---------------------------------------------------------------------

def test_issuing_a_link_for_an_unknown_journey_raises(registry):
    with pytest.raises(ValueError):
        registry.issue_link(JOURNEY_A)


def test_a_link_resolves_to_its_own_journey(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A, display_name="Ada's journey")
    assert registry.resolve_link(link.token).journey_id == JOURNEY_A


def test_a_link_carries_no_identity_beyond_its_display_label(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A, display_name="Ada's journey")
    assert link.as_dict()["display_name"] == "Ada's journey"
    # Nothing else in the payload identifies a person, a device or a session.
    assert set(link.as_dict()) == {
        "token", "journey_id", "created_at", "revoked", "label", "display_name",
    }


def test_revoking_a_link_takes_effect_immediately(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A)
    assert registry.resolve_link(link.token) is not None
    assert registry.revoke_link(link.token) is True
    # Not "eventually" — the family member's next poll fails now.
    assert registry.resolve_link(link.token) is None


def test_revoking_a_link_makes_family_view_raise(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A)
    registry.revoke_link(link.token)
    with pytest.raises(LookupError):
        registry.family_view(link.token)


def test_an_unknown_token_does_not_resolve(registry):
    assert registry.resolve_link("totally-made-up-token-value") is None
    with pytest.raises(LookupError):
        registry.family_view("totally-made-up-token-value")


def test_a_malformed_token_does_not_resolve(registry):
    for bad in ("", "short", "x" * 200, "has spaces in it here", "semi;colon--value"):
        assert registry.resolve_link(bad) is None


def test_revoking_an_unknown_token_reports_failure(registry):
    assert registry.revoke_link("never-existed-at-all") is False


def test_links_are_scoped_to_one_journey(registry):
    registry.create_journey(JOURNEY_A)
    registry.create_journey(JOURNEY_B)
    link_a = registry.issue_link(JOURNEY_A)
    assert [link.journey_id for link in registry.links_for(JOURNEY_A)] == [JOURNEY_A]
    assert registry.links_for(JOURNEY_B) == []
    assert registry.family_view(link_a.token)["journey"]["journey_id"] == JOURNEY_A


def test_revoked_links_drop_out_of_the_journeys_link_count(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A)
    assert registry.get_journey(JOURNEY_A).as_dict()["guardian_link_count"] == 1
    registry.revoke_link(link.token)
    assert registry.get_journey(JOURNEY_A).as_dict()["guardian_link_count"] == 0


def test_family_view_reports_where_the_position_came_from(registry, store):
    """
    Provenance is the point. A family member must be able to tell a
    corridor-fed position from a phone-fed one, because those carry very
    different promises about what happens when the phone dies.
    """
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A)
    registry.report_position(JOURNEY_A, -26.0, 28.0, source="corridor")
    view = registry.family_view(link.token)
    assert view["eta"]["last_report_source"] == "corridor"
    assert view["headline"]


def test_family_view_for_an_unstarted_journey_still_renders(registry):
    registry.create_journey(JOURNEY_A)
    link = registry.issue_link(JOURNEY_A)
    view = registry.family_view(link.token)
    assert view["status"] == "no_data"
    assert view["eta"]["milestones"] == []
    assert "waiting" in view["headline"].lower()


# ---------------------------------------------------------------------
# Ticket validation
# ---------------------------------------------------------------------

def test_reference_normalisation_is_forgiving():
    # People type these off a screenshot. A missing or lowercase space must
    # not look like a ticket that does not exist.
    assert normalize_reference("ab12cde") == "AB12 CDE"
    assert normalize_reference("AB12 CDE") == "AB12 CDE"
    assert normalize_reference("  ab12   cde ") == "AB12 CDE"
    assert is_valid_reference("ab12cde")
    assert is_valid_reference("AB12 CDE")
    assert not is_valid_reference("ABCDEFG")
    assert not is_valid_reference("AB12 CD")


def test_issued_ticket_is_admissible():
    store = TicketStore()
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town", holder_label="Ms Ndlovu")
    assert store.validate(ticket.booking_reference)["admissible"] is True
    assert ticket.as_dict()["holder_label"] == "Ms Ndlovu"


def test_a_used_ticket_cannot_be_reused():
    """
    One-way transitions are what make a journey's server-side identity
    durable: once boarded, the ticket cannot be boarded again, so a
    screenshot of someone else's ticket is worth nothing.
    """
    store = TicketStore()
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town")
    store.board(ticket.booking_reference, journey_id=JOURNEY_A)
    with pytest.raises(TicketValidationError):
        store.board(ticket.booking_reference, journey_id=JOURNEY_B)
    assert store.get_by_reference(ticket.booking_reference).journey_id == JOURNEY_A


def test_a_voided_ticket_can_never_be_boarded():
    store = TicketStore()
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town")
    store.void(ticket.booking_reference, reason="cancelled by passenger")
    result = store.validate(ticket.booking_reference)
    assert result["admissible"] is False
    assert "voided" in result["reason"].lower()
    with pytest.raises(TicketValidationError):
        store.board(ticket.booking_reference)


def test_an_expired_ticket_is_refused():
    store = TicketStore()
    now = 1_000_000.0
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town", valid_hours=1, now=now)
    assert store.validate(ticket.booking_reference, now=now + 60)["admissible"] is True
    result = store.validate(ticket.booking_reference, now=now + 7_200)
    assert result["admissible"] is False
    assert "validity window" in result["reason"].lower()


def test_validity_hours_are_capped():
    store = TicketStore()
    now = 1_000_000.0
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town", valid_hours=9_999, now=now)
    assert ticket.valid_until - ticket.valid_from == pytest.approx(72 * 3600)


def test_an_unknown_reference_raises():
    store = TicketStore()
    with pytest.raises(TicketValidationError):
        store.validate("ZZ99 XXX")


def test_duplicate_references_are_rejected():
    store = TicketStore()
    store.issue("pretoria_cape_town", "pretoria", "cape_town", booking_reference="AB12 CDE")
    with pytest.raises(TicketValidationError):
        store.issue("pretoria_cape_town", "pretoria", "cape_town", booking_reference="ab12cde")


def test_a_completed_ticket_cannot_be_voided():
    store = TicketStore()
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town")
    store.board(ticket.booking_reference, journey_id=JOURNEY_A)
    store.complete(ticket.booking_reference)
    with pytest.raises(TicketValidationError):
        store.void(ticket.booking_reference)


def test_validation_history_is_recorded_for_audit():
    store = TicketStore()
    ticket = store.issue("pretoria_cape_town", "pretoria", "cape_town")
    store.board(ticket.booking_reference, journey_id=JOURNEY_A)
    store.complete(ticket.booking_reference)
    actions = [v["action"] for v in store.get_by_reference(ticket.booking_reference).validations]
    assert actions == ["boarded", "completed"]
