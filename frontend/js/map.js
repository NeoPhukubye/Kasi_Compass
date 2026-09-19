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

    setTimeout(() => map.resize(), 200);
    window.addEventListener('resize', () => { if (map) map.resize(); });
}

function setRoute(routeData) {
    waypoints = routeData;
    const coordinates = waypoints.map(w => [w.lon, w.lat]);

    routeGeoJSON = {
        type: "Feature",
        properties: {},
        geometry: {
            type: "LineString",
            coordinates: coordinates,
        },
    };

    if (map.getSource('route-traveled')) {
        map.getSource('route-traveled').setData({
            type: "FeatureCollection",
            features: [{
                type: "Feature",
                geometry: {
                    type: "LineString",
                    coordinates: [...coordinates],
                },
            }],
        });
    } else {
        map.addSource('route-traveled', {
            type: "geojson",
            data: {
                type: "FeatureCollection",
                features: [{
                    type: "Feature",
                    geometry: {
                        type: "LineString",
                        coordinates: [...coordinates],
                    },
                }],
            },
        });

        map.addLayer({
            id: 'route-traveled',
            type: 'line',
            source: 'route-traveled',
            paint: {
                'line-color': '#d4af37',
                'line-width': 6,
                'line-opacity': 1,
            },
        });
    }

    if (map.getSource('route-remaining')) {
        map.getSource('route-remaining').setData({
            type: "FeatureCollection",
            features: [{
                type: "Feature",
                geometry: {
                    type: "LineString",
                    coordinates: [...coordinates],
                },
            }],
        });
    } else {
        map.addSource('route-remaining', {
            type: "geojson",
            data: {
                type: "FeatureCollection",
                features: [{
                    type: "Feature",
                    geometry: {
                        type: "LineString",
                        coordinates: [...coordinates],
                    },
                }],
            },
        });

        map.addLayer({
            id: 'route-remaining',
            type: 'line',
            source: 'route-remaining',
            paint: {
                'line-color': '#d4af37',
                'line-width': 6,
                'line-opacity': 0.2,
            },
        });
    }

    waypoints.forEach((w, index) => {
        const el = document.createElement('div');
        el.style.cssText = `
            width: 32px;
            height: 32px;
            background: #1a472a;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 13px;
            border: 3px solid #d4af37;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        `;
        el.innerHTML = `${index + 1}`;

        el.addEventListener('click', () => {
            if (typeof onWaypointClick === 'function') {
                onWaypointClick(w);
            }
        });

        new maplibregl.Marker({ element: el, anchor: 'center' })
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
        el.style.cssText = `
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: #1a472a;
            border: 4px solid #d4af37;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            animation: pulse-marker 2s ease-in-out infinite;
        `;
        el.innerHTML = '🚂';
        trainMarker = new maplibregl.Marker({ element: el, anchor: 'center' })
            .setLngLat([pos.lon, pos.lat])
            .addTo(map);
    } else {
        trainMarker.setLngLat([pos.lon, pos.lat]);
    }

    if (routeGeoJSON && progressFraction > 0) {
        const coords = routeGeoJSON.geometry.coordinates;
        const totalSegments = coords.length - 1;
        const exactIndex = progressFraction * totalSegments;
        const cutIndex = Math.floor(exactIndex);

        const traveledCoords = coords.slice(0, cutIndex + 1);
        traveledCoords.push([coords[cutIndex][0] + (coords[Math.min(cutIndex + 1, totalSegments)][0] - coords[cutIndex][0]) * (exactIndex - cutIndex), coords[cutIndex][1] + (coords[Math.min(cutIndex + 1, totalSegments)][1] - coords[cutIndex][1]) * (exactIndex - cutIndex)]);

        const remainingCoords = coords.slice(cutIndex);

        if (map.getSource('route-traveled')) {
            map.getSource('route-traveled').setData({
                type: "FeatureCollection",
                features: [{
                    type: "Feature",
                    geometry: {
                        type: "LineString",
                        coordinates: traveledCoords,
                    },
                }],
            });
        }

        if (map.getSource('route-remaining')) {
            map.getSource('route-remaining').setData({
                type: "FeatureCollection",
                features: [{
                    type: "Feature",
                    geometry: {
                        type: "LineString",
                        coordinates: remainingCoords,
                    },
                }],
            });
        }

        map.easeTo({
            center: [pos.lon, pos.lat],
            zoom: Math.max(map.getZoom(), 5.5),
            duration: 300,
        });
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
