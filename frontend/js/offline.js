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

// Must match the service worker's cache name. The client writes into this
// cache directly (a service worker cannot see a fetch it did not itself
// intercept), so the two have to agree or the packs land somewhere the
// offline path will never look.
const CACHE_NAME = 'kasi-story-packs-v1';

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
            const cache = await caches.open(CACHE_NAME);
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

    if (offlineState.cached.size === 0) {
        setOfflineStatus(
            offlineState.online
                ? 'Nothing cached yet. Pick a stop above, then use the button to store it and the next one.'
                : 'Offline with nothing cached — stories will not load until you reconnect.',
            offlineState.online ? 'info' : 'warn'
        );
        return;
    }

    setOfflineStatus(
        offlineState.online
            ? `Ready for dead zones: ${offlineState.cached.size} stop(s) cached.`
            : `Offline. ${offlineState.cached.size} cached stop(s) available.`,
        offlineState.online ? 'ok' : 'warn'
    );
}

/**
 * Read the stops that are actually stored, rather than trusting this page
 * load's memory of what it cached.
 *
 * Cache Storage outlives the page but `offlineState.cached` does not, so
 * without this the panel reported "0 stop(s) cached" after every reload even
 * with packs sitting in the cache — telling the rider their offline
 * coverage was empty when it was not. Worse than a cosmetic bug: they would
 * reasonably conclude the feature does not work.
 */
async function discoverCachedStops() {
    offlineState.cached.clear();
    if (!('caches' in window)) return offlineState.cached;

    try {
        const cache = await caches.open(CACHE_NAME);
        for (const request of await cache.keys()) {
            const url = new URL(request.url);
            if (!url.pathname.endsWith('/journey/offline-pack')) continue;
            // The pack's waypoint is in the request's own query string,
            // which is also the key the service worker matches on.
            const waypointId = url.searchParams.get('waypoint_id');
            if (waypointId) {
                offlineState.cached.add(waypointId);
            }
        }
    } catch (err) {
        console.warn('Could not enumerate cached story packs:', err);
    }
    return offlineState.cached;
}

function initOffline() {
    const button = document.getElementById('btn-cache-next');
    if (!button) return;

    registerOfflineWorker();
    setOfflineStatus('Checking what is cached…');
    discoverCachedStops().then(renderOfflineStatus);

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
