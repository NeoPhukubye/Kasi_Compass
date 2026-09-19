# Frontend — Kasi Compass

MapLibre GL JS animated frontend for the Pretoria to Cape Town journey mapper.

## Files

```
frontend/
  index.html              # Main entry point
  css/style.css           # Styles
  js/geo.js               # Shared haversine + along-track progress interpolation
  js/api.js               # Backend API client
  js/map.js               # MapLibre map, route, markers, animation
  js/app.js               # Mode switching, GPS, story cards
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
