// ---------------------------------------------------------------------
// Family tracking view — what a person opens when a rider pastes a
// tracking link into WhatsApp.
//
// Deliberately the smallest possible surface: no map, no controls, no way
// to change anything. The rider's link is a capability, and this page only
// spends it on reading. The token arrives in the URL fragment rather than
// the path so it is never sent to a server in a request line or written to
// an access log on the way in.
// ---------------------------------------------------------------------

const TRACK_POLL_MS = 10000;

function readTokenFromHash() {
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return null;
    const params = new URLSearchParams(hash);
    return params.get('token');
}

function formatEtaTime(iso) {
    if (!iso) return 'Not available yet';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return 'Not available yet';
    return date.toLocaleString(undefined, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function renderMilestones(milestones) {
    const list = document.getElementById('track-milestones');
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

function renderView(view) {
    const eta = view.eta;
    const dot = document.getElementById('status-dot');
    const status = eta.status;
    dot.className = 'status-dot';
    if (status === 'on_time' || status === 'delayed' || status === 'arrived') {
    dot.classList.add('green');
    } else if (status === 'stopped' || status === 'no_data') {
    dot.classList.add('amber');
    } else if (status === 'signal_lost') {
    dot.classList.add('red');
    }

    document.getElementById('track-label').textContent =
        view.tracking.display_name || 'Live journey';
    document.getElementById('track-headline').textContent = view.headline;

    const freshness = eta.last_report_seconds_ago === null
        ? 'No report yet'
        : `Last report ${Math.round(eta.last_report_seconds_ago)}s ago`;
    const provenance = eta.last_report_source
        ? ` (from ${eta.last_report_source.replace(/_/g, ' ')})`
        : '';
    document.getElementById('track-status').textContent = freshness + provenance;

    const rows = [
        ['Where is the train', eta.position ? eta.position.nearest_waypoint_name : 'Unknown'],
        ['Province', eta.province || '—'],
        ['Next province', eta.next_province || 'Final province'],
        ['Distance covered', eta.position ? `${eta.position.distance_along_km} km of ${eta.position.total_km} km` : '—'],
        ['Moving at', `${eta.observed_speed_kmh} km/h`],
        ['Next stop', eta.eta.next_station || 'Arriving'],
        ['Expected next stop', formatEtaTime(eta.eta.next_station_at)],
        ['Expected in Cape Town', formatEtaTime(eta.eta.arrival_at)],
        ['Schedule', eta.delay_display],
    ];

    const facts = document.getElementById('track-facts');
    facts.innerHTML = '';
    for (const [label, value] of rows) {
        const term = document.createElement('dt');
        term.textContent = label;
        const definition = document.createElement('dd');
        definition.textContent = value;
        facts.append(term, definition);
    }

    renderMilestones(eta.milestones);

    document.getElementById('track-detail').classList.remove('hidden');
}

function showNotFound() {
    document.getElementById('track-view').classList.add('hidden');
    document.getElementById('track-not-found').classList.remove('hidden');
    document.getElementById('track-detail').classList.add('hidden');
}

async function refresh() {
    const token = readTokenFromHash();
    if (!token) {
        showNotFound();
        return;
    }

    try {
        const view = await fetchFamilyView(token);
        if (!view) {
            // A revoked link is indistinguishable from a bad one, on purpose.
            showNotFound();
            clearInterval(pollTimer);
            return;
        }
        renderView(view);
    } catch (err) {
        console.error('Tracking link failed to load:', err);
        document.getElementById('track-status').textContent =
            'Lost contact with the tracking service. Retrying…';
    }
}

let pollTimer = null;

function init() {
    refresh().then(() => {
        pollTimer = setInterval(refresh, TRACK_POLL_MS);
    });
}

document.addEventListener('DOMContentLoaded', init);
