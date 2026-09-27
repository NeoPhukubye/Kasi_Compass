// ---------------------------------------------------------------------
// Railway Alerts & Service Notifications — Frontend Client.
// ---------------------------------------------------------------------

const ALERT_SEVERITY_STYLES = {
    info: { bg: '#e8f4ea', border: '#1a472a', icon: 'ℹ️', label: 'INFO' },
    warning: { bg: '#fff3cd', border: '#a63d1f', icon: '⚠️', label: 'WARNING' },
    critical: { bg: '#f8d7da', border: '#a63d1f', icon: '🚨', label: 'CRITICAL' },
};

const ALERT_CATEGORY_LABELS = {
    delay: 'Delay',
    cancellation: 'Cancellation',
    track_works: 'Track Works',
    signal_failure: 'Signal Failure',
    rail_moved: 'Rail Displacement',
    speed_restriction: 'Speed Restriction',
    platform_change: 'Platform Change',
    service_disruption: 'Service Disruption',
    weather: 'Weather',
    other: 'Other',
};

function formatAlertTime(epoch) {
    if (!epoch) return '';
    const date = new Date(epoch * 1000);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString(undefined, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatTimeAgo(epoch) {
    if (!epoch) return '';
    const now = Date.now();
    const diffMs = now - epoch * 1000;
    if (diffMs < 0) return 'in the future';
    const diffMinutes = Math.floor(diffMs / 60000);
    if (diffMinutes < 1) return 'just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
}

function createAlertElement(alert) {
    const style = ALERT_SEVERITY_STYLES[alert.severity] || ALERT_SEVERITY_STYLES.info;
    const categoryLabel = ALERT_CATEGORY_LABELS[alert.category] || alert.category;

    const article = document.createElement('article');
    article.className = 'railway-alert';
    article.dataset.alertId = alert.alert_id;
    article.style.borderLeftColor = style.border;
    article.style.background = style.bg;

    const expiresHtml = alert.expires_at
        ? `<span class="alert-expires">Expires: ${formatAlertTime(alert.expires_at)}</span>`
        : '';

    const journeyHtml = alert.journey_id
        ? `<span class="alert-journey">Journey: ${alert.journey_id.slice(0, 8)}…</span>`
        : '';

    const stationsHtml = alert.affected_stations && alert.affected_stations.length > 0
        ? `<span class="alert-stations">Stations: ${alert.affected_stations.map(s => s.replace(/_/g, ' ')).join(', ')}</span>`
        : '';

    article.innerHTML = `
        <div class="alert-header">
            <span class="alert-icon" aria-hidden="true">${style.icon}</span>
            <div class="alert-title-row">
                <h4 class="alert-title">${alert.title}</h4>
                <span class="alert-severity-badge">${style.label}</span>
            </div>
        </div>
        <div class="alert-meta">
            <span class="alert-category">${categoryLabel}</span>
            <span class="alert-time">Posted ${formatTimeAgo(alert.created_at)}</span>
            ${journeyHtml}
            ${stationsHtml}
            ${expiresHtml}
        </div>
        <p class="alert-message">${alert.message}</p>
    `;

    return article;
}

async function fetchAlerts(corridorId = 'pretoria_cape_town', journeyId = null) {
    const params = new URLSearchParams({ corridor_id: corridorId });
    if (journeyId) params.set('journey_id', journeyId);

    const apiBase = window.KASI_API_BASE || window.API_BASE || '';
    try {
        const response = await fetch(`${apiBase}/alerts?${params.toString()}`);
        if (!response.ok) throw new Error(`Failed to fetch alerts: ${response.statusText}`);
        return await response.json();
    } catch (err) {
        console.warn('Failed to fetch railway alerts:', err);
        return [];
    }
}

async function fetchAlertCounts(corridorId = 'pretoria_cape_town') {
    const apiBase = window.KASI_API_BASE || window.API_BASE || '';
    try {
        const response = await fetch(`${apiBase}/alerts/count?corridor_id=${encodeURIComponent(corridorId)}`);
        if (!response.ok) throw new Error(`Failed to fetch alert counts: ${response.statusText}`);
        return await response.json();
    } catch (err) {
        console.warn('Failed to fetch alert counts:', err);
        return { info: 0, warning: 0, critical: 0 };
    }
}

function renderAlerts(alerts, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';

    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<p class="alert-empty">No active service alerts.</p>';
        return;
    }

    for (const alert of alerts) {
        const el = createAlertElement(alert);
        container.appendChild(el);
    }
}

function renderAlertCounts(counts, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const total = (counts.info || 0) + (counts.warning || 0) + (counts.critical || 0);
    if (total === 0) {
        container.innerHTML = '<span class="alert-count-none">No active alerts</span>';
        return;
    }

    let html = '';
    if (counts.critical > 0) html += `<span class="alert-count critical" title="${counts.critical} critical alert${counts.critical !== 1 ? 's' : ''}">🚨 ${counts.critical}</span>`;
    if (counts.warning > 0) html += `<span class="alert-count warning" title="${counts.warning} warning alert${counts.warning !== 1 ? 's' : ''}">⚠️ ${counts.warning}</span>`;
    if (counts.info > 0) html += `<span class="alert-count info" title="${counts.info} info alert${counts.info !== 1 ? 's' : ''}">ℹ️ ${counts.info}</span>`;

    container.innerHTML = html;
}

async function initRailwayAlerts(options = {}) {
    const {
        corridorId = 'pretoria_cape_town',
        journeyId = null,
        containerId = 'railway-alerts',
        countsContainerId = 'alert-counts',
        pollIntervalMs = 60000,
    } = options;

    async function refresh() {
        const [alerts, counts] = await Promise.all([
            fetchAlerts(corridorId, journeyId),
            fetchAlertCounts(corridorId),
        ]);
        renderAlerts(alerts, containerId);
        renderAlertCounts(counts, countsContainerId);
    }

    await refresh();

    if (pollIntervalMs > 0) {
        setInterval(refresh, pollIntervalMs);
    }
}

// Expose for global use
window.RailwayAlerts = {
    fetchAlerts,
    fetchAlertCounts,
    renderAlerts,
    renderAlertCounts,
    init: initRailwayAlerts,
    createAlertElement,
    formatAlertTime,
    formatTimeAgo,
};