let currentMode = 'explorer';
let explorerInterval = null;
let companionWatchId = null;

const els = {
    btnExplorer: document.getElementById('btn-explorer'),
    btnCompanion: document.getElementById('btn-companion'),
    btnStart: document.getElementById('btn-start-journey'),
    btnPause: document.getElementById('btn-pause-journey'),
    speedSlider: document.getElementById('speed-slider'),
    speedValue: document.getElementById('speed-value'),
    btnGps: document.getElementById('btn-gps'),
    gpsStatus: document.getElementById('gps-status'),
    explorerControls: document.getElementById('explorer-controls'),
    companionControls: document.getElementById('companion-controls'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    storyCard: document.getElementById('story-card'),
    storyTitle: document.getElementById('story-title'),
    storyText: document.getElementById('story-text'),
    storySource: document.getElementById('story-source'),
    closeStory: document.getElementById('close-story'),
};

function init() {
    initMap();

    els.btnExplorer.addEventListener('click', () => switchMode('explorer'));
    els.btnCompanion.addEventListener('click', () => switchMode('companion'));
    els.btnStart.addEventListener('click', startExplorerJourney);
    els.btnPause.addEventListener('click', pauseExplorerJourney);
    els.speedSlider.addEventListener('input', updateSpeed);
    els.btnGps.addEventListener('click', toggleCompanionMode);
    els.closeStory.addEventListener('click', hideStoryCard);

    window.onProgressUpdate = onProgressUpdate;
    window.onJourneyComplete = onJourneyComplete;
    window.onWaypointClick = onWaypointClick;

    loadRoute();
}

function switchMode(mode) {
    currentMode = mode;

    if (mode === 'explorer') {
        els.btnExplorer.classList.add('active');
        els.btnCompanion.classList.remove('active');
        els.explorerControls.classList.remove('hidden');
        els.companionControls.classList.add('hidden');
        stopCompanionMode();
    } else {
        els.btnCompanion.classList.add('active');
        els.btnExplorer.classList.remove('active');
        els.companionControls.classList.remove('hidden');
        els.explorerControls.classList.add('hidden');
        pauseExplorerJourney();
    }
}

async function loadRoute() {
    try {
        const route = await fetchRoute();
        setRoute(route);
    } catch (err) {
        console.error('Failed to load route:', err);
        els.progressText.textContent = 'Error loading route. Is the backend running?';
    }
}

function startExplorerJourney() {
    if (explorerInterval) {
        clearInterval(explorerInterval);
        explorerInterval = null;
    }

    resetJourney();
    els.btnStart.disabled = true;
    els.btnPause.disabled = false;
    startAnimation();

    explorerInterval = setInterval(async () => {
        if (currentProgress <= 0 || currentProgress >= 1) return;

        const pos = getPositionAlongRoute(currentProgress);
        if (!pos) return;

        try {
            const result = await fetchPosition(pos.lat, pos.lon);
            if (result.triggered && result.story_text) {
                showStoryCard(result);
            }
        } catch (err) {
            console.error('Failed to fetch position:', err);
        }
    }, 2000);
}

function pauseExplorerJourney() {
    if (explorerInterval) {
        clearInterval(explorerInterval);
        explorerInterval = null;
    }

    if (isAnimating) {
        stopAnimation();
        els.btnStart.disabled = false;
        els.btnStart.textContent = 'Resume Journey';
        els.btnPause.disabled = true;
    }
}

function updateSpeed() {
    const speed = parseInt(els.speedSlider.value, 10);
    setSpeed(speed);
    els.speedValue.textContent = `${speed}x`;
}

async function toggleCompanionMode() {
    if (companionWatchId !== null) {
        stopCompanionMode();
        return;
    }

    if (!navigator.geolocation) {
        els.gpsStatus.textContent = 'Geolocation not supported';
        els.btnGps.textContent = 'Start GPS Tracking';
        return;
    }

    els.gpsStatus.textContent = 'Requesting GPS...';

    try {
        companionWatchId = navigator.geolocation.watchPosition(
            async (position) => {
                const { latitude, longitude } = position.coords;
                els.gpsStatus.textContent = `GPS active: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;

                try {
                    const result = await fetchPosition(latitude, longitude);
                    if (result.triggered && result.story_text) {
                        updateTrainPosition(result.route_progress_fraction);
                        showStoryCard(result);
                    } else {
                        const nearest = getNearestWaypoint(latitude, longitude);
                        if (nearest) {
                            updateTrainPosition(nearest.progress);
                        }
                    }
                    updateProgressUI(result.route_progress_fraction);
                } catch (err) {
                    console.error('Failed to fetch position:', err);
                }
            },
            (err) => {
                els.gpsStatus.textContent = `GPS error: ${err.message}`;
                stopCompanionMode();
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0,
            }
        );
        els.btnGps.textContent = 'Stop GPS';
    } catch (err) {
        els.gpsStatus.textContent = `GPS error: ${err.message}`;
        stopCompanionMode();
    }
}

function stopCompanionMode() {
    if (companionWatchId !== null) {
        navigator.geolocation.clearWatch(companionWatchId);
        companionWatchId = null;
    }
    els.btnGps.textContent = 'Start GPS Tracking';
    els.gpsStatus.textContent = 'GPS inactive';

    // Leaving Companion Mode should not strand the progress bar on whatever
    // fraction the last GPS fix happened to report — reset it to the idle
    // "Ready to begin" state so both modes start from a clean slate.
    updateProgressUI(0);
}

// Uses the single shared haversine implementation in js/geo.js (loaded before
// this file in index.html). This is only a client-side approximation for
// animating the train icon and showing "approaching X" hints — the backend
// (app/story_engine/geofence.py) remains the single source of truth for which
// waypoint actually triggers a story.
function getNearestWaypoint(lat, lon) {
    if (!waypoints.length) return null;
    if (typeof haversineMeters !== 'function') {
        console.error('geo.js (haversineMeters) not loaded — check script order in index.html');
        return null;
    }
    if (waypoints.length < 2) {
        return { ...waypoints[0], progress: 0 };
    }

    let nearest = null;
    let minDist = Infinity;
    let nearestIndex = 0;

    // Use the array index directly rather than waypoints.indexOf(w) inside the
    // loop, which was O(n^2) and relied on object identity.
    waypoints.forEach((w, index) => {
        const d = haversineMeters(lat, lon, w.lat, w.lon);
        if (d < minDist) {
            minDist = d;
            nearest = w;
            nearestIndex = index;
        }
    });

    if (!nearest) return null;
    return { ...nearest, progress: nearestIndex / (waypoints.length - 1) };
}

function onProgressUpdate(progress) {
    updateProgressUI(progress);
}

function updateProgressUI(progress) {
    const percent = Math.round(progress * 100);
    els.progressFill.style.width = `${percent}%`;

    if (progress <= 0) {
        els.progressText.textContent = 'Ready to begin';
    } else if (progress >= 1) {
        els.progressText.textContent = 'Journey complete!';
    } else {
        const waypoint = getCurrentWaypoint(progress);
        els.progressText.textContent = waypoint
            ? `Approaching ${waypoint.name}...`
            : `Journey progress: ${percent}%`;
    }
}

function getCurrentWaypoint(progress) {
    // Guard before dividing by (waypoints.length - 1): with a single waypoint
    // that divisor is 0, which yields NaN/Infinity and an out-of-range index.
    if (waypoints.length < 2) return null;
    const safeProgress = Math.max(0, Math.min(1, progress || 0));
    const idx = Math.round(safeProgress * (waypoints.length - 1));
    return waypoints[Math.min(idx, waypoints.length - 1)];
}

function onJourneyComplete() {
    els.btnStart.disabled = false;
    els.btnStart.textContent = 'Start Journey';
    els.btnPause.disabled = true;
    if (explorerInterval) {
        clearInterval(explorerInterval);
        explorerInterval = null;
    }
}

function onWaypointClick(waypoint) {
    const idx = waypoints.indexOf(waypoint);
    if (idx === -1) return;

    // Same single-waypoint guard as getCurrentWaypoint: never divide by
    // (waypoints.length - 1) when there is only one waypoint.
    if (waypoints.length < 2) {
        setProgress(0);
        return;
    }

    setProgress(idx / (waypoints.length - 1));
}

function showStoryCard(data) {
    els.storyTitle.textContent = data.waypoint_name || 'Stop';
    els.storyText.textContent = data.story_text || '';
    els.storySource.textContent = data.story_source ? `Source: ${data.story_source}` : '';
    els.storyCard.classList.remove('hidden');
}

function hideStoryCard() {
    els.storyCard.classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', init);
