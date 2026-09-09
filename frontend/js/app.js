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
        return;
    }

    els.gpsStatus.textContent = 'Requesting GPS...';
    els.btnGps.textContent = 'Stop GPS';

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
}

function getNearestWaypoint(lat, lon) {
    if (!waypoints.length) return null;
    let nearest = null;
    let minDist = Infinity;
    for (const w of waypoints) {
        const d = haversineMeters(lat, lon, w.lat, w.lon);
        if (d < minDist) {
            minDist = d;
            const idx = waypoints.indexOf(w);
            nearest = { ...w, progress: idx / (waypoints.length - 1) };
        }
    }
    return nearest;
}

function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
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
    if (!waypoints.length) return null;
    const idx = Math.round(progress * (waypoints.length - 1));
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
    const progress = idx / (waypoints.length - 1);
    setProgress(progress);
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
