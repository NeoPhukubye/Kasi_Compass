# Frontend — Kasi Compass

MapLibre GL JS animated frontend for the Pretoria to Cape Town journey mapper.

## Accessibility for Elderly Users

This app is designed to be easy to use for elderly people, on both cellphones and laptops:

- **Large text** — base font size is 20px (large-print mode bumps to 26px)
- **Large-print toggle** — an "Aa" button in the top-right corner increases text size further
- **High contrast** — dark green primary color on white backgrounds
- **Large touch targets** — all buttons are at least 60px tall, 56px wide
- **Clear focus indicators** — visible focus rings on all interactive elements
- **Responsive layout** — works on cellphones (single column, full-width buttons) and laptops
- **Reduced motion support** — respects `prefers-reduced-motion` for users who prefer less animation

## Files

```
frontend/
  index.html              # Main entry point
  css/style.css           # Styles (elderly-friendly, responsive)
  js/geo.js               # Shared haversine + along-track progress interpolation
  js/api.js               # Backend API client
  js/map.js               # MapLibre map, route, markers, animation
  js/app.js               # Mode switching, GPS, story cards, large-print toggle
```

Note the script order in `index.html`: `geo.js` must load before `app.js`, since
`app.js` calls `haversineMeters` and `alongTrackProgress` from it.

## Quick start

Serve the `frontend/` directory with any static file server, e.g.:

```bash
cd frontend && python3 -m http.server 3000
```

Then open `http://localhost:3000` in a browser.

## Requirements

- Backend running at `http://localhost:8000` (FastAPI service in `backend/`)
- Internet connection for MapLibre GL JS and OpenStreetMap raster tiles
- **No API key required.** The map uses MapLibre + OpenStreetMap rather than Google Maps,
  precisely so no billable key ships in public frontend JavaScript, and no AI service is
  called at request time. `GEMINI_API_KEY` is used only by the offline translation tool
  (`backend/tools/translate_stories.py`).

## Modes

- **Explorer Mode** — animated virtual ride along the route; stories surface as each waypoint is reached.
- **Companion Mode** — uses device GPS to auto-trigger stories as you pass each waypoint.

## Notes

- The backend must have CORS configured if the frontend is served from a different origin.
- Stories currently cover Kimberley and Matjiesfontein only (see `backend/app/story_engine/content_store.py`).
- In Companion Mode, the train icon is positioned with `alongTrackProgress` (true
  along-track interpolation), so it moves smoothly instead of jumping from station to
  station. This is client-side animation only — the backend still decides which story
  triggers.