let map = null;
let waypoints = [];
let routeGeoJSON = null;
let trainMarker = null;
let animationFrame = null;
let currentProgress = 0;
let isAnimating = false;
let animationSpeed = 3;
let triggeredWaypoints = new Set();

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION = '© OpenStreetMap contributors';

function initMap() {
    map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {
                'osm-tiles': {
                    type: 'raster',
                    tiles: [TILE_URL],
                    tileSize: 256,
                    attribution: TILE_ATTRIBUTION,
                },
            },
            layers: [
                {
                    id: 'osm-tiles',
                    type: 'raster',
                    source: 'osm-tiles',
                },
            ],
        },
        center: [25.0, -29.0],
        zoom: 5,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
}

function setRoute(routeData) {
    waypoints = routeData;
    const coordinates = waypoints.map(w => [w.lon, w.lat]);

    routeGeoJSON = {
        type: 'Feature',
        properties: {},
        geometry: {
            type: 'LineString',
            coordinates: coordinates,
        },
    };

    if (map.getSource('route')) {
        map.getSource('route').setData(routeGeoJSON);
    } else {
        map.addSource('route', {
            type: 'geojson',
            data: routeGeoJSON,
        });

        map.addLayer({
            id: 'route-line',
            type: 'line',
            source: 'route',
            paint: {
                'line-color': '#d4af37',
                'line-width': 4,
                'line-opacity': 0.8,
            },
        });
    }

    waypoints.forEach((w, index) => {
        const el = document.createElement('div');
        el.className = 'waypoint-marker';
        el.innerHTML = `<span>${index + 1}</span>`;
        el.style.cssText = `
            width: 28px;
            height: 28px;
            background: #1a472a;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
            border: 3px solid #d4af37;
            cursor: pointer;
        `;

        el.addEventListener('click', () => {
            if (typeof onWaypointClick === 'function') {
                onWaypointClick(w);
            }
        });

        new maplibregl.Marker({ element: el })
            .setLngLat([w.lon, w.lat])
            .addTo(map);
    });

    const bounds = new maplibregl.LngLatBounds();
    coordinates.forEach(coord => bounds.extend(coord));
    map.fitBounds(bounds, { padding: 50 });
}

function getPositionAlongRoute(progressFraction) {
    if (!routeGeoJSON || !waypoints.length) return null;

    const coords = routeGeoJSON.geometry.coordinates;
    const totalSegments = coords.length - 1;
    const exactIndex = progressFraction * totalSegments;
    const lowerIndex = Math.floor(exactIndex);
    const upperIndex = Math.min(lowerIndex + 1, totalSegments);
    const t = exactIndex - lowerIndex;

    const lon = coords[lowerIndex][0] + t * (coords[upperIndex][0] - coords[lowerIndex][0]);
    const lat = coords[lowerIndex][1] + t * (coords[upperIndex][1] - coords[lowerIndex][1]);

    return { lon, lat };
}

function updateTrainPosition(progressFraction) {
    const pos = getPositionAlongRoute(progressFraction);
    if (!pos) return;

    if (!trainMarker) {
        const el = document.createElement('div');
        el.innerHTML = '🚂';
        el.style.cssText = `
            font-size: 28px;
            transform: translate(-50%, -50%);
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
        `;
        trainMarker = new maplibregl.Marker({ element: el, anchor: 'center' })
            .setLngLat([pos.lon, pos.lat])
            .addTo(map);
    } else {
        trainMarker.setLngLat([pos.lon, pos.lat]);
    }
}

function startAnimation() {
    if (isAnimating) return;
    isAnimating = true;
    animate();
}

function stopAnimation() {
    isAnimating = false;
    if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = null;
    }
}

function animate() {
    if (!isAnimating) return;

    currentProgress += 0.0005 * animationSpeed;
    if (currentProgress >= 1) {
        currentProgress = 1;
        stopAnimation();
        if (typeof onJourneyComplete === 'function') {
            onJourneyComplete();
        }
    }

    updateTrainPosition(currentProgress);
    if (typeof onProgressUpdate === 'function') {
        onProgressUpdate(currentProgress);
    }

    if (isAnimating) {
        animationFrame = requestAnimationFrame(animate);
    }
}

function setSpeed(speed) {
    animationSpeed = speed;
}

function setProgress(progress) {
    currentProgress = Math.max(0, Math.min(1, progress));
    updateTrainPosition(currentProgress);
    if (typeof onProgressUpdate === 'function') {
        onProgressUpdate(currentProgress);
    }
}

function resetJourney() {
    stopAnimation();
    currentProgress = 0;
    triggeredWaypoints.clear();
    if (trainMarker) {
        trainMarker.remove();
        trainMarker = null;
    }
    if (typeof onProgressUpdate === 'function') {
        onProgressUpdate(0);
    }
}
