let currentMode = 'explorer';
let explorerInterval = null;
let companionWatchId = null;
let currentLanguage = 'en';
let lastFocusedElement = null;
let sharingPosition = false;
let sharedPositionsInterval = null;

// Tracks an in-flight share request and how many consecutive share failures
// we've seen, so repeated failures can be surfaced in the UI rather than
// only logged to the console.
let shareInFlight = null;
let consecutiveShareFailures = 0;

// Monotonic token identifying the most recent companion GPS request, so a
// slow earlier response can't overwrite a newer position/progress reading.
let latestPositionRequest = 0;

const els = {
    btnExplorer: document.getElementById('btn-explorer'),
    btnCompanion: document.getElementById('btn-companion'),
    btnStart: document.getElementById('btn-start-journey'),
    btnPause: document.getElementById('btn-pause-journey'),
    speedSlider: document.getElementById('speed-slider'),
    speedValue: document.getElementById('speed-value'),
    btnGps: document.getElementById('btn-gps'),
    gpsStatus: document.getElementById('gps-status'),
    shareToggle: document.getElementById('share-position-toggle'),
    shareStatus: document.getElementById('share-status'),
    explorerControls: document.getElementById('explorer-controls'),
    companionControls: document.getElementById('companion-controls'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    progressBar: document.querySelector('.progress-bar'),
    storyCard: document.getElementById('story-card'),
    storyTitle: document.getElementById('story-title'),
    storyText: document.getElementById('story-text'),
    storySource: document.getElementById('story-source'),
    storyPois: document.getElementById('story-pois'),
    poiList: document.getElementById('poi-list'),
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
    els.shareToggle.addEventListener('change', onShareToggleChanged);
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
        stopCompanionTracking();
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

function clearExplorerInterval() {
    if (explorerInterval) {
        clearInterval(explorerInterval);
        explorerInterval = null;
    }
}

function startExplorerJourney() {
    clearExplorerInterval();

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
    clearExplorerInterval();

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
        stopCompanionTracking();
        return;
    }
    startCompanionTracking();
}

function startCompanionTracking() {
    if (!navigator.geolocation) {
        els.gpsStatus.textContent = 'Geolocation not supported';
        els.btnGps.textContent = 'Start GPS Tracking';
        return;
    }

    els.gpsStatus.textContent = 'Requesting GPS...';

    try {
        companionWatchId = navigator.geolocation.watchPosition(
            handleCompanionPosition,
            (err) => {
                els.gpsStatus.textContent = `GPS error: ${err.message}`;
                stopCompanionTracking();
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
        stopCompanionTracking();
    }
}

function stopCompanionTracking() {
    if (companionWatchId !== null) {
        navigator.geolocation.clearWatch(companionWatchId);
        companionWatchId = null;
    }
    els.gpsStatus.textContent = 'GPS inactive';
    els.btnGps.textContent = 'Start GPS Tracking';

    if (sharingPosition) {
        els.shareToggle.checked = false;
        onShareToggleChanged();
    }
}

async function handleCompanionPosition(position) {
    const { latitude, longitude, accuracy } = position.coords;
    const thisRequest = ++latestPositionRequest;

    els.gpsStatus.textContent = `GPS active (accuracy: ${accuracy.toFixed(0)}m)`;

    try {
        const result = await fetchPosition(latitude, longitude, currentLanguage);

        if (thisRequest === latestPositionRequest) {
            updateTrainPosition(result.route_progress_fraction);
            onProgressUpdate(result.route_progress_fraction);

            if (result.triggered && result.story_text) {
                showStoryCard(result);
            }
        }
    } catch (err) {
        console.error('Failed to fetch position:', err);
        els.gpsStatus.textContent = 'Error fetching position';
    }

    if (sharingPosition) {
        shareLivePosition(latitude, longitude);
    }
}

function onProgressUpdate(progress) {
    currentProgress = progress;
    const percentage = (progress * 100).toFixed(1);
    els.progressFill.style.width = `${percentage}%`;
    els.progressText.textContent = `Journey progress: ${percentage}%`;
    els.progressBar.setAttribute('aria-valuenow', percentage);
}

function onJourneyComplete() {
    clearExplorerInterval();
    stopAnimation();
    els.btnStart.disabled = false;
    els.btnStart.textContent = 'Start Journey';
    els.btnPause.disabled = true;
    els.progressText.textContent = 'Journey complete!';
}

async function showStoryCard(data) {
    lastFocusedElement = document.activeElement;

    els.storyTitle.textContent = data.waypoint_name;
    els.storyText.textContent = data.story_text;
    els.storySource.textContent = `Source: ${data.story_source}`;
    els.storyCard.classList.remove('hidden');
    els.closeStory.focus();

    if (data.waypoint_id) {
        try {
            const pois = await fetchPois(data.waypoint_id);
            if (pois.length > 0) {
                els.storyPois.classList.remove('hidden');
                els.poiList.innerHTML = pois
                    .map(
                        (p) => `
                    <li>
                        <strong>${p.name}</strong> (${p.type})
                        ${p.description ? `<br><span class="poi-description">${p.description}</span>` : ''}
                    </li>
                `
                    )
                    .join('');
            } else {
                els.storyPois.classList.add('hidden');
            }
        } catch (err) {
            console.error('Failed to fetch POIs:', err);
            els.storyPois.classList.add('hidden');
        }
    } else {
        els.storyPois.classList.add('hidden');
    }
}

function hideStoryCard() {
    els.storyCard.classList.add('hidden');
}

async function onWaypointClick(waypoint) {
    try {
        const result = await fetchPosition(waypoint.lat, waypoint.lon, currentLanguage);
        if (result.triggered && result.story_text) {
            showStoryCard(result);
        }
    } catch (err) {
        console.error('Failed to fetch position for waypoint:', err);
    }
}

function onShareToggleChanged() {
    sharingPosition = els.shareToggle.checked;
    if (sharingPosition) {
        startPositionSharing();
    } else {
        stopPositionSharing();
    }
}

function startPositionSharing() {
    els.shareStatus.textContent = 'Sharing...';
    if (sharedPositionsInterval) clearInterval(sharedPositionsInterval);
    sharedPositionsInterval = setInterval(fetchSharedPositions, 5000);
    fetchSharedPositions();
}

function stopPositionSharing() {
    els.shareStatus.textContent = 'Not sharing';
    if (shareInFlight) {
        shareInFlight.abort();
        shareInFlight = null;
    }
    if (sharedPositionsInterval) {
        clearInterval(sharedPositionsInterval);
        sharedPositionsInterval = null;
    }
    clearSharedPositionMarkers();
    leaveLiveShare();
}

document.addEventListener('DOMContentLoaded', init);