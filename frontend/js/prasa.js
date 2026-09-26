// ---------------------------------------------------------------------
// PRASA API client.
//
// The Passenger Rail Agency of South Africa does not yet publish a
// developer API. This module is the shape that call would take, with a
// mock fallback so the app can exercise it now and swap in the real
// endpoint the moment one exists.
//
// When PRASA's API lands, set window.PRASA_API_BASE to its base URL and
// this file needs no change — the mock is only consulted when the fetch
// fails or returns a non-2xx status.
// ---------------------------------------------------------------------

const PRASA_BASE = window.PRASA_API_BASE || null;

// Shosholoza Meyl's known long-distance corridors. The Pretoria–Cape Town
// line is the one this app tracks; the others are listed so a future
// "which route am I on?" picker can be populated from the same constant.
const SHOSHOLOZA_ROUTES = {
    pretoria_cape_town: {
        id: 'pretoria_cape_town',
        name: 'Pretoria → Cape Town',
        stops: ['pretoria', 'johannesburg_park', 'kimberley', 'de_aar',
                'beaufort_west', 'matjiesfontein', 'worcester', 'cape_town'],
    },
    johannesburg_durban: {
        id: 'johannesburg_durban',
        name: 'Johannesburg → Durban',
        stops: ['johannesburg_park', 'pietermaritzburg', 'durban'],
    },
    cape_town_durban: {
        id: 'cape_town_durban',
        name: 'Cape Town → Durban',
        stops: ['cape_town', 'pietermaritzburg', 'durban'],
    },
};

// Fallback timetable, sourced from the content store's own station data,
// so the mock is consistent with the rest of the app.
function mockTimetable(routeId) {
    const route = SHOSHOLOZA_ROUTES[routeId] || SHOSHOLOZA_ROUTES.pretoria_cape_town;
    const now = Date.now();
    const DAY = 86400000;
    const stops = route.stops.map((stopId, index) => {
        const departure = new Date(now + index * 3 * 3600 * 1000);
        const arrival = new Date(departure.getTime() + 20 * 60 * 1000);
        return {
            station_id: stopId,
            station_name: stopId.replace(/_/g, ' '),
            sequence: index,
            arrives: arrival.toISOString(),
            departs: departure.toISOString(),
            platform: String(index + 1),
        };
    });
    return {
        route_id: route.id,
        route_name: route.name,
        service_name: 'Shosholoza Meyl',
        train_number: 'SHM-01',
        operating_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        stops,
        source: 'mock',
        note: 'PRASA has not yet published a developer API. This timetable is a demonstration fallback and will be replaced by the real service when one is available.',
    };
}

function mockLiveStatus(routeId, trainNumber) {
    const route = SHOSHOLOZA_ROUTES[routeId] || SHOSHOLOZA_ROUTES.pretoria_cape_town;
    const now = Date.now();
    const totalStops = route.stops.length;
    // A train roughly a third of the way down the line, moving.
    const currentStopIndex = Math.floor(totalStops / 3);
    const progressBetweenStops = 0.42;
    const cumulative = currentStopIndex + progressBetweenStops;
    return {
        route_id: route.id,
        route_name: route.name,
        service_name: 'Shosholoza Meyl',
        train_number: trainNumber || 'SHM-01',
        as_of: new Date(now).toISOString(),
        current_station: route.stops[currentStopIndex],
        next_station: route.stops[currentStopIndex + 1] || route.stops[route.stops.length - 1],
        progress_fraction: Math.min(1, cumulative / (totalStops - 1)),
        delay_minutes: 0,
        status: 'on_time',
        source: 'mock',
        note: 'PRASA has not yet published a developer API. This live status is a demonstration fallback and will be replaced by the real service when one is available.',
    };
}

async function fetchPrasaTimetable(routeId, date) {
    if (!PRASA_BASE) return mockTimetable(routeId);

    const query = new URLSearchParams({ route_id: routeId });
    if (date) query.set('date', date);

    try {
        const response = await fetch(`${PRASA_BASE}/timetable?${query.toString()}`);
        if (!response.ok) throw new Error(`PRASA timetable failed: ${response.status}`);
        return response.json();
    } catch (err) {
        console.warn('PRASA timetable unavailable, using mock:', err.message);
        return mockTimetable(routeId);
    }
}

async function fetchPrasaLiveStatus(routeId, trainNumber) {
    if (!PRASA_BASE) return mockLiveStatus(routeId, trainNumber);

    const query = new URLSearchParams({ route_id: routeId });
    if (trainNumber) query.set('train_number', trainNumber);

    try {
        const response = await fetch(`${PRASA_BASE}/live?${query.toString()}`);
        if (!response.ok) throw new Error(`PRASA live status failed: ${response.status}`);
        return response.json();
    } catch (err) {
        console.warn('PRASA live status unavailable, using mock:', err.message);
        return mockLiveStatus(routeId, trainNumber);
    }
}

async function fetchPrasaRoutes() {
    if (!PRASA_BASE) return Object.values(SHOSHOLOZA_ROUTES);

    try {
        const response = await fetch(`${PRASA_BASE}/routes`);
        if (!response.ok) throw new Error(`PRASA routes failed: ${response.status}`);
        return response.json();
    } catch (err) {
        console.warn('PRASA routes unavailable, using mock:', err.message);
        return Object.values(SHOSHOLOZA_ROUTES);
    }
}
