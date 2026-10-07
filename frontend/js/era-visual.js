// ---------------------------------------------------------------------
// Station Time Machine — schematic era reconstruction.
//
// The Time Machine is the frontend half of the backend's era data
// (backend/app/story_engine/content_store.py: get_era_details). It renders
// what the backend can actually support: a schematic reconstruction of a
// station's physical layout in each era — how many platform faces and running
// lines it had, what hauled its trains, whether the line was electrified, and
// how it was signalled. These are structural facts about infrastructure, and
// they change in a way that is genuinely different per era.
//
// This replaces what used to be there: two <img> elements both pointing at
// the same placeholder photograph, captioned "Past Era" and "Present". The
// backend never sent image_past/image_present, so the panel was showing the
// same stock photo twice inside a product whose whole argument is that it
// never shows a rider something it cannot substantiate. Stops with no
// surveyed layout say so rather than drawing an invented station.
//
// The panel is rendered lazily by showEraVisual(stopId), which the stop
// insights panel calls when it loads. No DOM is built at import time, so the
// module can be loaded before the panel exists.
// ---------------------------------------------------------------------

function renderEraLayout(layout) {
    // A schematic reconstruction: one row per platform face, one line per
    // running track, drawn as a simple grid. This is a scale sketch for the
    // station's class (a passing loop has two running lines; a junction like
    // De Aar has a yard), not a surveyed platform count — the backend marks
    // every payload with reconstruction: true so the UI can label it as a
    // schematic rather than passing it off as a photograph.
    const rows = [];
    for (let p = 0; p < layout.platforms; p++) {
        const line = document.createElement('div');
        line.className = 'era-schematic-line';
        line.style.cssText = `
            height: 18px;
            border: 2px solid #1a472a;
            border-radius: 3px;
            margin: 2px 0;
            background: repeating-linear-gradient(
                90deg,
                #1a472a 0 14px,
                #e8e8e0 14px 22px
            );
        `;
        line.setAttribute('aria-label', `Platform ${p + 1}`);
        rows.push(line);
    }
    return rows;
}

function showEraVisual(stopId) {
    const panel = document.getElementById('era-visual');
    if (!panel) return;
    if (!stopId) {
        panel.innerHTML = '';
        panel.classList.add('hidden');
        return;
    }

    const data = window.KASI_ERA_DETAILS && window.KASI_ERA_DETAILS[stopId];
    if (!data || Object.keys(data).length === 0) {
        panel.innerHTML = `<p class="era-note">No era reconstruction is recorded for ${stopId.replace(/_/g, ' ')} yet — heritage-partner outreach is still pending.</p>`;
        panel.classList.remove('hidden');
        return;
    }

    const years = Object.keys(data).sort();
    const fragments = [];
    for (const year of years) {
        const era = data[year];
        const block = document.createElement('div');
        block.className = 'era-block';

        const heading = document.createElement('h4');
        heading.className = 'era-year';
        heading.textContent = `${year} — ${era.title}`;
        block.appendChild(heading);

        if (era.layout_recorded && era.layout) {
            const schematic = document.createElement('div');
            schematic.className = 'era-schematic';
            schematic.setAttribute('aria-label', `Schematic of ${stopId.replace(/_/g, ' ')} station layout in ${year}`);
            const lines = renderEraLayout(era.layout);
            for (const line of lines) schematic.appendChild(line);
            block.appendChild(schematic);

            const change = document.createElement('p');
            change.className = 'era-change';
            change.textContent = era.layout.change;
            block.appendChild(change);
        } else {
            const note = document.createElement('p');
            note.className = 'era-note';
            note.textContent = `No surveyed layout is recorded for ${stopId.replace(/_/g, ' ')} in ${year} — the era narrative is shown instead, without an invented station drawing.`;
            block.appendChild(note);
        }

        const narrative = document.createElement('p');
        narrative.className = 'era-narrative';
        narrative.textContent = era.narrative;
        block.appendChild(narrative);

        const facts = document.createElement('dl');
        facts.className = 'era-facts';
        for (const [label, value] of Object.entries({
            Traction: era.traction,
            Signalling: era.signalling,
            Electrified: era.electrified ? 'Yes' : 'No',
        })) {
            const dt = document.createElement('dt');
            dt.textContent = label;
            const dd = document.createElement('dd');
            dd.textContent = value;
            facts.append(dt, dd);
        }
        block.appendChild(facts);

        const corridorNote = document.createElement('p');
        corridorNote.className = 'era-note';
        corridorNote.textContent = era.corridor_note;
        block.appendChild(corridorNote);

        fragments.push(block);
    }

    panel.innerHTML = '';
    for (const fragment of fragments) panel.appendChild(fragment);
    panel.classList.remove('hidden');
}

// Expose for the stop-insights panel to call after it has loaded era data.
window.showEraVisual = showEraVisual;