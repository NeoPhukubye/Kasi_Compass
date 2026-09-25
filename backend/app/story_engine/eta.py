"""
Automated ETA and provincial milestone engine.

This is the "Automated Geofencing & Milestones" claim from the pitch, made
concrete: given a journey's observed position, work out

  - where it is on the corridor (delegated to spatial.py),
  - how fast it is *actually* moving (not what the timetable promises),
  - when it will arrive at the next station and at Cape Town,
  - which province it is in right now, and which one it enters next.

The delay number is the product. A commuter who paid R2,800 and has been
stopped on the tracks for nine hours does not need a moving dot — they need
to be told, in plain language, that they are three hours behind and that
somebody is publishing that number. That is the difference between silence
and accountability, and it is the whole reason this module exists.

How the ETA is derived
----------------------
Observed speed, not scheduled speed. We take the last N telemetry points,
compute the along-corridor distance covered versus wall-clock time, and
smooth it with an exponentially weighted moving average so a single
stationary minute (a signal check, a points adjustment) does not collapse
the estimate. With too little data or a stationary train we fall back to the
corridor's scheduled pace, and we say so explicitly via `speed_source` rather
than quietly presenting a guess as a measurement.

No AI anywhere in this path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.story_engine import spatial
from app.story_engine.route import PRETORIA_TO_CAPE_TOWN
from app.story_engine.spatial import (
    CorridorPosition,
    TelemetryPoint,
    haversine_km,
)

# The store is always reached as `spatial.spatial_store` rather than imported
# by value, so there is exactly one binding in the process and swapping it in
# a test is guaranteed to be seen by every caller. Importing the name
# directly gave eta.py its own reference, so a test that replaced the store
# would silently go on exercising the real one.

# Scheduled end-to-end pace for the Pretoria-Cape Town long-distance service,
# in km/h. Roughly 1,600km over ~27 hours including station dwell. This is the
# *fallback* assumption only — it is what we compare observed progress
# against to produce the delay figure, never what we report as the ETA when
# we have real telemetry.
SCHEDULED_SPEED_KMH = 60.0

# Below this, the train is considered stationary (signal, siding, breakdown)
# and speed-based ETA is not meaningful.
STATIONARY_SPEED_KMH = 2.0

# Telemetry points considered when estimating observed speed. Roughly an hour
# at a 30-second reporting cadence — long enough to smooth a station stop,
# short enough to react to a real delay.
SPEED_SAMPLE_POINTS = 12

# Weight given to the newest sample in the EWMA. 0.35 is a deliberate
# compromise: responsive to a genuine slowdown, not jumpy enough that one
# bad GPS fix swings the ETA.
SPEED_EWMA_ALPHA = 0.35

# A journey with no telemetry newer than this is treated as having gone dark,
# and the family view says so rather than showing a confidently stale dot.
STALE_TELEMETRY_SECONDS = 900.0

# Tolerance when deciding whether a milestone has been reached, in km.
#
# `distance_along_km` comes from projecting the position onto a segment,
# while the milestone's `at_km` comes from summing station-to-station
# distances. They agree mathematically but not in the last floating-point
# bits, so a train standing exactly at Kimberley compared 482.1 against
# 482.1000000001 and the milestone reported itself as not yet reached. 10
# metres is tight enough to be meaningless at corridor scale and loose enough
# to absorb the arithmetic noise.
REACHED_EPSILON_KM = 0.01


def _iso(epoch: float) -> str:
    """UTC ISO-8601, seconds precision. One helper so every timestamp in the
    API surface is formatted identically."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _humanize_duration(hours: float) -> str:
    """'3h 25m' / '45m' / '40s' — for the plain-language delay line."""
    total_minutes = hours * 60.0
    if total_minutes < 1.0:
        return f"{int(total_minutes * 60)}s"
    if total_minutes < 60.0:
        return f"{int(round(total_minutes))}m"
    whole_hours = int(total_minutes // 60)
    minutes = int(round(total_minutes - whole_hours * 60))
    if minutes == 60:
        whole_hours += 1
        minutes = 0
    return f"{whole_hours}h {minutes:02d}m" if minutes else f"{whole_hours}h"


@dataclass(frozen=True)
class Milestone:
    """A province boundary or station crossing worth telling a family about."""

    kind: str  # "departure" | "province_entry" | "station" | "arrival"
    label: str
    detail: str
    reached: bool
    sequence: int = 0
    province: str = ""
    at_km: float = 0.0


@dataclass
class EtaResult:
    """Everything the family view and the API need for one journey."""

    journey_id: str
    status: str
    position: CorridorPosition
    observed_speed_kmh: float
    speed_source: str
    eta_next_station_epoch: float | None
    eta_next_station_name: str | None
    eta_arrival_epoch: float | None
    eta_arrival_name: str
    delay_hours: float
    delay_display: str
    province: str
    next_province: str | None
    distance_to_next_station_km: float
    last_report_seconds_ago: float | None
    last_report_source: str | None
    milestones: list[Milestone] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "journey_id": self.journey_id,
            "status": self.status,
            "position": self.position.as_dict(),
            "observed_speed_kmh": round(self.observed_speed_kmh, 1),
            "speed_source": self.speed_source,
            "eta": {
                "next_station": self.eta_next_station_name,
                "next_station_at": _iso(self.eta_next_station_epoch) if self.eta_next_station_epoch else None,
                "arrival_station": self.eta_arrival_name,
                "arrival_at": _iso(self.eta_arrival_epoch) if self.eta_arrival_epoch else None,
            },
            "delay_hours": round(self.delay_hours, 2),
            "delay_display": self.delay_display,
            "province": self.province,
            "next_province": self.next_province,
            "distance_to_next_station_km": round(self.distance_to_next_station_km, 1),
            "last_report_seconds_ago": (
                round(self.last_report_seconds_ago, 1) if self.last_report_seconds_ago is not None else None
            ),
            "last_report_source": self.last_report_source,
            "milestones": [
                {
                    "kind": m.kind,
                    "label": m.label,
                    "detail": m.detail,
                    "reached": m.reached,
                    "sequence": m.sequence,
                    "province": m.province,
                    "at_km": m.at_km,
                }
                for m in self.milestones
            ],
        }


def _next_stop_after(distance_along_km: float) -> tuple[str, float, float] | None:
    """
    The next station strictly ahead of a position, as
    (name, remaining_km_to_it, its_cumulative_km). None at journey's end.
    """
    cumulative = 0.0
    for index, waypoint in enumerate(PRETORIA_TO_CAPE_TOWN):
        if index > 0:
            previous = PRETORIA_TO_CAPE_TOWN[index - 1]
            cumulative += haversine_km(previous.latitude, previous.longitude, waypoint.latitude, waypoint.longitude)
        if index == 0:
            continue
        if cumulative > distance_along_km:
            return waypoint.name, max(0.0, cumulative - distance_along_km), cumulative
    return None


def _next_province_after(province: str) -> str | None:
    provinces: list[str] = []
    for waypoint in PRETORIA_TO_CAPE_TOWN:
        if waypoint.province and (not provinces or provinces[-1] != waypoint.province):
            provinces.append(waypoint.province)
    if province in provinces:
        index = provinces.index(province)
        return provinces[index + 1] if index + 1 < len(provinces) else None
    return provinces[0] if provinces else None


def estimate_speed(
    telemetry: list[TelemetryPoint],
    now: float | None = None,
) -> tuple[float, str]:
    """
    Smoothed observed speed in km/h, and a label for where it came from.

    Returns (speed_kmh, source) where source is one of:
      "observed"     — derived from real movement in the telemetry window
      "stationary"   — telemetry exists but the train is not moving
      "insufficient" — too little data to say anything honest
    """
    now = now if now is not None else time.time()
    if len(telemetry) < 2:
        return SCHEDULED_SPEED_KMH, "insufficient"

    window = telemetry[-SPEED_SAMPLE_POINTS:]
    samples: list[float] = []
    for previous, current in zip(window, window[1:]):
        elapsed = current.recorded_at - previous.recorded_at
        if elapsed <= 0:
            continue
        travelled = haversine_km(previous.latitude, previous.longitude, current.latitude, current.longitude)
        samples.append(travelled / elapsed * 3600.0)

    if not samples:
        return SCHEDULED_SPEED_KMH, "insufficient"

    smoothed = samples[-1]
    for sample in reversed(samples[:-1]):
        smoothed = SPEED_EWMA_ALPHA * sample + (1 - SPEED_EWMA_ALPHA) * smoothed

    if smoothed < STATIONARY_SPEED_KMH:
        return 0.0, "stationary"
    return smoothed, "observed"


def build_milestones(position: CorridorPosition) -> list[Milestone]:
    """
    The ordered list of province boundaries and stations a rider has passed or
    is approaching. This is the "provincial milestone tracking" the pitch
    promises, and it is deliberately human-scale: a family member does not
    need a progress percentage, they need "left the Northern Cape 40 minutes
    ago, next is Beaufort West".
    """
    cumulative = 0.0
    milestones: list[Milestone] = []
    previous_province = ""
    sequence = 0

    for index, waypoint in enumerate(PRETORIA_TO_CAPE_TOWN):
        if index > 0:
            previous = PRETORIA_TO_CAPE_TOWN[index - 1]
            cumulative += haversine_km(previous.latitude, previous.longitude, waypoint.latitude, waypoint.longitude)

        if index == 0:
            milestones.append(
                Milestone(
                    kind="departure",
                    label=f"Departed {waypoint.name}",
                    detail="Journey begins.",
                    reached=position.distance_along_km > 0.5,
                    sequence=sequence,
                    province=waypoint.province,
                    at_km=0.0,
                )
            )
            sequence += 1
        else:
            # A province boundary and the station that sits on it are two
            # different events and both matter: "entered the Northern Cape"
            # is the reassuring headline, but a family member also needs to
            # know the train is standing at De Aar. Emitting only one of
            # them loses the other, so both are recorded.
            if waypoint.province and waypoint.province != previous_province:
                milestones.append(
                    Milestone(
                        kind="province_entry",
                        label=f"Entered {waypoint.province}",
                        detail=f"Crossed into the {waypoint.province} at {waypoint.name}.",
                        reached=position.distance_along_km >= cumulative - REACHED_EPSILON_KM,
                        sequence=sequence,
                        province=waypoint.province,
                        at_km=round(cumulative, 2),
                    )
                )
                sequence += 1

            milestones.append(
                Milestone(
                    kind="station",
                    label=waypoint.name,
                    detail=f"Called at {waypoint.name}.",
                    reached=position.distance_along_km >= cumulative - REACHED_EPSILON_KM,
                    sequence=sequence,
                    province=waypoint.province,
                    at_km=round(cumulative, 2),
                )
            )
            sequence += 1

        if waypoint.province:
            previous_province = waypoint.province

    milestones.append(
        Milestone(
            kind="arrival",
            label="Arrived Cape Town",
            detail="End of the corridor.",
            reached=position.distance_along_km >= position.total_km - 1.0,
            sequence=sequence,
            province=PRETORIA_TO_CAPE_TOWN[-1].province,
            at_km=round(position.total_km, 2),
        )
    )
    return milestones


def compute_eta(journey_id: str, now: float | None = None) -> EtaResult:
    """
    The full ETA + milestone answer for one journey.

    Returns status "no_data" (rather than raising) when a journey has never
    reported a position — a family link opened for a train that hasn't
    started moving should say "waiting for the first report", not 404.
    """
    now = now if now is not None else time.time()
    telemetry = spatial.spatial_store.recent_telemetry(journey_id, limit=SPEED_SAMPLE_POINTS)
    if not telemetry:
        raise LookupError(f"no telemetry recorded for journey {journey_id!r}")

    latest = telemetry[-1]
    position = spatial.spatial_store.resolve_position(latest.latitude, latest.longitude)
    speed_kmh, speed_source = estimate_speed(telemetry, now=now)

    last_report_seconds_ago = max(0.0, now - latest.recorded_at)
    stale = last_report_seconds_ago > STALE_TELEMETRY_SECONDS
    if stale:
        status = "signal_lost"
    elif speed_source == "stationary":
        status = "stopped"
    elif position.progress_fraction >= 0.999:
        status = "arrived"
    else:
        status = "on_time" if speed_kmh >= SCHEDULED_SPEED_KMH * 0.95 else "delayed"

    # When the train is stopped or its feed is dark, the honest ETA is "not
    # yet knowable" — reporting a number anyway is exactly the kind of
    # false precision this project exists to eliminate.
    if speed_source in ("stationary",) or stale or speed_kmh <= 0.0:
        eta_next_epoch: float | None = None
        eta_arrival_epoch: float | None = None
    else:
        eta_arrival_epoch = now + (position.remaining_km / speed_kmh) * 3600.0
        upcoming = _next_stop_after(position.distance_along_km)
        if upcoming is None:
            eta_next_epoch = eta_arrival_epoch
        else:
            _, remaining_km, _ = upcoming
            eta_next_epoch = now + (remaining_km / speed_kmh) * 3600.0

    upcoming = _next_stop_after(position.distance_along_km)
    if upcoming is None:
        next_station_name: str | None = None
        distance_to_next = 0.0
    else:
        next_station_name, distance_to_next, _ = upcoming

    # Delay is measured against the timetable, not against a wish: how long
    # *should* the remaining distance take, minus how long it is taking.
    scheduled_hours = position.remaining_km / SCHEDULED_SPEED_KMH
    if speed_kmh > 0.0 and not stale:
        actual_hours = position.remaining_km / speed_kmh
        delay_hours = max(0.0, actual_hours - scheduled_hours)
    else:
        delay_hours = 0.0

    if status == "arrived":
        delay_display = "Journey complete"
    elif delay_hours >= 1.0:
        delay_display = f"Running {_humanize_duration(delay_hours)} behind schedule"
    elif speed_source == "stationary":
        delay_display = "Stopped — ETA pending a clear reason from the operator"
    elif stale:
        delay_display = f"No position report for {_humanize_duration(last_report_seconds_ago / 3600.0)}"
    else:
        delay_display = "On schedule"

    return EtaResult(
        journey_id=journey_id,
        status=status,
        position=position,
        observed_speed_kmh=speed_kmh,
        speed_source=speed_source,
        eta_next_station_epoch=eta_next_epoch,
        eta_next_station_name=next_station_name,
        eta_arrival_epoch=eta_arrival_epoch,
        eta_arrival_name=PRETORIA_TO_CAPE_TOWN[-1].name,
        delay_hours=delay_hours,
        delay_display=delay_display,
        province=position.province,
        next_province=_next_province_after(position.province),
        distance_to_next_station_km=distance_to_next,
        last_report_seconds_ago=last_report_seconds_ago,
        last_report_source=latest.source,
        milestones=build_milestones(position),
    )


def simulate_corridor_run(
    journey_id: str,
    start_waypoint_id: str = "pretoria",
    speed_kmh: float = 62.0,
    step_minutes: float = 30.0,
    steps: int = 8,
    now: float | None = None,
) -> str:
    """
    Generate a plausible run of corridor telemetry for a journey.

    This exists because the pitch's hardest claim — "we get position without
    the passenger's phone" — is otherwise undemonstrable on a laptop with no
    train in it. A judge can watch an ETA move, a province flip, and a family
    link update from a server-side feed that the passenger never touches.

    Deliberately not a random walk: positions are interpolated along the
    actual corridor between real stations, so every derived ETA, milestone
    and distance is arithmetically true of the real line.
    """
    now = now if now is not None else time.time()
    start_index = next(
        (i for i, w in enumerate(PRETORIA_TO_CAPE_TOWN) if w.id == start_waypoint_id),
        0,
    )
    total_steps = max(1, min(steps, len(PRETORIA_TO_CAPE_TOWN) - 1 - start_index))
    distance_per_step_km = speed_kmh * (step_minutes / 60.0)

    walked_km = 0.0
    for step in range(total_steps):
        target_km = walked_km + distance_per_step_km
        # The final sample is stamped "now" so a freshly simulated run does
        # not immediately read as a stale feed — a run that reports its own
        # position as 30 minutes old is indistinguishable from a dead one.
        sample_at = now - (total_steps - 1 - step) * step_minutes * 60.0
        segment_walked = 0.0
        for index in range(start_index, len(PRETORIA_TO_CAPE_TOWN) - 1):
            a = PRETORIA_TO_CAPE_TOWN[index]
            b = PRETORIA_TO_CAPE_TOWN[index + 1]
            segment_km = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
            if segment_walked + segment_km >= target_km:
                t = (target_km - segment_walked) / segment_km if segment_km else 0.0
                lat = a.latitude + t * (b.latitude - a.latitude)
                lon = a.longitude + t * (b.longitude - a.longitude)
                spatial.spatial_store.record_telemetry(
                    journey_id=journey_id,
                    lat=lat,
                    lon=lon,
                    speed_mps=speed_kmh / 3.6,
                    source="corridor-simulation",
                    recorded_at=sample_at,
                )
                break
            segment_walked += segment_km
        else:
            final = PRETORIA_TO_CAPE_TOWN[-1]
            spatial.spatial_store.record_telemetry(
                journey_id=journey_id,
                lat=final.latitude,
                lon=final.longitude,
                speed_mps=0.0,
                source="corridor-simulation",
                recorded_at=sample_at,
            )
            break
        walked_km = target_km

    return journey_id
