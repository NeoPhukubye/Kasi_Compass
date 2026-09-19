// Live position sharing between riders — opt-in only. See
// backend/app/story_engine/live_share.py for the server-side privacy
// guarantees (fuzzing, TTL, anonymity) this module relies on.
//
// riderId is a random UUID generated once per tab session (sessionStorage,
// not localStorage) — it resets on browser restart or new tab, is never
// tied to any name or identity field, and only exists to let the backend
// exclude "my own position" from the list of other riders.

function getOrCreateRiderId() {
    let riderId = sessionStorage.getItem('kasiCompassRiderId');
    if (!riderId) {
        riderId = crypto.randomUUID();
        sessionStorage.setItem('kasiCompassRiderId', riderId);
    }
    return riderId;
}

const riderId = getOrCreateRiderId();

async function shareMyPosition(lat, lon) {
    const response = await fetch(`${API_BASE}/journey/share-position`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rider_id: riderId, lat, lon }),
    });
    if (!response.ok) {
        throw new Error(`Failed to share position: ${response.statusText}`);
    }
    return response.json();
}

async function fetchSharedPositions() {
    const params = new URLSearchParams({ rider_id: riderId });
    const response = await fetch(`${API_BASE}/journey/shared-positions?${params.toString()}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch shared positions: ${response.statusText}`);
    }
    return response.json();
}

// Best-effort immediate removal when sharing is turned off deliberately
// (not on tab close — see leavePositionOnUnload for that case).
async function stopSharingPosition() {
    try {
        await fetch(`${API_BASE}/journey/share-position/leave`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rider_id: riderId, lat: 0, lon: 0 }),
        });
    } catch (err) {
        // Non-fatal: the 45s TTL on the backend covers this if the
        // request fails (e.g. connection already dropping).
        console.warn('Failed to explicitly leave position sharing:', err);
    }
}

// Tab close / navigation away: fetch() may not complete, so use
// sendBeacon, which the browser guarantees gets sent even as the page
// unloads. sendBeacon only supports POST, which is why the leave endpoint
// is a POST rather than a DELETE.
function leavePositionOnUnload() {
    if (!navigator.sendBeacon) return;
    const payload = JSON.stringify({ rider_id: riderId, lat: 0, lon: 0 });
    const blob = new Blob([payload], { type: 'application/json' });
    navigator.sendBeacon(`${API_BASE}/journey/share-position/leave`, blob);
}

window.addEventListener('pagehide', leavePositionOnUnload);
