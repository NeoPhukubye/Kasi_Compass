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

async function fetchStopDetails(stopId) {
    const response = await fetch(`${API_BASE}/story-engine/stop/${encodeURIComponent(stopId)}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch stop details: ${response.statusText}`);
    }
    const body = await response.json();
    if (body.status !== 'success') {
        throw new Error(`Stop details returned status ${body.status}`);
    }
    return body.data;
}

async function askGuide(question) {
    const response = await fetch(`${API_BASE}/story-engine/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
    });
    if (!response.ok) {
        throw new Error(`Guide request failed: ${response.statusText}`);
    }
    return response.json();
}

async function companionChat(prompt, stopContext = "Shosholoza Route Station Stop") {
    const response = await fetch(`${API_BASE}/story-engine/companion/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, stop_context: stopContext }),
    });
    if (!response.ok) {
        throw new Error(`Companion chat request failed: ${response.statusText}`);
    }
    return response.json();
}

// ---------------------------------------------------------------------
// Spatial layer — corridor geometry and on-corridor position resolution.
// Backed by PostGIS in production and an identical SQLite contract in the
// demo; `driver` in the response says which one answered.
// ---------------------------------------------------------------------

async function fetchCorridor() {
    const response = await fetch(`${API_BASE}/spatial/corridor`);
    if (!response.ok) {
        throw new Error(`Failed to fetch corridor: ${response.statusText}`);
    }
    return response.json();
}

async function resolvePosition(lat, lon) {
    const response = await fetch(`${API_BASE}/spatial/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon }),
    });
    if (!response.ok) {
        throw new Error(`Failed to resolve position: ${response.statusText}`);
    }
    return response.json();
}

// ---------------------------------------------------------------------
// Journey Guardian — server-side journeys, ETAs, and family tracking links.
// ---------------------------------------------------------------------

async function simulateRun(options = {}) {
    const response = await fetch(`${API_BASE}/guardian/simulate-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_waypoint_id: options.startWaypointId || 'johannesburg_park',
            speed_kmh: options.speedKmh || 62,
            step_minutes: options.stepMinutes || 30,
            steps: options.steps || 6,
        }),
    });
    if (!response.ok) {
        throw new Error(`Failed to start corridor feed: ${response.statusText}`);
    }
    return response.json();
}

async function fetchJourneyEta(journeyId) {
    const response = await fetch(`${API_BASE}/guardian/journeys/${journeyId}/eta`);
    if (!response.ok) {
        throw new Error(`Failed to fetch journey ETA: ${response.statusText}`);
    }
    return response.json();
}

async function issueGuardianLink(journeyId, displayName = '') {
    const response = await fetch(`${API_BASE}/guardian/journeys/${journeyId}/links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName, label: 'family' }),
    });
    if (!response.ok) {
        throw new Error(`Failed to issue guardian link: ${response.statusText}`);
    }
    return response.json();
}

async function revokeGuardianLink(token) {
    const response = await fetch(`${API_BASE}/guardian/links/${token}`, { method: 'DELETE' });
    if (!response.ok) {
        throw new Error(`Failed to revoke guardian link: ${response.statusText}`);
    }
    return true;
}

// Read-only family view. Takes the token from the URL hash, so opening a
// shared link is a matter of pasting it into WhatsApp — no install, no
// account, which is the whole point of the distribution channel.
async function fetchFamilyView(token) {
    const response = await fetch(`${API_BASE}/guardian/track/${token}`);
    if (response.status === 404) {
        return null;
    }
    if (!response.ok) {
        throw new Error(`Failed to load tracking link: ${response.statusText}`);
    }
    return response.json();
}

// ---------------------------------------------------------------------
// Ticket validation.
// ---------------------------------------------------------------------

async function issueTicket(options = {}) {
    const response = await fetch(`${API_BASE}/tickets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            origin_waypoint_id: options.originWaypointId || 'pretoria',
            destination_waypoint_id: options.destinationWaypointId || 'cape_town',
            holder_label: options.holderLabel || '',
        }),
    });
    if (!response.ok) {
        throw new Error(`Failed to issue ticket: ${response.statusText}`);
    }
    return response.json();
}

async function validateTicket(bookingReference) {
    const response = await fetch(`${API_BASE}/tickets/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_reference: bookingReference }),
    });
    if (response.status === 404) {
        return null;
    }
    if (!response.ok) {
        throw new Error(`Ticket validation failed: ${response.statusText}`);
    }
    return response.json();
}

// ---------------------------------------------------------------------
// Memory Vault — the rider memories the backend has always had but nothing
// in the browser consumed.
// ---------------------------------------------------------------------

async function fetchMemories(waypointId = null, limit = 20) {
    const query = new URLSearchParams({ limit: String(limit) });
    if (waypointId) {
        query.set('waypoint_id', waypointId);
    }
    const response = await fetch(`${API_BASE}/journey/memories?${query.toString()}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch memories: ${response.statusText}`);
    }
    return response.json();
}

async function fetchNearbyMemories(lat, lon, radius = 2000, limit = 10) {
    const query = new URLSearchParams({
        lat: String(lat),
        lon: String(lon),
        radius: String(radius),
        limit: String(limit),
    });
    const response = await fetch(`${API_BASE}/journey/memories/nearby?${query.toString()}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch nearby memories: ${response.statusText}`);
    }
    return response.json();
}

async function createMemory(payload) {
    const response = await fetch(`${API_BASE}/journey/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(`Failed to save memory: ${response.statusText}`);
    }
    return response.json();
}

async function fetchHealth() {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) {
        throw new Error(`Health check failed: ${response.statusText}`);
    }
    return response.json();
}
