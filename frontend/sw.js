/**
 * Offline story-pack service worker.
 *
 * The Karoo between De Aar and Matjiesfontein is roughly 200km with almost
 * no mobile coverage. A story split across four HTTP requests is a story
 * that never appears when a train pulls in with no bars, so the client
 * pre-caches a whole stop's pack — story, guide, POIs, era details and
 * nearby memories in one response — before entering a dead zone.
 *
 * Scope is deliberately narrow:
 *
 *   - Only GET. Nothing that changes state is ever served from cache, so a
 *     stale cache can show the wrong story but cannot book a wrong ticket or
 *     award a wrong stamp.
 *   - Only packs. The journey API is never cached, because an ETA served
 *     from cache would be worse than no ETA at all — a family member would
 *     read a frozen arrival time as live. When offline, the UI is told so
 *     explicitly instead.
 *   - Never caches a non-200, so an error is retried on the next attempt
 *     rather than being pinned for the rest of the trip.
 */

const CACHE_NAME = 'kasi-story-packs-v1';

const PACK_HOST_MARKERS = ['/journey/offline-pack', '/journey/pois', '/story-engine/stop/'];

self.addEventListener('install', (event) => {
    // Take over immediately: a rider mid-journey should not be held on the
    // old worker until every tab closes.
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((names) =>
                Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
            )
            .then(() => self.clients.claim())
    );
});

function isCacheablePack(request) {
    if (request.method !== 'GET') return false;
    const url = new URL(request.url);
    if (url.pathname.startsWith('/guardian/')) return false;
    if (url.pathname === '/health') return false;
    return PACK_HOST_MARKERS.some((marker) => url.pathname.startsWith(marker));
}

self.addEventListener('fetch', (event) => {
    const { request } = event;
    if (!isCacheablePack(request)) return;

    event.respondWith(
        caches.open(CACHE_NAME).then(async (cache) => {
            const cached = await cache.match(request);

            // Network first, so a pack is refreshed whenever there is signal,
            // but fall back to the cached copy when there is not.
            try {
                const response = await fetch(request);
                if (response.ok) {
                    cache.put(request, response.clone());
                }
                return response;
            } catch (err) {
                if (cached) return cached;
                return new Response(
                    JSON.stringify({
                        detail: 'This stop is not cached yet, and there is no signal to fetch it.',
                        offline: true,
                    }),
                    { status: 503, headers: { 'Content-Type': 'application/json' } }
                );
            }
        })
    );
});
