// ---------------------------------------------------------------------
// Offline story packs.
//
// Pre-caches the next stop's whole payload before the train enters a dead
// stretch, so a story still surfaces at Matjiesfontein with no signal. The
// cache is an all-or-nothing unit per stop: a story with no guide and no
// nearby memories is worse than no story, because the rider has no way to
// tell what is missing.
// ---------------------------------------------------------------------

const offlineState = {
    cached: new Set(),
    online: navigator.onLine,
};

// Registering the worker is best-effort. A browser without service worker
// support, or a page opened over file://, simply gets no offline packs —
// which is a degraded experience, not a broken one.
async function registerOfflineWorker() {
    if (!('serviceWorker' in navigator)) {
        return null;
    }
    try {
        return await navigator.serviceWorker.register('sw.js');
    } catch (err) {
        console.warn('Offline story packs unavailable:', err);
        return null;
    }
}

/**
 * Fetch and cache one stop's complete pack.
 *
 * Always goes to the network when it can. A cache primed days earlier would
 * carry a stale narrative, and this project does not show people things it
 * cannot stand behind.
 */
async function cacheStoryPack(waypointId, language = 'en') {
    const query = new URLSearchParams({ waypoint_id: waypointId, language });
    try {
        const response = await fetch(
            `${window.KASI_API_BASE}/journey/offline-pack?${query.toString()}`
        );
        if (!response.ok) {
            throw new Error(`pack fetch failed: ${response.status}`);
        }
        const pack = await response.json();

        if ('caches' in window) {
            // Store under the same URL the service worker will match, so the
            // pack is actually reachable by a later intercept rather than
            // sitting in a cache nothing reads.
            const cache = await caches.open('kasi-story-packs-v1');
            await cache.put(
                `${window.KASI_API_BASE}/journey/offline-pack?${query.toString()}`,
                new Response(JSON.stringify(pack), { headers: { 'Content-Type': 'application/json' } })
            );
        }

        offlineState.cached.add(waypointId);
        renderOfflineStatus();
        return pack;
    } catch (err) {
        console.error(`Could not cache story pack for ${waypointId}:`, err);
        setOfflineStatus(`Could not pre-cache ${waypointId.replace(/_/g, ' ')}.`, 'warn');
        return null;
    }
}

/**
 * Cache the current stop and the next one along the corridor.
 *
 * Two stops, not the whole route: the Karoo dead zone is a few hours long,
 * and a full eight-stop pack is megabytes nobody will read. Two is the
 * honest amount of runway for a phone's cache quota and a rider's patience.
 */
async function cacheUpcomingStops(currentWaypointId, language = 'en') {
    if (!currentWaypointId) return;
    const packs = [];
    const current = await cacheStoryPack(currentWaypointId, language);
    if (current) packs.push(current);

    if (current?.next_waypoint) {
        const next = await cacheStoryPack(current.next_waypoint.waypoint_id, language);
        if (next) packs.push(next);
    }

    if (packs.length) {
        setOfflineStatus(
            `Cached ${packs.map((p) => p.waypoint_name).join(' and ')} for offline playback.`,
            'ok'
        );
    }
    return packs;
}

function setOfflineStatus(text, tone = 'info') {
    const el = document.getElementById('offline-status');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
}

function renderOfflineStatus() {
    const list = document.getElementById('offline-cached');
    if (!list) return;
    list.innerHTML = '';
    for (const waypointId of offlineState.cached) {
        const item = document.createElement('li');
        item.textContent = waypointId.replace(/_/g, ' ');
        list.appendChild(item);
    }
    setOfflineStatus(
        offlineState.online
            ? `${offlineState.cached.size} stop(s) cached.`
            : 'Offline — showing cached stories only.',
        offlineState.online ? 'info' : 'warn'
    );
}

function initOffline() {
    const button = document.getElementById('btn-cache-next');
    if (!button) return;

    registerOfflineWorker();
    renderOfflineStatus();

    button.addEventListener('click', async () => {
        const waypointId = document.getElementById('memory-waypoint')?.value
            || document.getElementById('guardian-start')?.value
            || 'johannesburg_park';
        button.disabled = true;
        await cacheUpcomingStops(waypointId, document.getElementById('language-select').value);
        button.disabled = false;
    });

    window.addEventListener('online', () => {
        offlineState.online = true;
        renderOfflineStatus();
    });
    window.addEventListener('offline', () => {
        offlineState.online = false;
        renderOfflineStatus();
    });
}
