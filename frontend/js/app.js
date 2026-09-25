let currentMode = 'explorer';
let explorerInterval = null;
let companionWatchId = null;
let currentLanguage = 'en';
let lastFocusedElement = null;
let sharingPosition = false;
let sharedPositionsInterval = null;

// Waypoints whose stop-insights were already shown during the current
// explorer run, so the journey auto-pauses exactly once per stop instead
// of re-pausing every few seconds while passing it.
let stopPanelsShown = new Set();

// Tracks an in-flight share request and how many consecutive share failures
// we've seen, so repeated failures can be surfaced in the UI rather than
// only logged to the console.
let shareInFlight = null;
let consecutiveShareFailures = 0;

// Monotonic token identifying the most recent companion GPS request, so a
// slow earlier response can't overwrite a newer position/progress reading.
let latestPositionRequest = 0;

// Current stop data for the Time Machine feature
let currentStopData = null;

const els = {
    btnExplorer: document.getElementById('btn-explorer'),
    btnCompanion: document.getElementById('btn-companion'),
    btnStart: document.getElementById('btn-start-journey'),
    btnPause: document.getElementById('btn-pause-journey'),
    btnBeginJourney: document.getElementById('btn-begin-journey'),
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
    stopPanel: document.getElementById('stop-panel'),
    closeStopPanel: document.getElementById('close-stop-panel'),
    panelArchival: document.getElementById('stop-panel-archival'),
    stopImagery: document.getElementById('stop-imagery'),
    stopImgPast: document.getElementById('stop-img-past'),
    stopImgPresent: document.getElementById('stop-img-present'),
    stopImgPastCaption: document.getElementById('stop-img-past-caption'),
    stopImgPresentCaption: document.getElementById('stop-img-present-caption'),
    panelStopName: document.getElementById('panel-stop-name'),
    panelNarrative: document.getElementById('panel-narrative'),
    panelHeritageList: document.getElementById('panel-heritage-list'),
    panelStallsList: document.getElementById('panel-stalls-list'),
    btnContinueJourney: document.getElementById('btn-continue-journey'),
    eraSlider: document.getElementById('era-slider'),
    selectedYearLabel: document.getElementById('selected-year'),
    eraDescription: document.getElementById('era-description'),
    guideChat: document.getElementById('guide-chat'),
    chatMessages: document.getElementById('chat-messages'),
    guideForm: document.getElementById('guide-form'),
    guideInput: document.getElementById('guide-input'),
    guideStatus: document.getElementById('guide-status'),
};

function beginJourney() {
    document.getElementById('hero').style.display = 'none';
    document.getElementById('map-container').style.display = 'block';

    initMap();
    loadRoute();

    document.getElementById('map-container').scrollIntoView({
        behavior: 'smooth'
    });
}

function init() {
    

    els.btnExplorer.addEventListener('click', () => switchMode('explorer'));
    els.btnCompanion.addEventListener('click', () => switchMode('companion'));
    els.btnStart.addEventListener('click', startExplorerJourney);
    els.btnPause.addEventListener('click', pauseExplorerJourney);
    els.btnBeginJourney.addEventListener('click', beginJourney);
    els.speedSlider.addEventListener('input', updateSpeed);
    els.btnGps.addEventListener('click', toggleCompanionMode);
    els.shareToggle.addEventListener('change', onShareToggleChanged);
    els.closeStory.addEventListener('click', hideStoryCard);
    els.closeStopPanel.addEventListener('click', closeStopPanel);
    els.btnContinueJourney.addEventListener('click', resumeExplorerJourney);
    els.guideForm.addEventListener('submit', handleGuideSubmit);
    els.languageSelect.addEventListener('change', (e) => { currentLanguage = e.target.value; });
    els.eraSlider.addEventListener('input', handleEraChange);

    document.addEventListener('keydown', handleKeydown);

    window.onProgressUpdate = onProgressUpdate;
    window.onJourneyComplete = onJourneyComplete;
    window.onWaypointClick = onWaypointClick;

    // Journey Guardian panel + Memory Vault. Both are additive to the
    // journey experience above, so a failure here must not take the map
    // down with it.
    try {
        initGuardian();
    } catch (err) {
        console.error('Guardian panel failed to initialise:', err);
    }
}

function handleKeydown(e) {
    if (e.key === 'Escape' && !els.storyCard.classList.contains('hidden')) {
        hideStoryCard();
        if (lastFocusedElement) {
            lastFocusedElement.focus();
        }
    }
    if (e.key === 'Escape' && !els.stopPanel.classList.contains('hidden')) {
        closeStopPanel();
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
        els.guideChat.classList.add('hidden');
        stopCompanionTracking();
    } else {
        els.btnCompanion.classList.add('active');
        els.btnCompanion.setAttribute('aria-pressed', 'true');
        els.btnExplorer.classList.remove('active');
        els.btnExplorer.setAttribute('aria-pressed', 'false');
        els.companionControls.classList.remove('hidden');
        els.explorerControls.classList.add('hidden');
        els.guideChat.classList.remove('hidden');
        initGuideChat();
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

async function pollExplorerJourney() {
    if (currentProgress <= 0 || currentProgress >= 1) return;

    const pos = getPositionAlongRoute(currentProgress);
    if (!pos) return;

    try {
        const result = await fetchPosition(pos.lat, pos.lon, currentLanguage);
        if (
            result.triggered &&
            result.story_text &&
            result.waypoint_id &&
            !stopPanelsShown.has(result.waypoint_id)
        ) {
            stopPanelsShown.add(result.waypoint_id);
            await showStoryCard(result);
            await showStopInsights(result.waypoint_id, result.waypoint_name, { resumable: true });
            pauseExplorerJourney();
        }
    } catch (err) {
        console.error('Failed to fetch position:', err);
    }
}

function startExplorerJourney() {
    clearExplorerInterval();

    resetJourney();
    stopPanelsShown.clear();
    closeStopPanel();
    els.btnStart.disabled = true;
    els.btnPause.disabled = false;
    startAnimation();

    explorerInterval = setInterval(pollExplorerJourney, 2000);
}

// Picks up exactly where the auto-pause at a stop left off, without
// resetting journey progress (which Start Journey does).
function resumeExplorerJourney() {
    closeStopPanel();

    if (currentProgress <= 0 || currentProgress >= 1) {
        startExplorerJourney();
        return;
    }

    clearExplorerInterval();
    els.btnStart.disabled = true;
    els.btnPause.disabled = false;
    startAnimation();
    explorerInterval = setInterval(pollExplorerJourney, 2000);
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
            const pois = await fetchPOIs(data.waypoint_id);
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

async function showStopInsights(stopId, stopName, { resumable = false } = {}) {
    els.panelStopName.textContent = stopName || 'Stop Insights';
    els.panelNarrative.textContent = 'Loading stop insights...';
    els.panelHeritageList.innerHTML = '';
    els.panelStallsList.innerHTML = '';
    els.stopImagery.classList.add('hidden');
    els.panelArchival.classList.remove('hidden');
    els.btnContinueJourney.classList.toggle('hidden', !resumable);
    // Reset era slider to 1970 when opening a new stop
    els.eraSlider.value = '1970';
    els.selectedYearLabel.textContent = '1970';

    try {
        const data = await fetchStopDetails(stopId);
        // Store current stop data for Time Machine feature
        currentStopData = data;
        els.panelStopName.textContent = data.stop_name || stopName || 'Stop Insights';
        els.panelNarrative.textContent =
            data.historical_narrative || 'No narrative recorded for this stop yet.';

        renderFoundItems(els.panelHeritageList, data.heritage_sites, 'heritage', (site) =>
            `${site.name} (${site.era}): ${site.description}`
        );
        renderFoundItems(els.panelStallsList, data.local_stalls, 'stall', (stall) =>
            `${stall.name} [${stall.category}]: ${stall.description}`
        );

        renderStopImagery(data, stopName);
        // Set initial era description
        if (data.eras && data.eras['1970']) {
            els.eraDescription.textContent = data.eras['1970'];
        }
    } catch (err) {
        console.error('Failed to fetch stop details:', err);
        els.panelNarrative.textContent = 'Could not load stop insights. Is the backend running?';
        currentStopData = null;
    }

    els.stopPanel.classList.remove('hidden');
    els.closeStopPanel.focus();
}

function handleEraChange(e) {
    const year = e.target.value;
    els.selectedYearLabel.textContent = year;
    
    if (currentStopData && currentStopData.eras && currentStopData.eras[year]) {
        els.eraDescription.textContent = currentStopData.eras[year];
    } else {
        els.eraDescription.textContent = `Simulating station environment and surrounding infrastructure during the ${year} era.`;
    }
}

function renderStopImagery(data, stopName) {
    const hasRealImages = Boolean(data.image_past && data.image_present);
    if (hasRealImages) {
        els.stopImgPast.src = data.image_past;
        els.stopImgPresent.src = data.image_present;
    }
    const stopLabel = stopName || data.stop_name || 'This stop';
    els.stopImgPast.alt = data.image_past_alt || `${stopLabel} in the past era`;
    els.stopImgPresent.alt = data.image_present_alt || `${stopLabel} today`;
    els.stopImgPastCaption.textContent = data.image_past_caption || '';
    els.stopImgPresentCaption.textContent = data.image_present_caption || '';
    els.stopImagery.classList.remove('hidden');
    els.panelArchival.classList.add('hidden');
}

function renderFoundItems(listEl, items, emptyLabel, formatItem) {
    listEl.innerHTML = '';
    if (items && items.length > 0) {
        items.forEach((item) => {
            const li = document.createElement('li');
            li.textContent = formatItem(item);
            listEl.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.textContent = emptyLabel;
        listEl.appendChild(li);
    }
}

function closeStopPanel() {
    els.stopPanel.classList.add('hidden');
}

function hideStoryCard() {
    els.storyCard.classList.add('hidden');
}

async function onWaypointClick(waypoint) {
    try {
        const result = await fetchPosition(waypoint.lat, waypoint.lon, currentLanguage);
        if (result.triggered && result.story_text) {
            await showStoryCard(result);
        }
    } catch (err) {
        console.error('Failed to fetch position for waypoint:', err);
    }
    if (waypoint.id) {
        await showStopInsights(waypoint.id, waypoint.name, { resumable: false });
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

// ---------------------------------------------------------------------
// Route Guide chat (Companion Mode)
// ---------------------------------------------------------------------

function initGuideChat() {
    if (els.chatMessages.children.length === 0) {
        appendGuideMessage(
            'ai',
            "Sawubona! I'm your Kasi Compass route guide. Ask about Kimberley's diamond rush, " +
            "the stalls around Park Station, or any stop on the Pretoria–Cape Town line."
        );
    }
    els.guideInput.focus();
}

function appendGuideMessage(role, text) {
    const message = document.createElement('div');
    message.className = `chat-message ${role}`;
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    message.appendChild(paragraph);
    els.chatMessages.appendChild(message);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

async function handleGuideSubmit(event) {
    event.preventDefault();

    const question = els.guideInput.value.trim();
    if (!question) return;

    appendGuideMessage('user', question);
    els.guideInput.value = '';
    els.guideStatus.textContent = 'Checking the route corpus...';

    // /story-engine/ask is the endpoint that actually works with no API key:
    // it answers from the human-reviewed corpus and only reaches for Gemini
    // if the backend has a key configured. Calling /companion/chat directly
    // meant the guide 503'd for every user who had not configured one, and
    // the corpus fallback — the whole "grounded, never invents a fact"
    // promise — was unreachable from the UI.
    try {
        const result = await askGuide(question);
        appendGuideMessage('ai', result.answer);
        els.guideStatus.textContent = result.ai_used
            ? 'Answered by Gemini, grounded in the route corpus.'
            : 'Answered from the human-reviewed route corpus.';
    } catch (err) {
        console.error('Failed to reach the guide:', err);
        appendGuideMessage(
            'ai',
            'The route guide is unreachable right now. Check that the backend is running, then ask again.'
        );
        els.guideStatus.textContent = '';
    }
    els.guideInput.focus();
}

document.addEventListener('DOMContentLoaded', init);