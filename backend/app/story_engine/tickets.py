"""
Ticket validation — the "ticket validation databases" claim in the unfair
advantage section of the pitch.

The argument this module is meant to make concrete: a safety product that
only works if a passenger keeps their phone alive is a product that fails
exactly when it is needed. Binding a journey's tracking to a validated
ticket means the train's identity, its route, and its family link all exist
server-side and keep existing whether or not anyone is holding a device.

Deliberately scoped as a *reference* implementation, not a payments system:

- No card data, no payment processing, no personal data of any kind. A
  ticket here is a booking reference, a corridor, a date, and a validity
  window — the minimum needed to decide "is this person supposed to be on
  this train".
- Status transitions are one-way and explicit. A ticket cannot be
  revalidated after it is voided, so a screenshot of a used ticket is worth
  nothing.
- Everything is in-process. The point of the module is the model and the
  invariants, which a judge's "how would this work with PRASA's system"
  question can be answered against concretely.

No AI anywhere in this path.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field

# Booking references in the shape South African rail operators issue:
# two letters, two digits, three letters (e.g. "KQ7 4TP"). Validated rather
# than generated free-form so a typo'd reference is a 422, not a 404 from a
# ticket that never existed.
BOOKING_REFERENCE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[ ]?[A-Z]{3}$")

VALID_TICKET_STATUSES = ("issued", "valid", "boarded", "completed", "void")
# Boarding can only move a ticket forward. Everything else is a refusal.
_BOARDABLE_FROM = ("issued", "valid")

MAX_TICKET_HOLD_HOURS = 72.0


def normalize_reference(reference: str) -> str:
    """
    Canonical form: uppercased, all whitespace stripped, then a single space
    inserted in the operator's fixed position — "ab12cde", "AB12 CDE" and
    "AB12CDE" all become "AB12 CDE".

    People type these off a screenshot into a phone keyboard, and getting the
    space wrong must not look like an unknown ticket.
    """
    compact = re.sub(r"\s+", "", reference.strip().upper())
    if len(compact) == 7:
        return f"{compact[:4]} {compact[4:]}"
    return compact


def is_valid_reference(reference: str) -> bool:
    return bool(BOOKING_REFERENCE_PATTERN.match(normalize_reference(reference)))


def generate_reference() -> str:
    """Mint a reference in the operator's shape, for the demo path."""
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O — misread on a phone camera
    digits = "0123456789"
    return "".join(secrets.choice(letters) for _ in range(2)) + \
        "".join(secrets.choice(digits) for _ in range(2)) + " " + \
        "".join(secrets.choice(letters) for _ in range(3))


@dataclass
class Ticket:
    """
    A validated booking. Carries no passenger identity: `holder_label` is a
    free-text the operator or the rider supplies ("Ms Ndlovu", "Group 4") and
    is never joined to anything else in this system.
    """

    ticket_id: str
    booking_reference: str
    corridor_id: str
    origin_waypoint_id: str
    destination_waypoint_id: str
    issued_at: float
    valid_from: float
    valid_until: float
    holder_label: str = ""
    status: str = "issued"
    journey_id: str | None = None
    validations: list[dict] = field(default_factory=list)

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now > self.valid_until

    def as_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "booking_reference": self.booking_reference,
            "corridor_id": self.corridor_id,
            "origin_waypoint_id": self.origin_waypoint_id,
            "destination_waypoint_id": self.destination_waypoint_id,
            "issued_at": self.issued_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "holder_label": self.holder_label,
            "status": self.status,
            "expired": self.is_expired(),
            "journey_id": self.journey_id,
            "validation_count": len(self.validations),
        }


class TicketValidationError(Exception):
    """Raised when a ticket cannot move to the requested state. The API
    layer turns this into a 422 with the reason as the detail."""


class TicketStore:
    """In-process ticket registry. Single process — see journey.py for why."""

    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}
        self._by_reference: dict[str, str] = {}

    def issue(
        self,
        corridor_id: str,
        origin_waypoint_id: str,
        destination_waypoint_id: str,
        holder_label: str = "",
        booking_reference: str | None = None,
        valid_hours: float = 48.0,
        now: float | None = None,
    ) -> Ticket:
        """
        Issue a ticket. `valid_hours` bounds the validity window so a stale
        reference cannot be replayed weeks later — capped at
        MAX_TICKET_HOLD_HOURS regardless of what the caller asks for.
        """
        now = now if now is not None else time.time()
        hours = max(0.5, min(valid_hours, MAX_TICKET_HOLD_HOURS))

        reference = normalize_reference(booking_reference) if booking_reference else generate_reference()
        if not is_valid_reference(reference):
            raise TicketValidationError(
                f"booking_reference must match the operator format (e.g. 'AB12 CDE'), got {reference!r}"
            )
        if reference in self._by_reference:
            raise TicketValidationError(f"booking_reference already issued: {reference}")

        ticket = Ticket(
            ticket_id=secrets.token_urlsafe(12),
            booking_reference=reference,
            corridor_id=corridor_id,
            origin_waypoint_id=origin_waypoint_id,
            destination_waypoint_id=destination_waypoint_id,
            issued_at=now,
            valid_from=now,
            valid_until=now + hours * 3600.0,
            holder_label=holder_label.strip()[:80],
        )
        self._tickets[ticket.ticket_id] = ticket
        self._by_reference[reference] = ticket.ticket_id
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def get_by_reference(self, reference: str) -> Ticket | None:
        ticket_id = self._by_reference.get(normalize_reference(reference))
        return self._tickets.get(ticket_id) if ticket_id else None

    def validate(self, reference: str, now: float | None = None) -> dict:
        """
        Check a booking reference without consuming it — what a conductor or
        a station scanner does at the gate. Returns the ticket plus an
        explicit `admissible` flag and, when it is False, the reason.
        """
        now = now if now is not None else time.time()
        ticket = self.get_by_reference(reference)
        if ticket is None:
            raise TicketValidationError(f"unknown booking reference: {normalize_reference(reference)}")

        reason = ""
        if ticket.status == "void":
            reason = "This ticket has been voided."
        elif ticket.status in ("boarded", "completed"):
            reason = f"This ticket was already used (status: {ticket.status})."
        elif ticket.is_expired(now):
            reason = "This ticket's validity window has closed."

        return {
            "admissible": not reason,
            "reason": reason,
            "ticket": ticket.as_dict(),
        }

    def board(self, reference: str, journey_id: str | None = None, now: float | None = None) -> Ticket:
        """
        Consume a ticket at boarding, binding it to a journey.

        One-way: a used ticket cannot be boarded again, which is what makes
        the journey's server-side identity durable. After this, the journey
        exists independently of any device the passenger is carrying.
        """
        now = now if now is not None else time.time()
        check = self.validate(reference, now=now)
        if not check["admissible"]:
            raise TicketValidationError(check["reason"])

        ticket = self.get_by_reference(reference)
        assert ticket is not None  # validate() already proved it exists
        ticket.status = "boarded"
        ticket.journey_id = journey_id
        ticket.validations.append(
            {"action": "boarded", "at": now, "journey_id": journey_id}
        )
        return ticket

    def complete(self, reference: str, now: float | None = None) -> Ticket:
        """Mark a journey's ticket as completed on arrival at the destination."""
        now = now if now is not None else time.time()
        ticket = self.get_by_reference(reference)
        if ticket is None:
            raise TicketValidationError(f"unknown booking reference: {normalize_reference(reference)}")
        if ticket.status == "void":
            raise TicketValidationError("This ticket has been voided.")
        if ticket.status != "boarded":
            raise TicketValidationError(f"Only a boarded ticket can be completed (status: {ticket.status}).")
        ticket.status = "completed"
        ticket.validations.append({"action": "completed", "at": now})
        return ticket

    def void(self, reference: str, reason: str = "", now: float | None = None) -> Ticket:
        """
        Void a ticket. Terminal: a voided ticket can never be boarded, which
        is what stops a photo of a cancelled booking from being replayed.
        """
        now = now if now is not None else time.time()
        ticket = self.get_by_reference(reference)
        if ticket is None:
            raise TicketValidationError(f"unknown booking reference: {normalize_reference(reference)}")
        if ticket.status == "completed":
            raise TicketValidationError("A completed ticket cannot be voided.")
        ticket.status = "void"
        ticket.validations.append({"action": "voided", "at": now, "reason": reason[:200]})
        return ticket

    def count(self) -> int:
        return len(self._tickets)


# Single shared instance for the running process.
ticket_store = TicketStore()
