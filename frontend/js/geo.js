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
