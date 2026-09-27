"""
Railway Alerts & Service Notifications.

Pushes service disruption alerts to users: delays, cancellations,
track works, "rail moved", signal failures, etc.

The alert model is deliberately simple and corridor-scoped: an alert
belongs to a route (e.g. Pretoria-Cape Town) and optionally a
specific journey. Family links and rider apps can subscribe to the
relevant corridor.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    """Severity levels for railway alerts."""

    INFO = "info"           # Planned works, minor notices
    WARNING = "warning"     # Delays, speed restrictions
    CRITICAL = "critical"   # Cancellations, line blockages, rail moved


class AlertCategory(str, Enum):
    """Categories of railway alerts."""

    DELAY = "delay"
    CANCELLATION = "cancellation"
    TRACK_WORKS = "track_works"
    SIGNAL_FAILURE = "signal_failure"
    RAIL_MOVED = "rail_moved"
    SPEED_RESTRICTION = "speed_restriction"
    PLATFORM_CHANGE = "platform_change"
    SERVICE_DISRUPTION = "service_disruption"
    WEATHER = "weather"
    OTHER = "other"


@dataclass(frozen=True)
class Alert:
    """A railway service alert."""

    alert_id: str
    corridor_id: str
    category: AlertCategory
    severity: AlertSeverity
    title: str
    message: str
    created_at: float
    updated_at: float
    expires_at: float | None = None
    journey_id: str | None = None
    affected_stations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "corridor_id": self.corridor_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "journey_id": self.journey_id,
            "affected_stations": self.affected_stations,
            "metadata": self.metadata,
            "is_active": self.is_active(),
        }

    def is_active(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if self.expires_at is not None and now > self.expires_at:
            return False
        return True


# In-memory store for alerts (in production, persist to database)
_alerts: dict[str, Alert] = {}
_corridor_index: dict[str, set[str]] = {}  # corridor_id -> set of alert_ids


def _index_alert(alert: Alert) -> None:
    _corridor_index.setdefault(alert.corridor_id, set()).add(alert.alert_id)


def _unindex_alert(alert: Alert) -> None:
    if alert.corridor_id in _corridor_index:
        _corridor_index[alert.corridor_id].discard(alert.alert_id)
        if not _corridor_index[alert.corridor_id]:
            del _corridor_index[alert.corridor_id]


def create_alert(
    corridor_id: str,
    category: AlertCategory,
    severity: AlertSeverity,
    title: str,
    message: str,
    journey_id: str | None = None,
    affected_stations: list[str] | None = None,
    expires_in_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
    now: float | None = None,
) -> Alert:
    """Create a new railway alert."""
    now = now if now is not None else time.time()
    alert_id = str(uuid.uuid4())
    expires_at = now + expires_in_seconds if expires_in_seconds else None

    alert = Alert(
        alert_id=alert_id,
        corridor_id=corridor_id,
        category=category,
        severity=severity,
        title=title,
        message=message,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
        journey_id=journey_id,
        affected_stations=affected_stations or [],
        metadata=metadata or {},
    )

    _alerts[alert_id] = alert
    _index_alert(alert)
    return alert


def get_alert(alert_id: str) -> Alert | None:
    """Get an alert by ID."""
    return _alerts.get(alert_id)


def get_alerts_for_corridor(
    corridor_id: str,
    include_expired: bool = False,
    now: float | None = None,
) -> list[Alert]:
    """Get all alerts for a corridor, sorted by severity then creation time."""
    now = now if now is not None else time.time()
    alert_ids = _corridor_index.get(corridor_id, set())
    alerts = [_alerts[aid] for aid in alert_ids if aid in _alerts]

    if not include_expired:
        alerts = [a for a in alerts if a.is_active(now)]

    # Sort: critical first, then warning, then info; within each, newest first
    severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.created_at))
    return alerts


def get_alerts_for_journey(
    journey_id: str,
    corridor_id: str,
    include_expired: bool = False,
    now: float | None = None,
) -> list[Alert]:
    """Get alerts relevant to a specific journey (corridor-wide + journey-specific)."""
    corridor_alerts = get_alerts_for_corridor(corridor_id, include_expired, now)
    journey_alerts = [a for a in corridor_alerts if a.journey_id == journey_id]
    general_alerts = [a for a in corridor_alerts if a.journey_id is None]
    # Journey-specific alerts first, then general corridor alerts
    return journey_alerts + general_alerts


def update_alert(
    alert_id: str,
    title: str | None = None,
    message: str | None = None,
    severity: AlertSeverity | None = None,
    expires_in_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
    now: float | None = None,
) -> Alert | None:
    """Update an existing alert."""
    now = now if now is not None else time.time()
    alert = _alerts.get(alert_id)
    if alert is None:
        return None

    _unindex_alert(alert)

    updated = Alert(
        alert_id=alert.alert_id,
        corridor_id=alert.corridor_id,
        category=alert.category,
        severity=severity if severity is not None else alert.severity,
        title=title if title is not None else alert.title,
        message=message if message is not None else alert.message,
        created_at=alert.created_at,
        updated_at=now,
        expires_at=now + expires_in_seconds if expires_in_seconds is not None else alert.expires_at,
        journey_id=alert.journey_id,
        affected_stations=alert.affected_stations,
        metadata={**alert.metadata, **(metadata or {})},
    )

    _alerts[alert_id] = updated
    _index_alert(updated)
    return updated


def expire_alert(alert_id: str, now: float | None = None) -> bool:
    """Expire an alert immediately."""
    now = now if now is not None else time.time()
    return update_alert(alert_id, expires_in_seconds=0, now=now) is not None


def delete_alert(alert_id: str) -> bool:
    """Permanently delete an alert."""
    alert = _alerts.pop(alert_id, None)
    if alert:
        _unindex_alert(alert)
        return True
    return False


# Predefined alert templates for common scenarios
ALERT_TEMPLATES = {
    "rail_moved": {
        "category": AlertCategory.RAIL_MOVED,
        "severity": AlertSeverity.CRITICAL,
        "title": "Rail Displacement Detected",
        "message": "The rail has shifted on the {corridor} line between {stations}. Trains are stopped until repairs are complete. Expect significant delays.",
    },
    "signal_failure": {
        "category": AlertCategory.SIGNAL_FAILURE,
        "severity": AlertSeverity.CRITICAL,
        "title": "Signal Failure",
        "message": "Signalling equipment has failed on the {corridor} line near {stations}. Trains are being held at stations. No estimated restoration time yet.",
    },
    "major_delay": {
        "category": AlertCategory.DELAY,
        "severity": AlertSeverity.WARNING,
        "title": "Major Delay",
        "message": "Trains on the {corridor} line are running {delay} behind schedule due to {reason}. Next update at {next_update}.",
    },
    "cancellation": {
        "category": AlertCategory.CANCELLATION,
        "severity": AlertSeverity.CRITICAL,
        "title": "Service Cancelled",
        "message": "The {train_number} service on the {corridor} line has been cancelled. Alternative transport is being arranged. Please check for rebooking options.",
    },
    "track_works": {
        "category": AlertCategory.TRACK_WORKS,
        "severity": AlertSeverity.INFO,
        "title": "Planned Track Works",
        "message": "Maintenance work is scheduled on the {corridor} line between {stations} from {start} to {end}. Trains may run on a modified timetable.",
    },
    "speed_restriction": {
        "category": AlertCategory.SPEED_RESTRICTION,
        "severity": AlertSeverity.WARNING,
        "title": "Speed Restriction in Effect",
        "message": "A temporary speed restriction of {speed} km/h is in place on the {corridor} line between {stations} due to {reason}. Expect delays of approximately {delay}.",
    },
    "platform_change": {
        "category": AlertCategory.PLATFORM_CHANGE,
        "severity": AlertSeverity.INFO,
        "title": "Platform Change",
        "message": "The {train_number} at {station} will now depart from platform {platform} instead of the usual platform. Please proceed to the new platform.",
    },
    "weather_disruption": {
        "category": AlertCategory.WEATHER,
        "severity": AlertSeverity.WARNING,
        "title": "Weather-Related Disruption",
        "message": "Severe weather ({condition}) is affecting the {corridor} line. Trains are running at reduced speed for safety. Delays of {delay} are expected.",
    },
}


def create_alert_from_template(
    template_key: str,
    corridor_id: str,
    substitutions: dict[str, str],
    journey_id: str | None = None,
    affected_stations: list[str] | None = None,
    expires_in_seconds: float | None = None,
    now: float | None = None,
) -> Alert | None:
    """Create an alert from a predefined template with substitutions."""
    template = ALERT_TEMPLATES.get(template_key)
    if not template:
        return None

    title = template["title"].format(**substitutions, corridor=corridor_id)
    message = template["message"].format(**substitutions, corridor=corridor_id)

    return create_alert(
        corridor_id=corridor_id,
        category=template["category"],
        severity=template["severity"],
        title=title,
        message=message,
        journey_id=journey_id,
        affected_stations=affected_stations,
        expires_in_seconds=expires_in_seconds,
        now=now,
    )


def get_active_alert_count(corridor_id: str, now: float | None = None) -> dict[str, int]:
    """Get count of active alerts by severity for a corridor."""
    alerts = get_alerts_for_corridor(corridor_id, include_expired=False, now=now)
    counts = {s.value: 0 for s in AlertSeverity}
    for alert in alerts:
        counts[alert.severity.value] += 1
    return counts


# ---------------------------------------------------------------------
# Passenger Alert Subscriptions
#
# Links a passenger's ticket/journey to alert delivery. When a ticket is
# boarded (onboarding), the passenger subscribes to alerts for their
# corridor and journey. When the ticket is completed (offboarding), the
# subscription is removed.
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class AlertSubscription:
    """A passenger's subscription to railway alerts for a specific journey."""

    subscription_id: str
    ticket_id: str
    booking_reference: str
    journey_id: str | None
    corridor_id: str
    origin_waypoint_id: str
    destination_waypoint_id: str
    subscribed_at: float
    last_notified_at: float | None = None
    is_active: bool = True
    notification_preferences: dict = field(default_factory=dict)  # e.g., {"push": true, "sms": false}

    def as_dict(self) -> dict:
        return {
            "subscription_id": self.subscription_id,
            "ticket_id": self.ticket_id,
            "booking_reference": self.booking_reference,
            "journey_id": self.journey_id,
            "corridor_id": self.corridor_id,
            "origin_waypoint_id": self.origin_waypoint_id,
            "destination_waypoint_id": self.destination_waypoint_id,
            "subscribed_at": self.subscribed_at,
            "last_notified_at": self.last_notified_at,
            "is_active": self.is_active,
            "notification_preferences": self.notification_preferences,
        }


_subscriptions: dict[str, AlertSubscription] = {}  # subscription_id -> subscription
_ticket_subscriptions: dict[str, str] = {}  # ticket_id -> subscription_id
_journey_subscriptions: dict[str, set[str]] = {}  # journey_id -> set of subscription_ids


def _index_subscription(sub: AlertSubscription) -> None:
    _ticket_subscriptions[sub.ticket_id] = sub.subscription_id
    if sub.journey_id:
        _journey_subscriptions.setdefault(sub.journey_id, set()).add(sub.subscription_id)


def _unindex_subscription(sub: AlertSubscription) -> None:
    _ticket_subscriptions.pop(sub.ticket_id, None)
    if sub.journey_id and sub.journey_id in _journey_subscriptions:
        _journey_subscriptions[sub.journey_id].discard(sub.subscription_id)
        if not _journey_subscriptions[sub.journey_id]:
            del _journey_subscriptions[sub.journey_id]


def create_alert_subscription(
    ticket_id: str,
    booking_reference: str,
    corridor_id: str,
    origin_waypoint_id: str,
    destination_waypoint_id: str,
    journey_id: str | None = None,
    notification_preferences: dict | None = None,
    now: float | None = None,
) -> AlertSubscription:
    """Create an alert subscription for a passenger's ticket (onboarding)."""
    now = now if now is not None else time.time()
    subscription_id = str(uuid.uuid4())

    # Deactivate any existing subscription for this ticket
    existing_sub_id = _ticket_subscriptions.get(ticket_id)
    if existing_sub_id and existing_sub_id in _subscriptions:
        existing = _subscriptions[existing_sub_id]
        _unindex_subscription(existing)
        _subscriptions[existing_sub_id] = AlertSubscription(
            **{**existing.__dict__, "is_active": False, "last_notified_at": now}
        )

    sub = AlertSubscription(
        subscription_id=subscription_id,
        ticket_id=ticket_id,
        booking_reference=booking_reference,
        journey_id=journey_id,
        corridor_id=corridor_id,
        origin_waypoint_id=origin_waypoint_id,
        destination_waypoint_id=destination_waypoint_id,
        subscribed_at=now,
        notification_preferences=notification_preferences or {"push": True, "in_app": True},
    )

    _subscriptions[subscription_id] = sub
    _index_subscription(sub)
    return sub


def get_subscription_by_ticket(ticket_id: str) -> AlertSubscription | None:
    """Get active subscription for a ticket."""
    sub_id = _ticket_subscriptions.get(ticket_id)
    if sub_id and sub_id in _subscriptions:
        sub = _subscriptions[sub_id]
        if sub.is_active:
            return sub
    return None


def get_subscription_by_journey(journey_id: str) -> list[AlertSubscription]:
    """Get all active subscriptions for a journey."""
    sub_ids = _journey_subscriptions.get(journey_id, set())
    return [_subscriptions[sid] for sid in sub_ids if sid in _subscriptions and _subscriptions[sid].is_active]


def deactivate_subscription(ticket_id: str, now: float | None = None) -> AlertSubscription | None:
    """Deactivate a subscription (offboarding)."""
    now = now if now is not None else time.time()
    sub_id = _ticket_subscriptions.get(ticket_id)
    if not sub_id or sub_id not in _subscriptions:
        return None
    sub = _subscriptions[sub_id]
    _unindex_subscription(sub)
    updated = AlertSubscription(
        **{**sub.__dict__, "is_active": False, "last_notified_at": now}
    )
    _subscriptions[sub_id] = updated
    return updated


def get_relevant_alerts_for_subscription(
    subscription_id: str,
    include_expired: bool = False,
    now: float | None = None,
) -> list[Alert]:
    """Get alerts relevant to a passenger's subscription (journey-specific + corridor-wide)."""
    sub = _subscriptions.get(subscription_id)
    if not sub or not sub.is_active:
        return []
    return get_alerts_for_journey(sub.journey_id or "", sub.corridor_id, include_expired, now)


def mark_subscription_notified(subscription_id: str, now: float | None = None) -> AlertSubscription | None:
    """Update last_notified_at for a subscription."""
    now = now if now is not None else time.time()
    sub = _subscriptions.get(subscription_id)
    if not sub:
        return None
    updated = AlertSubscription(**{**sub.__dict__, "last_notified_at": now})
    _subscriptions[subscription_id] = updated
    return updated


def get_all_active_subscriptions() -> list[AlertSubscription]:
    """Get all active subscriptions (for notification delivery)."""
    return [s for s in _subscriptions.values() if s.is_active]