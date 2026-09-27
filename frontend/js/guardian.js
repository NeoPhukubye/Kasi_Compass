// ---------------------------------------------------------------------
// Journey Guardian (frontend) — corridor feed, ETA, and family links.
//
// This panel is the demonstration of the claim that is hardest to defend
// in a pitch: a journey keeps reporting itself from the corridor, not from
// the passenger's phone. Starting a feed here creates server-side telemetry
// that the browser does not feed and does not need to keep open — a family
// member's link resolves the same data afterwards.
// ---------------------------------------------------------------------

const guardianState = {
    journeyId: null,
    shareUrl: null,
    token: null,
    pollTimer: null,
};

// How often the panel re-reads the ETA. Deliberately not a tight loop: this
// is a family reassurance surface, not a live-tracking product, and 10s is
// well inside what a person waiting for news would actually notice.
const GUARDIAN_POLL_MS = 10000;

// The demo corridor feed runs the full Pretoria-Cape Town length so the
// passport fills with every station. Sample count, not distance, is what
// decides whether a stamp lands: too few samples and the feed steps straight
// over a station without ever coming within stamping distance of it.
const DEMO_FEED_STEPS = 50;
const DEMO_FEED_STEP_MINUTES = 30;

function formatEtaTime(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString(undefined, {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function setGuardianStatus(text, tone = 'info') {
    const el = document.getElementById('guardian-status');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
}

function renderMilestones(milestones) {
    const list = document.getElementById('guardian-milestones');
    if (!list) return;
    list.innerHTML = '';
    for (const milestone of milestones || []) {
        const item = document.createElement('li');
        item.className = milestone.reached ? 'milestone reached' : 'milestone';
        item.dataset.kind = milestone.kind;

        const marker = document.createElement('span');
        marker.className = 'milestone-marker';
        marker.setAttribute('aria-hidden', 'true');

        const label = document.createElement('span');
        label.className = 'milestone-label';
        label.textContent = milestone.label;

        const distance = document.createElement('span');
        distance.className = 'milestone-distance';
        distance.textContent = `${Math.round(milestone.at_km)} km`;

        item.append(marker, label, distance);
        list.appendChild(item);
    }
}

function renderGuardianEta(eta) {
    document.getElementById('guardian-headline').textContent = eta.delay_display;

    const rows = [
        ['Status', eta.status.replace(/_/g, ' ')],
        ['Last seen near', eta.position ? eta.position.nearest_waypoint_name : '—'],
        ['Province', eta.province || '—'],
        ['Next province', eta.next_province || 'Arriving'],
        ['Distance covered', eta.position ? `${eta.position.distance_along_km} km of ${eta.position.total_km} km` : '—'],
        ['Observed speed', `${eta.observed_speed_kmh} km/h (${eta.speed_source.replace(/_/g, ' ')})`],
        ['Next stop ETA', formatEtaTime(eta.eta.next_station_at)],
        ['Cape Town ETA', formatEtaTime(eta.eta.arrival_at)],
        ['Report source', eta.last_report_source || '—'],
    ];

    const body = document.getElementById('guardian-facts');
    body.innerHTML = '';
    for (const [label, value] of rows) {
        const term = document.createElement('dt');
        term.textContent = label;
        const definition = document.createElement('dd');
        definition.textContent = value;
        body.append(term, definition);
    }

    renderMilestones(eta.milestones);
}

async function pollGuardianEta() {
    if (!guardianState.journeyId) return;
    try {
        const eta = await fetchJourneyEta(guardianState.journeyId);
        renderGuardianEta(eta);
        setGuardianStatus(
            eta.last_report_seconds_ago === null
                ? 'Waiting for the first corridor report.'
                : `Last corridor report ${Math.round(eta.last_report_seconds_ago)}s ago — served by ${eta.position.driver}.`,
            eta.status === 'signal_lost' ? 'warn' : 'info',
        );
        // The passport grows as the journey does, so it is re-read on the
        // same cadence rather than needing its own timer.
        await renderPassport(guardianState.journeyId);
    } catch (err) {
        console.error('Guardian poll failed:', err);
        setGuardianStatus('Lost contact with the backend.', 'warn');
    }
}

// ---------------------------------------------------------------------
// Journey passport
// ---------------------------------------------------------------------

async function renderPassport(journeyId) {
    try {
        const passport = await fetchPassport(journeyId);
        document.getElementById('passport-progress').textContent = passport.complete
            ? 'Corridor complete — every station stamped.'
            : `${passport.stamps_earned} of ${passport.stamps_total} stations stamped.`;

        const list = document.getElementById('passport-stamps');
        list.innerHTML = '';
        for (const stamp of passport.stamps) {
            const item = document.createElement('li');
            item.className = 'stamp';

            const name = document.createElement('span');
            name.className = 'stamp-name';
            name.textContent = stamp.name;

            const province = document.createElement('span');
            province.className = 'stamp-province';
            province.textContent = stamp.province;

            const when = document.createElement('span');
            when.className = 'stamp-time';
            when.textContent = new Date(stamp.stamped_at * 1000).toLocaleString(undefined, {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
            });

            const source = document.createElement('span');
            source.className = 'stamp-source';
            source.textContent = `via ${stamp.source.replace(/_/g, ' ')}`;

            item.append(name, province, when, source);
            list.appendChild(item);
        }

        document.getElementById('passport-note').textContent = passport.coverage_note;
    } catch (err) {
        console.error('Failed to render passport:', err);
    }
}

async function startGuardianFeed() {
    const button = document.getElementById('btn-start-feed');
    button.disabled = true;
    setGuardianStatus('Starting the corridor feed...');

    try {
        const startWaypoint = document.getElementById('guardian-start')?.value || 'johannesburg_park';
        const result = await simulateRun({
            startWaypointId: startWaypoint,
            steps: DEMO_FEED_STEPS,
            stepMinutes: DEMO_FEED_STEP_MINUTES,
            speedKmh: 62,
        });
        guardianState.journeyId = result.journey_id;
        document.getElementById('guardian-panel').classList.remove('hidden');
        renderGuardianEta(result.eta);
        await renderPassport(result.journey_id);

        // Mint the family link immediately so the demo always has one to show
        // — the link is the deliverable a family member would actually get.
        const link = await issueGuardianLink(result.journey_id, 'Family tracking link');
        guardianState.token = link.token;
        guardianState.shareUrl = link.share_url;
        document.getElementById('guardian-share-url').textContent = link.share_url;
        setGuardianStatus('Corridor feed running. This link works without the rider\'s phone.', 'ok');

        clearInterval(guardianState.pollTimer);
        guardianState.pollTimer = setInterval(pollGuardianEta, GUARDIAN_POLL_MS);
    } catch (err) {
        console.error('Failed to start corridor feed:', err);
        setGuardianStatus('Could not start the corridor feed. Is the backend running?', 'warn');
    } finally {
        button.disabled = false;
    }
}

async function copyGuardianLink() {
    if (!guardianState.shareUrl) return;
    try {
        await navigator.clipboard.writeText(guardianState.shareUrl);
        setGuardianStatus('Link copied — paste it into a WhatsApp message.', 'ok');
    } catch {
        // Clipboard access needs a secure context, which a plain http://
        // localhost demo may or may not have. Selecting the text is a
        // perfectly good fallback.
        const field = document.getElementById('guardian-share-url');
        const range = document.createRange();
        range.selectNodeContents(field);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        setGuardianStatus('Link selected — press Ctrl+C to copy.', 'info');
    }
}

function shareGuardianLinkWhatsApp() {
    if (!guardianState.shareUrl) return;
    const text = encodeURIComponent(`Track my journey on Kasi Compass: ${guardianState.shareUrl}`);
    const waUrl = `https://wa.me/?text=${text}`;
    window.open(waUrl, '_blank');
}

async function stopGuardianFeed() {
    clearInterval(guardianState.pollTimer);
    guardianState.pollTimer = null;
    document.getElementById('guardian-panel').classList.add('hidden');
    guardianState.journeyId = null;
    setGuardianStatus('Corridor feed stopped.');
}

// ---------------------------------------------------------------------
// Memory Vault — rider memories at the stops along the corridor.
// ---------------------------------------------------------------------

function renderMemories(memories) {
    const list = document.getElementById('memory-list');
    const empty = document.getElementById('memory-empty');
    if (!list) return;

    list.innerHTML = '';
    empty.classList.toggle('hidden', memories.length > 0);

    for (const memory of memories) {
        const item = document.createElement('li');
        item.className = 'memory';

        const text = document.createElement('p');
        text.className = 'memory-text';
        text.textContent = memory.text;

        const meta = document.createElement('p');
        meta.className = 'memory-meta';
        const when = new Date(memory.created_at * 1000).toLocaleDateString();
        meta.textContent = `${memory.waypoint_id.replace(/_/g, ' ')} · ${when} · ${memory.language_code}`;

        item.append(text, meta);
        list.appendChild(item);
    }
}

async function loadMemories() {
    const list = document.getElementById('memory-list');
    if (!list) return;
    list.innerHTML = '<li class="memory memory-loading">Loading memories…</li>';

    try {
        const waypointId = document.getElementById('memory-waypoint').value;
        const memories = await fetchMemories(waypointId || null, 20);
        renderMemories(memories);
    } catch (err) {
        console.error('Failed to load memories:', err);
        list.innerHTML = '';
        document.getElementById('memory-empty').classList.remove('hidden');
        document.getElementById('memory-empty').textContent = 'Could not reach the memory vault.';
    }
}

async function saveMemory(event) {
    event.preventDefault();
    const input = document.getElementById('memory-input');
    const text = input.value.trim();
    if (!text) return;

    const waypointId = document.getElementById('memory-waypoint').value;
    if (!waypointId) {
        setMemoryStatus('Pick a stop first — a memory has to belong to a place.', 'warn');
        return;
    }

    try {
        await createMemory({
            rider_id: getOrCreateRiderId(),
            waypoint_id: waypointId,
            text,
            language_code: document.getElementById('language-select').value,
        });
        input.value = '';
        setMemoryStatus('Memory saved to the vault.', 'ok');
        await loadMemories();
    } catch (err) {
        console.error('Failed to save memory:', err);
        setMemoryStatus('Could not save that memory.', 'warn');
    }
}

// ---------------------------------------------------------------------
// Minor / Guardian travel — unaccompanied minors with arrival handshake.
// ---------------------------------------------------------------------

async function createMinorJourney(payload) {
    const response = await fetch(`${API_BASE}/guardian/minor-journeys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to create minor journey: ${response.statusText}`);
    }
    return response.json();
}

async function addPickupContact(journeyId, payload) {
    const response = await fetch(`${API_BASE}/guardian/journeys/${encodeURIComponent(journeyId)}/pickup-contacts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to add pickup contact: ${response.statusText}`);
    }
    return response.json();
}

async function getPickupContacts(journeyId) {
    const response = await fetch(`${API_BASE}/guardian/journeys/${encodeURIComponent(journeyId)}/pickup-contacts`);
    if (!response.ok) {
        throw new Error(`Failed to fetch pickup contacts: ${response.statusText}`);
    }
    return response.json();
}

async function verifyArrivalHandshake(journeyId, payload) {
    const response = await fetch(`${API_BASE}/guardian/journeys/${encodeURIComponent(journeyId)}/arrival-handshake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to verify handshake: ${response.statusText}`);
    }
    return response.json();
}

function setMinorStatus(text, tone = 'info') {
    const el = document.getElementById('minor-setup-status');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
}

function setPickupStatus(text, tone = 'info') {
    const el = document.getElementById('pickup-contact-status');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
}

function setHandshakeStatus(text, tone = 'info') {
    const el = document.getElementById('handshake-status');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
}

function renderMinorJourney(journey) {
    const setupEl = document.getElementById('minor-guardian-setup');
    const activeEl = document.getElementById('minor-guardian-active');
    const headlineEl = document.getElementById('minor-guardian-headline');
    const factsEl = document.getElementById('minor-guardian-facts');
    const handshakeFormEl = document.getElementById('arrival-handshake-form');
    const handshakeCompleteEl = document.getElementById('handshake-complete');
    const contactSelectEl = document.getElementById('handshake-contact');

    if (!activeEl || !headlineEl || !factsEl) return;

    setupEl.classList.add('hidden');
    activeEl.classList.remove('hidden');

    // Headline
    headlineEl.textContent = journey.is_minor_journey
        ? `Tracking ${journey.minor_name || 'minor'} (${journey.minor_age}y) — ${journey.guardian_contact_phone || 'no guardian phone'}`
        : 'Minor journey not configured';

    // Facts
    factsEl.innerHTML = '';
    const rows = [
        ['Minor', journey.minor_name || '—'],
        ['Age', journey.minor_age ? `${journey.minor_age}` : '—'],
        ['Guardian phone', journey.guardian_contact_phone || '—'],
        ['Destination', journey.destination_waypoint_id || '—'],
        ['Pickup contacts', journey.pickup_contacts?.length || 0],
        ['Handshake complete', journey.arrival_handshake_completed ? 'Yes' : 'No'],
    ];
    for (const [label, value] of rows) {
        const dt = document.createElement('dt');
        dt.textContent = label;
        const dd = document.createElement('dd');
        dd.textContent = value;
        factsEl.append(dt, dd);
    }

    // Render pickup contacts
    renderPickupContacts(journey);

    // Arrival handshake UI
    if (journey.arrival_handshake_completed) {
        handshakeFormEl.classList.add('hidden');
        handshakeCompleteEl.classList.remove('hidden');
        document.getElementById('handshake-contact-name').textContent = journey.pickup_contacts?.find(pc => pc.verified_at)?.name || 'Contact';
        document.getElementById('handshake-time').textContent = journey.handshake_completed_at
            ? new Date(journey.handshake_completed_at * 1000).toLocaleString()
            : '—';
    } else if (journey.pickup_contacts?.length > 0) {
        handshakeFormEl.classList.remove('hidden');
        handshakeCompleteEl.classList.add('hidden');
        // Populate contact select
        if (contactSelectEl) {
            contactSelectEl.innerHTML = '<option value="">Select contact…</option>';
            for (const pc of journey.pickup_contacts) {
                const opt = document.createElement('option');
                opt.value = pc.contact_id;
                opt.textContent = `${pc.name} (${pc.relation})`;
                contactSelectEl.appendChild(opt);
            }
        }
    } else {
        handshakeFormEl.classList.add('hidden');
        handshakeCompleteEl.classList.add('hidden');
    }
}

function renderPickupContacts(journey) {
    const listEl = document.getElementById('pickup-contacts-list');
    if (!listEl) return;
    listEl.innerHTML = '';
    const contacts = journey.pickup_contacts || [];
    if (contacts.length === 0) {
        listEl.innerHTML = '<li class="minor-contact-empty">No pickup contacts added yet.</li>';
        return;
    }
    for (const pc of contacts) {
        const li = document.createElement('li');
        li.className = 'minor-contact-item';
        const verified = pc.verified_at ? '✅ Verified' : `🔐 Code: ${pc.verification_code || '—'}`;
        li.innerHTML = `
            <strong>${pc.name}</strong> — ${pc.relation} — ${pc.phone}
            <span class="minor-contact-status">${verified}</span>
        `;
        listEl.appendChild(li);
    }
}

async function initMinorGuardian() {
    const form = document.getElementById('minor-setup-form');
    const pickupForm = document.getElementById('pickup-contact-form');
    const handshakeForm = document.getElementById('arrival-handshake-form');

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('btn-create-minor-journey');
            btn.disabled = true;
            setMinorStatus('Creating minor journey…');

            try {
                const payload = {
                    minor_name: document.getElementById('minor-name').value.trim(),
                    minor_age: parseInt(document.getElementById('minor-age').value, 10),
                    guardian_contact_phone: document.getElementById('guardian-phone').value.trim(),
                    ticket_reference: document.getElementById('minor-ticket-ref').value.trim() || undefined,
                    origin_waypoint_id: document.getElementById('minor-origin').value,
                    destination_waypoint_id: document.getElementById('minor-destination').value,
                };
                const journey = await createMinorJourney(payload);
                guardianState.journeyId = journey.journey_id;
                // Also start polling for this journey
                renderMinorJourney(journey);
                setMinorStatus('Minor journey created! Add pickup contacts below.', 'ok');
            } catch (err) {
                setMinorStatus(err.message, 'warn');
            } finally {
                btn.disabled = false;
            }
        });
    }

    if (pickupForm) {
        pickupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!guardianState.journeyId) {
                setPickupStatus('Create a minor journey first.', 'warn');
                return;
            }
            const btn = document.getElementById('btn-add-pickup-contact');
            btn.disabled = true;
            setPickupStatus('Adding pickup contact…');

            try {
                const contact = await addPickupContact(guardianState.journeyId, {
                    name: document.getElementById('pickup-name').value.trim(),
                    phone: document.getElementById('pickup-phone').value.trim(),
                    relation: document.getElementById('pickup-relation').value.trim(),
                });
                setPickupStatus(`Added ${contact.name} — code: ${contact.verification_code}`, 'ok');
                pickupForm.reset();
                // Refresh journey to show new contact
                const journey = await fetchJourneyEta(guardianState.journeyId);
                renderMinorJourney(journey);
            } catch (err) {
                setPickupStatus(err.message, 'warn');
            } finally {
                btn.disabled = false;
            }
        });
    }

    if (handshakeForm) {
        handshakeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!guardianState.journeyId) {
                setHandshakeStatus('No active minor journey.', 'warn');
                return;
            }
            const btn = document.getElementById('btn-verify-handshake');
            btn.disabled = true;
            setHandshakeStatus('Verifying handshake…');

            try {
                const result = await verifyArrivalHandshake(guardianState.journeyId, {
                    contact_id: document.getElementById('handshake-contact').value,
                    verification_code: document.getElementById('handshake-code').value.trim(),
                });
                if (result.verified) {
                    setHandshakeStatus('Handshake verified — child safely collected!', 'ok');
                    handshakeForm.classList.add('hidden');
                    document.getElementById('handshake-complete').classList.remove('hidden');
                    handshakeForm.reset();
                    // Refresh journey
                    const journey = await fetchJourneyEta(guardianState.journeyId);
                    renderMinorJourney(journey);
                } else {
                    setHandshakeStatus('Invalid code — please check and try again.', 'warn');
                }
            } catch (err) {
                setHandshakeStatus(err.message, 'warn');
            } finally {
                btn.disabled = false;
            }
        });
    }
}

// ---------------------------------------------------------------------
// Journey Guardian initialization
// ---------------------------------------------------------------------

function initGuardian() {
    document.getElementById('btn-start-feed')?.addEventListener('click', startGuardianFeed);
    document.getElementById('btn-stop-feed')?.addEventListener('click', stopGuardianFeed);
    document.getElementById('btn-copy-link')?.addEventListener('click', copyGuardianLink);
    document.getElementById('btn-share-whatsapp')?.addEventListener('click', shareGuardianLinkWhatsApp);

    initMinorGuardian();

    const waypointSelect = document.getElementById('memory-waypoint');
    if (waypointSelect) {
        // Populated from the corridor the backend already serves, so the two
        // can never disagree about which stops exist.
        fetchRoute()
            .then((waypoints) => {
                for (const waypoint of waypoints) {
                    const option = document.createElement('option');
                    option.value = waypoint.id;
                    option.textContent = waypoint.name;
                    waypointSelect.appendChild(option);
                }
                return loadMemories();
            })
            .catch((err) => console.error('Failed to populate stops:', err));

        waypointSelect.addEventListener('change', loadMemories);
    }

    document.getElementById('memory-form')?.addEventListener('submit', saveMemory);
}

// ---------------------------------------------------------------------
// Memory Vault — rider memories at the stops along the corridor.
// ---------------------------------------------------------------------
