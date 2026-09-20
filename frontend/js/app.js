let currentMode = 'explorer';
let explorerInterval = null;
let companionWatchId = null;
let currentLanguage = 'en';
let lastFocusedElement = null;
let sharingPosition = false;
let sharedPositionsInterval = null;

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

// Tracks an in-flight share request and how many consecutive share failures
// we've seen, so repeated failures can be surfaced in the UI rather than
// only logged to the console.
let shareInFlight = null;
let consecutiveShareFailures = 0;

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

// Named callback for a single GPS update: resolve the story/progress for the
// current position, redraw the map, and (if sharing is on) push the position
// to the backend.
async function handleCompanionPosition(position) {
    const { latitude, longitude } = position.coords;
    els.gpsStatus.textContent = `GPS active: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;

    try {
        const result = await fetchPosition(latitude, longitude, currentLanguage);
        const alongTrack = alongTrackProgress(latitude, longitude, waypoints);
        const progress = alongTrack !== null
            ? alongTrack
            : result.route_progress_fraction;

        if (result.triggered && result.story_text) {
            showStoryCard(result);
        }
        updateTrainPosition(progress);
        updateProgressUI(progress);

        if (sharingPosition) {
            // Await the share so updates are sent in order, but don't let a
            // slow/failed share block the GPS redraw that already happened.
            sharePositionForCompanion(latitude, longitude);
        }
    } catch (err) {
        console.error('Failed to fetch position:', err);
    }
}

// Send the current position to the sharing endpoint, skipping the request if
// one is already in flight (a fast-moving rider can otherwise stack them).
// Consecutive failures are surfaced in the share status line.
function sharePositionForCompanion(lat, lon) {
    if (shareInFlight) return shareInFlight;

    shareInFlight = shareMyPosition(lat, lon)
        .then(() => {
            consecutiveShareFailures = 0;
        })
        .catch(err => {
            consecutiveShareFailures += 1;
            console.error('Failed to share position:', err);
            if (consecutiveShareFailures === 3) {
                els.shareStatus.textContent = 'Having trouble sharing your position — check your connection';
            }
            return null;
        })
        .finally(() => {
            shareInFlight = null;
        });

    return shareInFlight;
}

function stopCompanionTracking() {
    if (companionWatchId !== null) {
        navigator.geolocation.clearWatch(companionWatchId);
        companionWatchId = null;
    }
    els.btnGps.textContent = 'Start GPS Tracking';
    els.gpsStatus.textContent = 'GPS inactive';

    // Sharing only makes sense while GPS tracking is actually running —
    // stopping GPS always stops sharing too, regardless of the toggle's
    // last state, so a rider's position never keeps broadcasting after
    // they've turned tracking off.
    if (sharingPosition) {
        els.shareToggle.checked = false;
        disableSharing();
    }

    updateProgressUI(0);
}

async function onShareToggleChanged() {
    if (els.shareToggle.checked) {
        if (companionWatchId === null) {
            // Sharing without GPS running has nothing to share — guard
            // against the checkbox being toggled before "Start GPS
            // Tracking" is pressed.
            els.shareToggle.checked = false;
            els.shareStatus.textContent = 'Start GPS tracking first';
            return;
        }
        enableSharing();
    } else {
        await disableSharing();
    }
}

function enableSharing() {
    sharingPosition = true;
    els.shareStatus.textContent = 'Sharing your position with nearby riders';

    if (sharedPositionsInterval) return;
    sharedPositionsInterval = setInterval(async () => {
        try {
            const others = await fetchSharedPositions();
            renderOtherRiders(others);
        } catch (err) {
            console.error('Failed to fetch shared positions:', err);
        }
    }, 10000);
}

async function disableSharing() {
    sharingPosition = false;
    els.shareStatus.textContent = 'Not sharing';

    if (sharedPositionsInterval) {
        clearInterval(sharedPositionsInterval);
        sharedPositionsInterval = null;
    }
    clearOtherRiders();
    await stopSharingPosition();
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
        const waypoint = waypointAtProgress(progress, waypoints);
        els.progressText.textContent = waypoint
            ? `Approaching ${waypoint.name}...`
            : `Journey progress: ${percent}%`;
    }
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

    fetchPOIs(data.waypoint_id)
        .then(pois => {
            // Build the list with DOM nodes + textContent rather than an
            // innerHTML template, so a POI name can never be interpreted as
            // markup (e.g. a name containing "<script>").
            els.poiList.replaceChildren();
            pois.forEach(p => {
                const li = document.createElement('li');
                const nameSpan = document.createElement('span');
                nameSpan.textContent = p.name;
                const typeSpan = document.createElement('span');
                typeSpan.className = 'poi-type';
                typeSpan.textContent = p.type;
                li.append(nameSpan, ' ', typeSpan);
                els.poiList.appendChild(li);
            });
            els.storyPois.classList.remove('hidden');
        })
        .catch(() => {
            els.storyPois.classList.add('hidden');
        });

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
