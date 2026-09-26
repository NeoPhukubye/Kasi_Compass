"""
Spatial persistence for the Pretoria-Cape Town corridor — the PostgreSQL +
PostGIS layer named in the project pitch.

Why this module exists
----------------------
Until now every spatial answer in this project was answered by an in-memory
list of `Waypoint` dataclasses in route.py. That is fine for triggering a
story when a rider walks past Kimberley station, and useless for the three
things the pitch actually promises:

  1. Route geometry that a database can actually answer spatial questions
     against ("how far off-corridor is this position?", "what fraction along
     the line is it?").
  2. Journey telemetry that survives a process restart, so a family link
     does not go blank the moment the backend recycles.
  3. An ETA that is derived from observed corridor speed, not from a
     passenger's phone reporting in.

Dual-driver design
------------------
`SpatialStore` speaks PostgreSQL/PostGIS when `DATABASE_URL` is set, and
falls back to a self-contained SQLite store otherwise. Both drivers return
the *same* `CorridorPosition` and `CorridorNode` dataclasses, so eta.py,
journey.py and the API layer never branch on which database is live.

The SQLite path is not a toy: it implements the same along-track projection
that PostGIS does with ST_ClosestPoint/ST_LineLocatePoint, in pure Python.
That keeps the whole system demonstrable with zero infrastructure (which is
what a hackathon demo actually needs) while the PostGIS path is the real
production target, using genuine geography types rather than lat/lon floats.

Nothing here is on the AI path. No model call touches this module.
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from dataclasses import dataclass

from app.story_engine.route import (
    METERS_PER_DEGREE_LATITUDE,
    PRETORIA_TO_CAPE_TOWN,
    Waypoint,
)

# Where to find the PostGIS connection string. Absent by design — the lab
# build and the demo run entirely on the SQLite fallback.
DATABASE_URL_ENV = "DATABASE_URL"

# A position further than this from the corridor centreline is not "on the
# corridor" — it is somewhere off in the Karoo. Used to reject obviously
# bogus telemetry rather than to refuse service.
CORRIDOR_TOLERANCE_METERS = 25_000.0

# How much telemetry to retain per journey. A 27-hour trip sampled every 30s
# is ~3,200 points; capping at the most recent 5,000 means we keep the whole
# trip with headroom and never grow unbounded for a stalled feed.
MAX_TELEMETRY_POINTS = 5_000


@dataclass(frozen=True)
class CorridorNode:
    """One station on the corridor, with its position along the line."""

    waypoint_id: str
    name: str
    province: str
    latitude: float
    longitude: float
    sequence: int
    cumulative_km: float


@dataclass(frozen=True)
class CorridorPosition:
    """
    A point resolved against the corridor. This is the unit of currency
    between the spatial layer and everything above it — the API, the ETA
    engine and the Journey Guardian all speak `CorridorPosition`, so swapping
    PostGIS in or out changes nothing downstream.
    """

    latitude: float
    longitude: float
    progress_fraction: float
    distance_along_km: float
    total_km: float
    remaining_km: float
    nearest_waypoint_id: str
    nearest_waypoint_name: str
    province: str
    distance_to_corridor_m: float
    driver: str

    def as_dict(self) -> dict:
        return {
            "lat": self.latitude,
            "lon": self.longitude,
            "progress_fraction": self.progress_fraction,
            "distance_along_km": self.distance_along_km,
            "total_km": self.total_km,
            "remaining_km": self.remaining_km,
            "nearest_waypoint_id": self.nearest_waypoint_id,
            "nearest_waypoint_name": self.nearest_waypoint_name,
            "province": self.province,
            "distance_to_corridor_m": self.distance_to_corridor_m,
            "driver": self.driver,
        }


@dataclass(frozen=True)
class TelemetryPoint:
    """A single corridor-sourced position report for a journey."""

    journey_id: str
    latitude: float
    longitude: float
    speed_mps: float | None
    recorded_at: float
    source: str

    def as_dict(self) -> dict:
        return {
            "journey_id": self.journey_id,
            "lat": self.latitude,
            "lon": self.longitude,
            "speed_mps": self.speed_mps,
            "recorded_at": self.recorded_at,
            "source": self.source,
        }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    from app.story_engine.geofence import haversine_meters

    return haversine_meters(lat1, lon1, lat2, lon2) / 1_000.0


def _project_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float, float]:
    """
    Project point P onto segment A->B, returning
    (t along segment, perpendicular distance in meters, projected lat, projected lon).

    All six inputs are (longitude, latitude) pairs — x is longitude, y is
    latitude — and the working frame scales longitude by cos(latitude) so
    the two axes stay metric at a given mid-latitude.

    Over a ~200km Karoo segment the distortion this introduces is far below
    the 150m coordinate fuzzing the live-share layer already applies, so it is
    not worth the cost of a full geodesic solve.
    """
    mid_lat = math.radians((ay + by) / 2.0)
    kx = math.cos(mid_lat) * METERS_PER_DEGREE_LATITUDE
    ky = METERS_PER_DEGREE_LATITUDE

    ax_m, ay_m = ax * kx, ay * ky
    bx_m, by_m = bx * kx, by * ky
    px_m, py_m = px * kx, py * ky

    dx, dy = bx_m - ax_m, by_m - ay_m
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / seg_len_sq))

    cx_m = ax_m + t * dx
    cy_m = ay_m + t * dy
    distance = math.hypot(px_m - cx_m, py_m - cy_m)
    return t, distance, cy_m / ky, cx_m / kx


class SpatialStore:
    """
    Corridor geometry + journey telemetry, on PostGIS when available and on
    SQLite when not.

    Constructed once per process and shared, mirroring how content_store.py
    and live_share.py expose module-level singletons.
    """

    def __init__(self, dsn: str | None = None, sqlite_path: str | None = None) -> None:
        self._dsn = dsn if dsn is not None else os.environ.get(DATABASE_URL_ENV, "").strip() or None
        self._sqlite_path = sqlite_path or os.environ.get("SQLITE_PATH", "").strip() or None
        self._conn = None
        self._driver = "sqlite"
        self._node_cache: list[CorridorNode] | None = None
        self._ensured = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def driver(self) -> str:
        return "postgis" if self._dsn else "sqlite"

    def connect(self) -> None:
        """
        Open the live driver and make sure its schema exists. Safe to call
        repeatedly. Falls back to SQLite if a PostGIS DSN is configured but
        the driver or the server is unreachable, so a demo never dies on a
        missing database.

        Schema creation happens here rather than at FastAPI startup on
        purpose: unit tests and CLI tools construct a SpatialStore directly
        and never run an app lifespan, and lazily creating the schema means
        they work identically to the deployed service. The DDL is idempotent
        (CREATE TABLE IF NOT EXISTS) and the seed is an upsert, so this costs
        a handful of statements once per process.
        """
        if self._conn is not None:
            if not self._ensured:
                self._run_schema()
            return
        if self._dsn:
            try:
                self._conn = self._connect_postgis(self._dsn)
                self._driver = "postgis"
            except Exception:
                self._conn = None
                self._dsn = None
        if self._conn is None:
            self._conn = self._connect_sqlite(self._sqlite_path)
            self._driver = "sqlite"
        self._run_schema()

    def _run_schema(self) -> None:
        if self._ensured:
            return
        self._ensured = True
        statements = self._POSTGIS_SCHEMA if self._driver == "postgis" else self._SQLITE_SCHEMA
        for statement in statements:
            self._conn.execute(statement)  # type: ignore[attr-defined]
        self._conn.commit()  # type: ignore[attr-defined]
        self.seed_corridor()

    @staticmethod
    def _connect_postgis(dsn: str):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on deployment
            raise RuntimeError(
                "DATABASE_URL is set but psycopg is not installed. "
                "Run: pip install 'psycopg[binary,pool]'"
            ) from exc
        conn = psycopg.connect(dsn)
        return conn

    @staticmethod
    def _connect_sqlite(path: str | None):
        if path in (None, "", ":memory:"):
            conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    _POSTGIS_SCHEMA = (
        """
        CREATE EXTENSION IF NOT EXISTS postgis;
        """,
        """
        CREATE TABLE IF NOT EXISTS corridor_waypoints (
            waypoint_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            province      TEXT NOT NULL DEFAULT '',
            sequence      INTEGER NOT NULL UNIQUE,
            story_theme   TEXT NOT NULL DEFAULT '',
            geom          geometry(Point, 4326) NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS corridor_lines (
            corridor_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            geom          geometry(LineString, 4326) NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS journey_telemetry (
            id            BIGSERIAL PRIMARY KEY,
            journey_id    TEXT NOT NULL,
            lat           DOUBLE PRECISION NOT NULL,
            lon           DOUBLE PRECISION NOT NULL,
            speed_mps     DOUBLE PRECISION,
            source        TEXT NOT NULL DEFAULT 'corridor',
            recorded_at   DOUBLE PRECISION NOT NULL
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS journey_telemetry_lookup
            ON journey_telemetry (journey_id, recorded_at DESC);
        """,
        """
        CREATE INDEX IF NOT EXISTS corridor_waypoints_geom
            ON corridor_waypoints USING GIST (geom);
        """,
        """
        CREATE TABLE IF NOT EXISTS guardian_journeys (
            journey_id              TEXT PRIMARY KEY,
            corridor_id             TEXT NOT NULL,
            origin_waypoint_id      TEXT NOT NULL,
            destination_waypoint_id TEXT NOT NULL,
            created_at              DOUBLE PRECISION NOT NULL,
            ticket_id               TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS guardian_links (
            token         TEXT PRIMARY KEY,
            journey_id    TEXT NOT NULL,
            created_at    DOUBLE PRECISION NOT NULL,
            revoked       BOOLEAN NOT NULL DEFAULT FALSE,
            label         TEXT NOT NULL DEFAULT 'family',
            display_name  TEXT NOT NULL DEFAULT ''
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS guardian_links_journey
            ON guardian_links (journey_id, revoked);
        """,
    )

    _SQLITE_SCHEMA = (
        """
        CREATE TABLE IF NOT EXISTS corridor_waypoints (
            waypoint_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            province      TEXT NOT NULL DEFAULT '',
            sequence      INTEGER NOT NULL UNIQUE,
            story_theme   TEXT NOT NULL DEFAULT '',
            lat           REAL NOT NULL,
            lon           REAL NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS corridor_lines (
            corridor_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            lat_lon_json  TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS journey_telemetry (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            journey_id    TEXT NOT NULL,
            lat           REAL NOT NULL,
            lon           REAL NOT NULL,
            speed_mps     REAL,
            source        TEXT NOT NULL DEFAULT 'corridor',
            recorded_at   REAL NOT NULL
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS journey_telemetry_lookup
            ON journey_telemetry (journey_id, recorded_at DESC);
        """,
        """
        CREATE TABLE IF NOT EXISTS guardian_journeys (
            journey_id            TEXT PRIMARY KEY,
            corridor_id           TEXT NOT NULL,
            origin_waypoint_id    TEXT NOT NULL,
            destination_waypoint_id TEXT NOT NULL,
            created_at            DOUBLE PRECISION NOT NULL,
            ticket_id             TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS guardian_links (
            token         TEXT PRIMARY KEY,
            journey_id    TEXT NOT NULL,
            created_at    DOUBLE PRECISION NOT NULL,
            revoked       INTEGER NOT NULL DEFAULT 0,
            label         TEXT NOT NULL DEFAULT 'family',
            display_name  TEXT NOT NULL DEFAULT ''
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS guardian_links_journey
            ON guardian_links (journey_id, revoked);
        """,
    )

    def ensure_schema(self, seed: bool = True) -> None:
        """
        Create tables (and spatial indexes) and seed the corridor.

        Idempotent, and called automatically by connect() — exposed because
        the API's startup hook and the tests both want to call it explicitly
        and assert that a schema problem surfaces at boot rather than as a
        500 to a family member's browser.
        """
        self.connect()
        self._ensured = False
        self._run_schema()
        if seed:
            self.corridor_nodes(refresh=True)

    def seed_corridor(self, waypoints: list[Waypoint] | None = None) -> None:
        """
        Upsert the corridor from route.py, and materialise the centreline as
        an ordered LineString so the spatial queries have a real geometry to
        work against rather than reconstructing it per request.
        """
        self.connect()
        nodes = waypoints if waypoints is not None else PRETORIA_TO_CAPE_TOWN

        if self._driver == "postgis":
            for index, w in enumerate(nodes):
                self._conn.execute(  # type: ignore[attr-defined]
                    """
                    INSERT INTO corridor_waypoints
                        (waypoint_id, name, province, sequence, story_theme, geom)
                    VALUES (%s, %s, %s, %s, %s,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    ON CONFLICT (waypoint_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        province = EXCLUDED.province,
                        sequence = EXCLUDED.sequence,
                        story_theme = EXCLUDED.story_theme,
                        geom = EXCLUDED.geom
                    """,
                    (w.id, w.name, w.province, index, w.story_theme, w.longitude, w.latitude),
                )
            coordinates = ", ".join(f"({w.longitude} {w.latitude})" for w in nodes)
            self._conn.execute(  # type: ignore[attr-defined]
                f"""
                INSERT INTO corridor_lines (corridor_id, name, geom)
                VALUES ('pretoria_cape_town', 'Pretoria to Cape Town',
                        ST_GeomFromText('LINESTRING({coordinates})', 4326))
                ON CONFLICT (corridor_id) DO UPDATE SET geom = EXCLUDED.geom
                """,
            )
            self._conn.commit()  # type: ignore[attr-defined]
            return

        for index, w in enumerate(nodes):
            self._conn.execute(  # type: ignore[attr-defined]
                """
                INSERT INTO corridor_waypoints
                    (waypoint_id, name, province, sequence, story_theme, lat, lon)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(waypoint_id) DO UPDATE SET
                    name = excluded.name,
                    province = excluded.province,
                    sequence = excluded.sequence,
                    story_theme = excluded.story_theme,
                    lat = excluded.lat,
                    lon = excluded.lon
                """,
                (w.id, w.name, w.province, index, w.story_theme, w.latitude, w.longitude),
            )
        import json

        self._conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO corridor_lines (corridor_id, name, lat_lon_json)
            VALUES ('pretoria_cape_town', 'Pretoria to Cape Town', ?)
            ON CONFLICT(corridor_id) DO UPDATE SET lat_lon_json = excluded.lat_lon_json
            """,
            (json.dumps([[w.longitude, w.latitude] for w in nodes]),),
        )
        self._conn.commit()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Corridor geometry
    # ------------------------------------------------------------------

    def corridor_nodes(self, refresh: bool = False) -> list[CorridorNode]:
        """
        The corridor in order, each node carrying its cumulative distance from
        Pretoria. Cached per instance: the corridor geometry is static
        reference data, and re-deriving it on every position update would
        dominate the request cost.
        """
        if self._node_cache is not None and not refresh:
            return self._node_cache
        self.connect()
        if self._driver == "postgis":
            rows = self._conn.execute(  # type: ignore[attr-defined]
                """
                SELECT waypoint_id, name, province, sequence,
                       ST_Y(geom) AS lat, ST_X(geom) AS lon
                FROM corridor_waypoints
                ORDER BY sequence
                """
            ).fetchall()
        else:
            rows = self._conn.execute(  # type: ignore[attr-defined]
                """
                SELECT waypoint_id, name, province, sequence, lat, lon
                FROM corridor_waypoints
                ORDER BY sequence
                """
            ).fetchall()

        nodes: list[CorridorNode] = []
        cumulative = 0.0
        for index, row in enumerate(rows):
            if index > 0:
                previous = nodes[-1]
                cumulative += haversine_km(previous.latitude, previous.longitude, row["lat"], row["lon"])
            nodes.append(
                CorridorNode(
                    waypoint_id=row["waypoint_id"],
                    name=row["name"],
                    province=row["province"] or "",
                    latitude=float(row["lat"]),
                    longitude=float(row["lon"]),
                    sequence=index,
                    cumulative_km=round(cumulative, 2),
                )
            )
        self._node_cache = nodes
        return nodes

    def total_km(self) -> float:
        nodes = self.corridor_nodes()
        return nodes[-1].cumulative_km if nodes else 0.0

    def corridor_geometry(self) -> dict:
        """
        GeoJSON-ish payload for the map: an ordered LineString plus the
        per-node metadata (province, sequence, distance from origin) that
        Journey Guardian milestones are built on.
        """
        nodes = self.corridor_nodes()
        return {
            "corridor_id": "pretoria_cape_town",
            "name": "Pretoria to Cape Town",
            "driver": self.driver,
            "total_km": self.total_km(),
            "coordinates": [[node.longitude, node.latitude] for node in nodes],
            "nodes": [
                {
                    "waypoint_id": n.waypoint_id,
                    "name": n.name,
                    "province": n.province,
                    "sequence": n.sequence,
                    "lat": n.latitude,
                    "lon": n.longitude,
                    "cumulative_km": n.cumulative_km,
                }
                for n in nodes
            ],
        }

    # ------------------------------------------------------------------
    # Position resolution
    # ------------------------------------------------------------------

    def resolve_position(self, lat: float, lon: float) -> CorridorPosition:
        """
        Snap an arbitrary position onto the corridor centreline and report how
        far along it is.

        On PostGIS this is ST_Distance / ST_ClosestPoint / ST_LineLocatePoint
        against the stored LineString geography — a genuine spatial query,
        not a Python loop. On SQLite the same answer is computed in-process.
        """
        self.connect()
        if self._driver == "postgis":
            return self._resolve_postgis(lat, lon)
        return self._resolve_python(lat, lon)

    def _resolve_postgis(self, lat: float, lon: float) -> CorridorPosition:
        row = self._conn.execute(  # type: ignore[attr-defined]
            """
            WITH line AS (
                SELECT geom::geography AS geog FROM corridor_lines
                WHERE corridor_id = 'pretoria_cape_town'
            ),
            point AS (
                SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography AS geog
            ),
            closest AS (
                SELECT ST_ClosestPoint(line.geog, point.geog) AS pt
                FROM line, point
            )
            SELECT
                ST_Latitude(pt) AS lat,
                ST_Longitude(pt) AS lon,
                ST_Distance(line.geog, point.geog) AS off_m,
                ST_Length(line.geog) / 1000.0 AS total_km,
                ST_LineLocatePoint(line.geog::geometry, ST_ClosestPoint(line.geog, point.geog)::geometry) AS progress
            FROM line, point, closest
            """,
            (lon, lat),
        ).fetchone()

        nodes = self.corridor_nodes()
        if row is None or not nodes:
            return self._resolve_python(lat, lon)

        total_km = float(row["total_km"])
        progress = max(0.0, min(1.0, float(row["progress"])))
        return self._build_position(
            latitude=float(row["lat"]),
            longitude=float(row["lon"]),
            progress=progress,
            total_km=total_km,
            off_m=float(row["off_m"]),
            driver="postgis",
        )

    def _resolve_python(self, lat: float, lon: float) -> CorridorPosition:
        """
        Pure-Python along-track projection. Walks every corridor segment,
        keeps the closest, and converts the result into a fraction of total
        corridor length. O(segments) per call — 7 segments here, which is
        cheaper than a database round trip, which is why the SQLite path
        doesn't pretend to need one.
        """
        nodes = self.corridor_nodes()
        if len(nodes) < 2:
            return CorridorPosition(
                latitude=lat,
                longitude=lon,
                progress_fraction=0.0,
                distance_along_km=0.0,
                total_km=0.0,
                remaining_km=0.0,
                nearest_waypoint_id=nodes[0].waypoint_id if nodes else "",
                nearest_waypoint_name=nodes[0].name if nodes else "",
                province=nodes[0].province if nodes else "",
                distance_to_corridor_m=0.0,
                driver="sqlite",
            )

        best: tuple[float, float, float, float] | None = None
        for index in range(len(nodes) - 1):
            a, b = nodes[index], nodes[index + 1]
            segment_km = b.cumulative_km - a.cumulative_km
            t, off_m, proj_lat, proj_lon = _project_on_segment(
                lon, lat, a.longitude, a.latitude, b.longitude, b.latitude
            )
            along_km = a.cumulative_km + t * segment_km
            if best is None or off_m < best[0]:
                best = (off_m, along_km, proj_lat, proj_lon)

        off_m, along_km, proj_lat, proj_lon = best  # type: ignore[misc]
        total_km = nodes[-1].cumulative_km
        progress = max(0.0, min(1.0, along_km / total_km)) if total_km else 0.0
        return self._build_position(
            latitude=proj_lat,
            longitude=proj_lon,
            progress=progress,
            total_km=total_km,
            off_m=off_m,
            driver="sqlite",
        )

    def _build_position(
        self,
        latitude: float,
        longitude: float,
        progress: float,
        total_km: float,
        off_m: float,
        driver: str,
    ) -> CorridorPosition:
        """
        Shared tail of both drivers: convert a fraction-along-the-line into
        the station the rider is nearest.

        Nearest by *distance*, not by sequence number. The eight stations on
        this corridor are not evenly spaced — Kimberley to De Aar is ~250km
        while Beaufort West to Matjiesfontein is ~180km — so picking by index
        would report a train standing at De Aar as being at Beaufort West.
        """
        nodes = self.corridor_nodes()
        if not nodes:
            return CorridorPosition(
                latitude=latitude,
                longitude=longitude,
                progress_fraction=progress,
                distance_along_km=0.0,
                total_km=total_km,
                remaining_km=total_km,
                nearest_waypoint_id="",
                nearest_waypoint_name="",
                province="",
                distance_to_corridor_m=off_m,
                driver=driver,
            )

        nearest = min(
            nodes,
            key=lambda node: haversine_km(node.latitude, node.longitude, latitude, longitude),
        )
        along_km = progress * total_km
        return CorridorPosition(
            latitude=latitude,
            longitude=longitude,
            progress_fraction=progress,
            distance_along_km=round(along_km, 2),
            total_km=round(total_km, 2),
            remaining_km=round(max(0.0, total_km - along_km), 2),
            nearest_waypoint_id=nearest.waypoint_id,
            nearest_waypoint_name=nearest.name,
            province=nearest.province,
            distance_to_corridor_m=round(off_m, 1),
            driver=driver,
        )

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def record_telemetry(
        self,
        journey_id: str,
        lat: float,
        lon: float,
        speed_mps: float | None = None,
        source: str = "corridor",
        recorded_at: float | None = None,
    ) -> TelemetryPoint:
        """
        Append a corridor-sourced position report for a journey.

        This is the write path that makes the pitch's central claim true:
        a journey's position is established by *infrastructure reporting in*,
        so it keeps updating whether or not the passenger's phone is alive,
        charged, or has signal.
        """
        self.connect()
        recorded_at = recorded_at if recorded_at is not None else time.time()
        self._conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO journey_telemetry
                (journey_id, lat, lon, speed_mps, source, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (journey_id, lat, lon, speed_mps, source, recorded_at),
        )
        self._conn.execute(  # type: ignore[attr-defined]
            """
            DELETE FROM journey_telemetry
            WHERE journey_id = ? AND id NOT IN (
                SELECT id FROM journey_telemetry
                WHERE journey_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            )
            """,
            (journey_id, journey_id, MAX_TELEMETRY_POINTS),
        )
        self._conn.commit()  # type: ignore[attr-defined]
        return TelemetryPoint(
            journey_id=journey_id,
            latitude=lat,
            longitude=lon,
            speed_mps=speed_mps,
            recorded_at=recorded_at,
            source=source,
        )

    def recent_telemetry(self, journey_id: str, limit: int = 20) -> list[TelemetryPoint]:
        """Most recent position reports first. Oldest-first for the caller."""
        self.connect()
        rows = self._conn.execute(  # type: ignore[attr-defined]
            """
            SELECT journey_id, lat, lon, speed_mps, source, recorded_at
            FROM journey_telemetry
            WHERE journey_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (journey_id, limit),
        ).fetchall()
        return [
            TelemetryPoint(
                journey_id=row["journey_id"],
                latitude=float(row["lat"]),
                longitude=float(row["lon"]),
                speed_mps=float(row["speed_mps"]) if row["speed_mps"] is not None else None,
                recorded_at=float(row["recorded_at"]),
                source=row["source"],
            )
            for row in reversed(rows)
        ]

    def latest_telemetry(self, journey_id: str) -> TelemetryPoint | None:
        points = self.recent_telemetry(journey_id, limit=1)
        return points[0] if points else None

    def journey_count(self) -> int:
        self.connect()
        row = self._conn.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(DISTINCT journey_id) AS n FROM journey_telemetry"
        ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # Guardian journeys and links
    #
    # Persisting these matters for a reason that is easy to underrate: a
    # family tracking link is a capability somebody has already pasted into
    # a WhatsApp message. If a redeploy invalidates it, the product silently
    # breaks the promise it was built on, and the person who finds out is the
    # family member, not the operator.
    # ------------------------------------------------------------------

    def save_journey(self, journey: dict) -> None:
        """Upsert a journey's own record. Journey *positions* live in
        journey_telemetry; this is the identity that links them together."""
        self.connect()
        self._conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO guardian_journeys
                (journey_id, corridor_id, origin_waypoint_id,
                 destination_waypoint_id, created_at, ticket_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(journey_id) DO UPDATE SET
                corridor_id = excluded.corridor_id,
                origin_waypoint_id = excluded.origin_waypoint_id,
                destination_waypoint_id = excluded.destination_waypoint_id,
                ticket_id = excluded.ticket_id
            """,
            (
                journey["journey_id"],
                journey["corridor_id"],
                journey["origin_waypoint_id"],
                journey["destination_waypoint_id"],
                journey["created_at"],
                journey.get("ticket_id"),
            ),
        )
        self._conn.commit()  # type: ignore[attr-defined]

    def load_journeys(self) -> list[dict]:
        self.connect()
        rows = self._conn.execute(  # type: ignore[attr-defined]
            """
            SELECT journey_id, corridor_id, origin_waypoint_id,
                   destination_waypoint_id, created_at, ticket_id
            FROM guardian_journeys
            ORDER BY created_at
            """
        ).fetchall()
        return [
            {
                "journey_id": row["journey_id"],
                "corridor_id": row["corridor_id"],
                "origin_waypoint_id": row["origin_waypoint_id"],
                "destination_waypoint_id": row["destination_waypoint_id"],
                "created_at": float(row["created_at"]),
                "ticket_id": row["ticket_id"],
            }
            for row in rows
        ]

    def save_link(self, link: dict) -> None:
        self.connect()
        self._conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO guardian_links
                (token, journey_id, created_at, revoked, label, display_name)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
                revoked = excluded.revoked,
                label = excluded.label,
                display_name = excluded.display_name
            """,
            (
                link["token"],
                link["journey_id"],
                link["created_at"],
                1 if link["revoked"] else 0,
                link.get("label") or "family",
                link.get("display_name") or "",
            ),
        )
        self._conn.commit()  # type: ignore[attr-defined]

    def load_link(self, token: str) -> dict | None:
        self.connect()
        row = self._conn.execute(  # type: ignore[attr-defined]
            """
            SELECT token, journey_id, created_at, revoked, label, display_name
            FROM guardian_links WHERE token = ?
            """,
            (token,),
        ).fetchone()
        return self._link_row_to_dict(row) if row else None

    def load_links_for_journey(self, journey_id: str) -> list[dict]:
        self.connect()
        rows = self._conn.execute(  # type: ignore[attr-defined]
            """
            SELECT token, journey_id, created_at, revoked, label, display_name
            FROM guardian_links WHERE journey_id = ?
            """,
            (journey_id,),
        ).fetchall()
        return [self._link_row_to_dict(row) for row in rows]

    def load_all_links(self) -> list[dict]:
        """Every guardian link ever issued, revoked ones included, so a
        restart can rebuild the registry without resurrecting a cancellation."""
        self.connect()
        rows = self._conn.execute(  # type: ignore[attr-defined]
            """
            SELECT token, journey_id, created_at, revoked, label, display_name
            FROM guardian_links ORDER BY created_at
            """
        ).fetchall()
        return [self._link_row_to_dict(row) for row in rows]

    def revoke_link(self, token: str) -> bool:
        """
        Revoke a link in the database.

        This is the durability guarantee that matters: a revoke is written
        immediately rather than held in memory until something happens to
        flush, so a restart cannot resurrect a link the rider has cancelled.
        """
        self.connect()
        cursor = self._conn.execute(  # type: ignore[attr-defined]
            "UPDATE guardian_links SET revoked = 1 WHERE token = ?", (token,)
        )
        self._conn.commit()  # type: ignore[attr-defined]
        return cursor.rowcount > 0

    @staticmethod
    def _link_row_to_dict(row) -> dict:
        return {
            "token": row["token"],
            "journey_id": row["journey_id"],
            "created_at": float(row["created_at"]),
            "revoked": bool(row["revoked"]),
            "label": row["label"],
            "display_name": row["display_name"],
        }


# Single shared instance for the running process.
spatial_store = SpatialStore()
