let currentMode = 'explorer';
let explorerInterval = null;
let companionWatchId = null;
let currentLanguage = 'en';
let lastFocusedElement = null;

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
    progressBar: document.querySelector('.progress-bar'),
    storyCard: document.getElementById('story-card'),
    storyTitle: document.getElementById('story-title'),
    storyText: document.getElementById('story-text'),
    storySource: document.getElementById('story-source'),
    closeStory: document.getElementById('close-story'),
    languageSelect: document.getElementById('language-select'),
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
    els.languageSelect.addEventListener('change', (e) => { currentLanguage = e.target.value; });

    document.addEventListener('keydown', handleKeydown);

    window.onProgressUpdate = onProgressUpdate;
    window.onJourneyComplete = onJourneyComplete;
    window.onWaypointClick = onWaypointClick;

    loadRoute();
}

function handleKeydown(e) {
    if (e.key === 'Escape' && !els.storyCard.classList.contains('hidden')) {
        hideStoryCard();
        if (lastFocusedElement) {
            lastFocusedElement.focus();
        }
    }
    if (els.speedSlider.matches(':focus') && (e.key === 'ArrowLeft' || e.key === 'ArrowDown')) {
        e.preventDefault();
        els.speedSlider.value = Math.max(1, parseInt(els.speedSlider.value, 10) - 1);
        updateSpeed();
    }
    if (els.speedSlider.matches(':focus') && (e.key === 'ArrowRight' || e.key === 'ArrowUp')) {
        e.preventDefault();
        els.speedSlider.value = Math.min(10, parseInt(els.speedSlider.value, 10) + 1);
        updateSpeed();
    }
}

function switchMode(mode) {
    currentMode = mode;

    if (mode === 'explorer') {
        els.btnExplorer.classList.add('active');
        els.btnExplorer.setAttribute('aria-pressed', 'true');
        els.btnCompanion.classList.remove('active');
        els.btnCompanion.setAttribute('aria-pressed', 'false');
        els.explorerControls.classList.remove('hidden');
        els.companionControls.classList.add('hidden');
        stopCompanionMode();
    } else {
        els.btnCompanion.classList.add('active');
        els.btnCompanion.setAttribute('aria-pressed', 'true');
        els.btnExplorer.classList.remove('active');
        els.btnExplorer.setAttribute('aria-pressed', 'false');
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
            const result = await fetchPosition(pos.lat, pos.lon, currentLanguage);
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
    els.speedSlider.setAttribute('aria-valuenow', String(speed));
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
                    const result = await fetchPosition(latitude, longitude, currentLanguage);
                    const alongTrack = alongTrackProgress(
                        latitude, longitude, waypoints
                    );
                    const progress = alongTrack !== null
                        ? alongTrack
                        : result.route_progress_fraction;

                    if (result.triggered && result.story_text) {
                        showStoryCard(result);
                    }
                    updateTrainPosition(progress);
                    updateProgressUI(progress);
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

    updateProgressUI(0);
}

function onProgressUpdate(progress) {
    updateProgressUI(progress);
}

function updateProgressUI(progress) {
    const percent = Math.round(progress * 100);
    els.progressFill.style.width = `${percent}%`;

    if (els.progressBar) {
        els.progressBar.setAttribute('aria-valuenow', String(percent));
    }

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

    if (waypoints.length < 2) {
        setProgress(0);
        return;
    }

    setProgress(idx / (waypoints.length - 1));
}

function showStoryCard(data) {
    lastFocusedElement = document.activeElement;
    els.storyTitle.textContent = data.waypoint_name || 'Stop';
    els.storyText.textContent = data.story_text || '';
    els.storySource.textContent = data.story_source ? `Source: ${data.story_source}` : '';
    els.storyCard.classList.remove('hidden');
    els.storyCard.setAttribute('aria-hidden', 'false');
    setTimeout(() => {
        els.closeStory.focus();
    }, 100);
}

function hideStoryCard() {
    els.storyCard.classList.add('hidden');
    els.storyCard.setAttribute('aria-hidden', 'true');
    if (lastFocusedElement) {
        lastFocusedElement.focus();
    }
}

document.addEventListener('DOMContentLoaded', init);
