const API_BASE = window.KASI_API_BASE;

async function fetchRoute() {
    const response = await fetch(`${API_BASE}/journey/route`);
    if (!response.ok) {
        throw new Error(`Failed to fetch route: ${response.statusText}`);
    }
    return response.json();
}

async function fetchPosition(lat, lon, language = 'en') {
    // URLSearchParams handles encoding, so numeric values and any future
    // non-ASCII language codes (e.g. language names with spaces) are escaped
    // correctly rather than being interpolated raw into the URL.
    const params = new URLSearchParams({
        lat: String(lat),
        lon: String(lon),
        language: language,
    });

    const response = await fetch(`${API_BASE}/journey/position?${params.toString()}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch position: ${response.statusText}`);
    }
    return response.json();
}

async function fetchPOIs(waypointId) {
    const response = await fetch(`${API_BASE}/journey/pois?waypoint_id=${encodeURIComponent(waypointId)}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch POIs: ${response.statusText}`);
    }
    return response.json();
}
