const API_BASE = 'http://localhost:8000';

async function fetchRoute() {
    const response = await fetch(`${API_BASE}/journey/route`);
    if (!response.ok) {
        throw new Error(`Failed to fetch route: ${response.statusText}`);
    }
    return response.json();
}

async function fetchPosition(lat, lon, language = 'en') {
    const response = await fetch(
        `${API_BASE}/journey/position?lat=${lat}&lon=${lon}&language=${language}`
    );
    if (!response.ok) {
        throw new Error(`Failed to fetch position: ${response.statusText}`);
    }
    return response.json();
}
