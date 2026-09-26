// ---------------------------------------------------------------------
// Station Time Machine — schematic era renderer.
//
// Replaces what used to be here: two <img> elements both pointing at
// assets/background.jpg, captioned "Past Era" and "Present". That showed
// the same stock photograph twice inside a product whose whole argument is
// that it never displays something it cannot substantiate.
//
// What this draws instead is a schematic of the station's *physical
// layout* in the selected era — running lines, platform faces, catenary,
// and traction — built from the era data the backend serves. It is labelled
// a reconstruction, and it is genuinely different per era: a two-line
// passing loop at Matjiesfontein in 1970, a thirteen-track interchange at
// Park Station in 2023, catenary appearing on the mainline in 1990 and not
// in 1970.
//
// Genuine archival photography is still pending heritage-partner outreach,
// and the panel says so rather than dressing a placeholder up as a
// historical record.
// ---------------------------------------------------------------------

const SVG_NS = 'http://www.w3.org/2000/svg';

const ERA_COLORS = {
    steam: { line: '#5b4636', accent: '#8a6f52', label: 'Steam' },
    diesel: { line: '#3d4a5c', accent: '#5f7391', label: 'Diesel-electric' },
    electric: { line: '#1a472a', accent: '#2d6a4f', label: 'Electric' },
    mixed: { line: '#3d4a5c', accent: '#2d6a4f', label: 'Electric + diesel' },
};

// Which traction the corridor was running in a given year. Kept in step
// with CORRIDOR_ERAS in backend/app/story_engine/content_store.py.
function tractionForYear(year) {
    if (year <= 1970) return 'steam';
    if (year <= 1990) return 'diesel';
    return 'mixed';
}

function el(name, attrs = {}, text = null) {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) {
        node.setAttribute(key, String(value));
    }
    if (text !== null) {
        node.textContent = text;
    }
    return node;
}

/**
 * Render the schematic into a container. Replaces its contents entirely.
 */
function renderEraStation(container, stopName, era) {
    if (!container) return;
    container.innerHTML = '';

    if (!era) {
        container.appendChild(buildNote('No era data recorded for this stop.'));
        return;
    }

    const layout = era.layout;
    if (!layout) {
        // Deliberately not drawing a plausible-looking station. The narrative
        // still shows; the layout is simply reported as unrecorded.
        container.appendChild(buildNote(
            `${stopName}: the station layout for ${era.year} is not yet surveyed. The written record for this era is shown below.`
        ));
        return;
    }

    const palette = ERA_COLORS[tractionForYear(era.year)] || ERA_COLORS.diesel;
    const width = 520;
    const height = 200;
    const trackCount = Math.max(2, layout.tracks || 2);
    const platformCount = Math.max(1, layout.platforms || 1);
    const marginTop = 34;
    const marginBottom = 40;
    const usable = height - marginTop - marginBottom;
    const spacing = usable / (trackCount - 1);
    const trackStart = 60;
    const trackEnd = width - 40;

    const svg = el('svg', {
        viewBox: `0 0 ${width} ${height}`,
        class: 'era-schematic',
        role: 'img',
        'aria-label':
            `Schematic reconstruction of ${stopName} in ${era.year}: ` +
            `${layout.tracks} running lines and ${layout.platforms} platform faces, ` +
            `${era.traction}.`,
    });

    // Ground line.
    svg.appendChild(el('line', {
        x1: 24, y1: marginTop - 12, x2: width - 24, y2: marginTop - 12,
        stroke: '#d8d8d0', 'stroke-width': 2,
    }));

    for (let i = 0; i < trackCount; i += 1) {
        const y = marginTop + i * spacing;
        svg.appendChild(el('line', {
            x1: trackStart, y1: y, x2: trackEnd, y2: y,
            stroke: palette.line, 'stroke-width': 2.5, 'stroke-linecap': 'round',
        }));
        // Sleepers, on every other track only, so the drawing stays legible
        // at the panel's real size.
        if (i % 2 === 0) {
            for (let x = trackStart + 10; x < trackEnd; x += 16) {
                svg.appendChild(el('line', {
                    x1: x, y1: y - 4, x2: x, y2: y + 4,
                    stroke: '#c8c8c0', 'stroke-width': 1,
                }));
            }
        }
    }

    // Platform faces as raised blocks alongside the running lines.
    for (let p = 0; p < platformCount; p += 1) {
        const y = marginTop - 4 + p * (usable / Math.max(1, platformCount - 0.001));
        const clamped = Math.min(y, marginTop + usable + 4);
        svg.appendChild(el('rect', {
            x: 26, y: clamped - 5, width: 30, height: 10, rx: 2,
            fill: '#e8e4d9', stroke: '#b9b3a3', 'stroke-width': 1,
        }));
        svg.appendChild(el('text', {
            x: 41, y: clamped + 4, 'text-anchor': 'middle',
            'font-size': 9, fill: '#6b6555',
        }, `P${p + 1}`));
    }

    // Catenary, only where the era says the line was electrified. This is
    // the most visible change between the 1970 and 1990 schematics.
    if (era.electrified) {
        for (let i = 0; i < trackCount; i += 1) {
            const y = marginTop + i * spacing - 9;
            svg.appendChild(el('line', {
                x1: trackStart, y1: y, x2: trackEnd, y2: y,
                stroke: palette.accent, 'stroke-width': 1, opacity: 0.55,
            }));
            for (let x = trackStart + 18; x < trackEnd; x += 42) {
                svg.appendChild(el('line', {
                    x1: x, y1: y, x2: x, y2: y + 9,
                    stroke: palette.accent, 'stroke-width': 1, opacity: 0.45,
                }));
            }
        }
        svg.appendChild(el('text', {
            x: trackEnd, y: marginTop - 20, 'text-anchor': 'end',
            'font-size': 10, fill: palette.accent,
        }, 'electrified line'));
    } else {
        svg.appendChild(el('text', {
            x: trackEnd, y: marginTop - 20, 'text-anchor': 'end',
            'font-size': 10, fill: '#8a8577',
        }, 'diesel line — not electrified'));
    }

    // Legend: what the drawing is actually counting.
    svg.appendChild(el('text', {
        x: 26, y: height - 12, 'font-size': 10, fill: '#6b6555',
    }, `${layout.tracks} running lines · ${layout.platforms} platform faces · ${layout.station_class.replace(/_/g, ' ')}`));

    svg.appendChild(el('text', {
        x: trackEnd, y: height - 12, 'text-anchor': 'end',
        'font-size': 10, 'font-weight': '600', fill: palette.line,
    }, `${era.year} — ${palette.label}`));

    container.appendChild(svg);

    const change = document.createElement('p');
    change.className = 'era-change';
    change.textContent = layout.change;
    container.appendChild(change);

    const facts = document.createElement('dl');
    facts.className = 'era-facts';
    for (const [label, value] of [
        ['Traction', era.traction],
        ['Signalling', era.signalling],
        ['Line', era.electrified ? 'Electrified' : 'Not electrified'],
    ]) {
        const term = document.createElement('dt');
        term.textContent = label;
        const definition = document.createElement('dd');
        definition.textContent = value;
        facts.append(term, definition);
    }
    container.appendChild(facts);
}

function buildNote(text) {
    const note = document.createElement('p');
    note.className = 'era-note';
    note.textContent = text;
    return note;
}
