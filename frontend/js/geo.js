// Shared geospatial helpers for the frontend map.
//
// NOTE: this is a client-side approximation used only for smoothly animating
// the train icon and showing "approaching X" hints. The backend remains the
// single source of truth for which waypoint actually triggers a story
// (see backend/app/story_engine/geofence.py) — do not rely on this for
// triggering decisions.

function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

// Project a point onto a single route segment (a -> b), treating the segment
// as a flat plane. Over inter-station distances (tens to a few hundred km) the
// planar error is well under what matters for animating an icon, and it keeps
// this cheap enough to run on every animation frame.
//
// Returns { lat, lon, t, distanceFromStart } where t is the clamped fraction
// along the segment and distanceFromStart is meters from `a` to the projected
// point.
function projectOntoSegment(lat, lon, aLat, aLon, bLat, bLon) {
    const toRad = x => x * Math.PI / 180;
    // Meters per degree, scaled by latitude so east-west distances are correct.
    const mPerDegLat = 111320;
    const mPerDegLon = 111320 * Math.cos(toRad((aLat + bLat) / 2));

    const abx = (bLon - aLon) * mPerDegLon;
    const aby = (bLat - aLat) * mPerDegLat;
    const apx = (lon - aLon) * mPerDegLon;
    const apy = (lat - aLat) * mPerDegLat;

    const segLenSq = abx * abx + aby * aby;
    let t = segLenSq === 0 ? 0 : (apx * abx + apy * aby) / segLenSq;
    t = Math.max(0, Math.min(1, t));

    return {
        lat: aLat + t * (bLat - aLat),
        lon: aLon + t * (bLon - aLon),
        t,
        distanceFromStart: t * Math.sqrt(segLenSq),
    };
}

// Given a rider's position and the ordered route waypoints (each with lat/lon),
// return the true along-track progress as a fraction in [0, 1] by projecting
// onto the nearest route segment and measuring cumulative geodesic distance.
//
// This is what makes the train icon move *smoothly* rather than jumping from
// station to station, which is all a nearest-waypoint estimate (index / (n-1))
// can ever do. Still a client-side approximation for animation and
// "approaching X" hints only — backend geofence.py remains the single source
// of truth for which waypoint actually triggers a story.
function alongTrackProgress(lat, lon, routeWaypoints) {
    if (!routeWaypoints || routeWaypoints.length < 2) return null;

    // Cumulative geodesic length up to each waypoint, so a projection's
    // distance-into-segment can be converted into distance-along-route.
    const cumulative = [0];
    for (let i = 1; i < routeWaypoints.length; i++) {
        const prev = routeWaypoints[i - 1];
        const curr = routeWaypoints[i];
        cumulative.push(
            cumulative[i - 1] +
            haversineMeters(prev.lat, prev.lon, curr.lat, curr.lon)
        );
    }
    const totalLength = cumulative[cumulative.length - 1];
    if (totalLength === 0) return 0;

    let best = null;

    for (let i = 0; i < routeWaypoints.length - 1; i++) {
        const a = routeWaypoints[i];
        const b = routeWaypoints[i + 1];

        const proj = projectOntoSegment(lat, lon, a.lat, a.lon, b.lat, b.lon);
        // Distance from the rider to the projected point on this segment,
        // measured with the existing haversine so it is consistent with the
        // segment lengths above.
        const offTrack = haversineMeters(lat, lon, proj.lat, proj.lon);

        if (best === null || offTrack < best.offTrack) {
            best = {
                offTrack,
                distanceAlong: cumulative[i] + proj.distanceFromStart,
            };
        }
    }

    if (!best) return null;
    return Math.max(0, Math.min(1, best.distanceAlong / totalLength));
}
