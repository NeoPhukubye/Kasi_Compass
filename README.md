# Kasi Compass — Train Journey Mapper

**Every stop tells a story.**

An interactive, animated digital companion for South Africa's most storied rail journey — Pretoria to Cape Town — built for Geekulcha's **Train Journey Mapper** challenge (Geekulcha Annual Hackathon 2026, #GKHack26 #BuildForUse).

*Team NeoDev — selected 6 September 2026, physical track, BCX HQs Centurion, 25–27 September 2026.*

---

## 1. The Real-World Hook

- **Blue Train** and **Rovos Rail** both run this exact ~1,600km route today as ultra-premium, multi-day luxury experiences — Highveld goldfields, the Kimberley diamond fields, the Karoo through Matjiesfontein and Beaufort West, and the Cape Winelands.
- **Shosholoza Meyl**, PRASA's affordable long-distance service on the same corridor, has been suspended since 2024 due to a lack of serviceable locomotives, with a **planned reintroduction in 2027** — the same year Geekulcha is hosting its dedicated Train Tourism Hackathon.

That leaves a real gap right now: the only way to experience this journey's culture and history today is a luxury ticket. Kasi Compass exists to close that gap before the 2027 relaunch, and to be ready to ride shotgun on it when it happens.

## 2. Problem Statement

Nothing digital currently tells the story of the towns strung along this corridor — Kimberley's diamond rush, Matjiesfontein's Victorian time-capsule village, the Hex River Valley's wine country — to anyone who isn't already paying for a luxury seat. Existing storytelling on the luxury trains is guide-led and printed, not personal, not localized, and not something a rider keeps after the trip.

## 3. Solution

Two modes:

- **Explorer Mode** — anyone "rides" the journey virtually on an animated map, previewing every stop's story before ever buying a ticket. Works standalone today, independent of any train operator.
- **Companion Mode** — for riders actually on a train on this corridor, GPS-based geofencing auto-unlocks each stop's story as the train physically passes that point. Riders can optionally opt in to sharing their live (fuzzed, anonymous) position, so others in Companion Mode see fellow riders moving along the route — see "Live position sharing" below.

### Live position sharing: opt-in, coarse, non-persistent

A different privacy category from geofence triggering (which only ever checks a rider's own position against 8 fixed public station points): this broadcasts one rider's live location to other riders, so it gets its own guardrails, implemented in `backend/app/story_engine/live_share.py`:

- **Opt-in only** — off by default; a position is shared only after a rider explicitly checks "Share my live position" in Companion Mode, and only while GPS tracking is actually running.
- **Coarse, not exact** — every shared position is snapped to a ~150m grid cell before it's stored. Raw device GPS coordinates are never persisted, even in memory.
- **Anonymous** — riders are keyed by a random client-generated id with no link to any name, session, or other identity field.
- **Non-persistent** — positions live in an in-memory store with a 45-second TTL and are never written to disk. Restarting the backend clears all of it (and this doesn't scale past a single server process — a known, stated limitation at this project's current scope, not a silent one).
- **Explicit leave** — turning sharing off, stopping GPS tracking, or closing the tab (via `navigator.sendBeacon`) removes a rider's position immediately rather than waiting out the TTL.

### Rider memories: the older generation relives, the new generation creates

Every stop carries a curated *historical* story (see the content model below) — that's the old memory of a place. Riders also leave *new* memories that the next traveller can relive:

- **Create (`POST /journey/memories`)** — a rider passing a stop drops a first-person memory (text, bounded to 2,000 chars, keyed to an anonymous opaque rider UUID — no name, no session). It can be **pinned to the exact spot** it was left (`lat`/`lon`, always together) and can reference a hosted **voice note** via `audio_url`.
- **Relive by stop (`GET /journey/memories`)** — newest-first memories for a waypoint (or the whole route).
- **Relive by proximity (`GET /journey/memories/nearby`)** — the geofenced unlock: a new-generation rider passing through only surfaces memories dropped within `radius` meters of their live position, so a memory left on the Big Hole platform doesn't have to compete with the whole town. The Memory Vault made literal.
- **Validation** — memories can only attach to real waypoints; unknown ids, blank/oversized text, half-provided or out-of-range coordinates, malformed rider ids, and non-http(s) `audio_url` are rejected (422). The store is bounded (oldest evicted) so a demo process can't grow without limit.
- **Persistence plan** — the in-memory `MemoryStore` (`backend/app/story_engine/memories.py`) is the documented swap target for a PostGIS `rider_memories` table (schema includes `lat`/`lon`, `audio_url`, and a spatial index for unlock lookups); the module docstring has the full interface the DB-backed store must keep so `api.py` doesn't change.

### Content model: human-sourced first, AI assistive only

Following direct feedback from Geekulcha organizers to align this build "more to a sense of reality" and reduce AI reliance, the content pipeline has been redesigned:

- **Every story is authored and reviewed by a human** — sourced from local narrators, heritage sites, and tourism-board partners along the route (see `backend/app/story_engine/content_store.py`, where every entry carries a `source` and `reviewed_by` field).
- **AI has exactly one allowed role in the content pipeline**: drafting a first-pass translation of an already human-approved story into another official South African language, for a human (ideally first-language speaker) to review before it's ever published. AI is never called at request time for stories — nothing in the runtime story path depends on an AI service being available.
- **One carefully-gated exception — the Companion Mode Route Guide** (`POST /story-engine/ask`, `backend/app/story_engine/guide.py`): when the operator sets `GEMINI_API_KEY` server-side, the request-time guide *may* ask Gemini to rephrase a grounded, human-reviewed route answer. The key is read only on the backend (`os.environ`), never shipped to the browser, and **any** failure (no key, network error, empty answer, invalid model) degrades to the fully-written corpus answer with `"ai_used": false`. There is no invented content and no hard dependency: the unsent journalistic commitment — a human answers for the corridor — stands even when the model is unavailable.
- This removes AI-outage/hallucination risk from the critical path entirely, and keeps the commitment to telling each place's story with input from people who actually live there.

#### How the AI-assisted translation is implemented

The one permitted AI role is built as a deliberately **offline, two-step tool** — `backend/tools/translate_stories.py` — using Google's **Gemini API** for first-pass translation of human-approved English stories into isiZulu, Afrikaans, isiXhosa and the other official languages (specifically to **Google Gemini (AI-assisted translation)**).

AI output cannot reach a rider unreviewed, and the tooling enforces that mechanically rather than by convention:

```
Step 1 — draft   python3 tools/translate_stories.py draft --waypoint kimberley --language zu
                 -> calls Gemini, writes translation_drafts/kimberley.zu.json
                 -> marked "reviewed": false.  content_store.py is NOT touched.

Step 2 — approve python3 tools/translate_stories.py apply --draft translation_drafts/kimberley.zu.json \
                     --reviewed-by "Sipho Ndlovu, first-language Zulu reviewer"
                 -> refuses unless a human set "reviewed": true
                 -> rejects AI-looking reviewer names ("Gemini", "GPT", "AI", ...)
                 -> prints a ready-to-paste LocalizedStory block for the reviewer to commit
```

The guardrails are covered by tests (`backend/tests/test_translation_tool.py`), including one that parses `api.py` to assert the running service imports neither the translation tool nor any AI SDK. Running the app with `GEMINI_API_KEY` unset is a **supported, fully-functional state**: the API returns human-reviewed stories with no key and no network, and the Route Guide answers purely from its corpus (`"ai_used": false`), which is what makes the TRL 4 "no AI in the request path" claim verifiable rather than aspirational.

> **Note on the map:** the map deliberately uses **MapLibre GL JS with OpenStreetMap tiles**, not Google Maps. This needs no API key and no billing account, so the animated map works offline in the lab and can't leak a key from public frontend JavaScript. A Google Maps key shipped in `frontend/js/` would be readable by anyone and billable by anyone — so the map stays on MapLibre.

## 4. Technological Architecture

```
Rider (Explorer or Companion Mode, web)          Family member (link, no install)
        |                                                      |
        v                                                      v
FastAPI Gateway  (app/story_engine/api.py)        GET /guardian/track/{token}
        |                                                      |
        v                                                      v
Story & Route Engine (Python)  ──────────────►  Journey Guardian + ETA engine
  - Geofence trigger engine                          - corridor-fed telemetry
  - Route/waypoint graph (real stations)              - observed-speed ETA + delay
  - Human-sourced content store (no AI)              - provincial milestones
  - Rider memories store (create / relive)            - one plain-language headline
        |
        v
Spatial layer (app/story_engine/spatial.py)
  - PostGIS when DATABASE_URL is set (ST_ClosestPoint / ST_LineLocatePoint
    against a geography LineString, GiST-indexed)
  - Identical API contract on SQLite otherwise, with the same along-track
    projection computed in-process — so the demo needs no infrastructure
        |
        v
MapLibre animated frontend (train position animates along the real route;
human-authored story cards surface as each waypoint is reached)
```

### Why the spatial layer has two drivers

The pitch's hardest claim is that a journey keeps reporting itself from
infrastructure rather than from the passenger's phone — a phone at 4% with
no signal in the Karoo must not decide whether a family knows anything.

`SpatialStore` answers that on PostGIS, and answers it identically on SQLite.
Both return the same `CorridorPosition`, so `eta.py`, `journey.py` and the
API never branch on which database is live, and `GET /health` reports which
one answered. Nothing needs to be provisioned to run the project; set
`DATABASE_URL` and the corridor geometry, telemetry and ETA move onto real
spatial queries.

`POST /guardian/simulate-run` exists for the same reason: with no train
available, a server-side feed can be generated along the real corridor so a
judge can watch an ETA move, a province flip and a family link update from a
feed the passenger's phone never touches.

## 5. Technology Readiness Level: TRL 4

Per organizer guidance to build to **TRL 4** ahead of the hackathon weekend, this project has moved from isolated proof-of-concept components to a validated, integrated system in a lab environment:

**TRL 3 evidence (isolated components, already had this):**
- Geofence-triggered story engine — haversine distance logic (`app/story_engine/geofence.py`)
- Real route/waypoint data model (`app/story_engine/route.py`)
- Along-track progress interpolation for smooth map animation (`frontend/js/geo.js`)
- 9 passing unit tests (`backend/tests/test_story_engine.py`)

**TRL 4 evidence (integrated system, validated together — new):**
- A single running FastAPI service (`app/story_engine/api.py`) that wires the route data, geofence engine, and human-sourced content store together into one request path -- `GET /journey/position?lat=...&lon=...` returns the correct triggered waypoint *and* its human-reviewed story in one call, with no manual glue code between modules.
- **End-to-end integration tests** (`backend/tests/test_integration.py`) that exercise this actual running app via `TestClient` -- real HTTP requests in, real JSON responses out -- including a test that confirms every returned story carries a human reviewer, not an AI attribution.
- **Rider memories over HTTP** (`POST`/`GET /journey/memories`, `GET /journey/memories/nearby`) — new memories created by riders at a stop and relived by later travellers, geofence-unlockable at the exact spot they were left; validated end-to-end (unknown waypoint, blank text, malformed rider id, bad coordinates all 422).
- **Stop discovery + live-telemetry geofence** (`GET /story-engine/stop/{id}`, `GET /story-engine/geofence/verify`, CLI in `backend/tools/stop_lookup.py`) — the Shosholoza corridor's narrative, heritage sites, stalls, and coordinates for every stop, plus proximity verification for a rider approaching a stop (default 100m radius) and the route-aware **Companion Mode Route Guide** (`POST /story-engine/ask`) that answers rider questions from the human-reviewed corpus (Gemini-rephrased only where a server-side key is set).
- **Ticket validation** (`app/story_engine/tickets.py`, `POST /tickets`, `/tickets/validate`, `/tickets/board`, `/tickets/void`) — the model behind "bound to ticket validation databases". No personal data and no payment processing. Transitions are one-way, so a photo of a used or cancelled ticket is worth nothing; boarding binds a ticket to a journey, which is what makes that journey's identity durable independently of any device.
- **Guardrail tests for the AI-assisted translation path** (`backend/tests/test_translation_tool.py`) — verifies the running API imports no AI SDK, that drafts can't be applied without human review, and that AI-looking reviewer names are rejected.
- **Spatial layer with a real database contract** (`app/story_engine/spatial.py`) — corridor centreline materialised as a `geography LineString` with a GiST index, journey telemetry in a queryable table, and along-track position resolution via `ST_ClosestPoint`/`ST_LineLocatePoint` on PostGIS. Served through an identical SQLite contract so it runs with zero infrastructure, and `GET /health` reports which driver is live.
- **Automated ETA and provincial milestones** (`app/story_engine/eta.py`, `GET /guardian/journeys/{id}/eta`) — ETA from *observed* speed, smoothed with an EWMA, compared against the timetable to produce an explicit delay figure. A stopped train or a dark feed returns **no ETA at all** plus a plain-language reason, rather than a confident guess; `speed_source` says whether a number was measured or assumed.
- **Journey Guardian with corridor-fed position** (`app/story_engine/journey.py`) — a journey's identity lives server-side, created and advanced by position reports from the corridor. The API cannot verify who is reporting, so it is explicit about it: every report carries a `source`, and the family view surfaces the most recent one and never claims a freshness it does not have.
- **Family tracking links** (`POST /guardian/journeys/{id}/links`, `GET /guardian/track/{token}`, `DELETE /guardian/links/{token}`, page `frontend/track.html`) — a read-only capability token bound to one journey, carrying no name or contact details, revocable immediately. The link is the WhatsApp-shareable artefact: paste it, the family member sees one plain-language sentence, the province, the delay and the milestone list, with no app and no account. **Links and journeys are persisted**, so a redeploy cannot invalidate a token somebody has already been sent — and a revocation is written immediately, so a restart cannot resurrect a cancelled link.
- **Digital journey passport** (`app/story_engine/passport.py`, `GET /guardian/journeys/{id}/passport`) — a stamp per station, computed from the journey's own persisted position history. A client cannot award itself a stamp by claiming it arrived somewhere: a stamp exists only if a corridor report puts the journey within 25km of that station. A feed that began late therefore leaves a visible gap with a specific explanation, rather than a backfilled-looking book of stamps.
- **QR boarding** (`GET /tickets/{ref}/qr`, `GET /scan/{ref}`) — a scannable code bound to a validated ticket, encoding the booking reference and corridor and nothing else. The scan target returns the same admissible/reason pair as the gate validation endpoint, so a scanner and a conductor cannot disagree. Uses `segno`; degrades to a clear reason rather than taking the API down.
- **Offline story packs** (`GET /journey/offline-pack`, `frontend/sw.js`, `frontend/js/offline.js`) — one stop's entire story, guide, POIs, era details and nearby memories in a single self-contained response, pre-cached before the train enters the Karoo. The service worker caches **only** packs and only GETs: a stale cache can show an old story, but it can never award a wrong stamp or book a wrong ticket, and the journey API is never cached because a frozen ETA served as live would be worse than no ETA.
- **Station Time Machine** — a schematic reconstruction of each station's physical layout per era (running lines, platform faces, catenary, traction, signalling), drawn from the corridor's documented history. This **replaces** what used to be there: two `<img>` elements both pointing at `assets/background.jpg`, captioned "Past Era" and "Present". The backend never sent `image_past`/`image_present`, so the panel was showing the same stock photo twice inside a product whose whole argument is that it never shows a rider something it cannot substantiate. Stops with no surveyed layout say so rather than drawing an invented station; genuine archival photography is still pending partner outreach and the UI says that too.
- **195/195 → 227/227 tests passing** across twelve suites, including guardrails for each of the above.

**Not yet reached (TRL 5+):**
- No live GPS feed from an actual train -- Companion Mode is validated against known coordinates in this lab environment, not yet tested onboard a moving train.
- No user testing yet with real riders -- that's the explicit purpose of the Phase 3 closed pilot below.
- No genuine archival photography for the Time Machine, and no surveyed platform counts for Germiston or Klerksdorp -- both are reported as unrecorded rather than invented.
- Story content coverage is currently 2 of 8 waypoints (Kimberley, Matjiesfontein) pending partner outreach -- see WBS Phase 1.

## 6. User Journey Story

**Naledi, 27, from Soweto -- first long-distance train trip, visiting family in Cape Town:**

1. **Discovery** -- sees a social post about Kasi Compass while planning her trip.
2. **Pre-trip** -- opens Explorer Mode, previews the Kimberley diamond-fields story.
3. **Boarding** -- scans a QR code at the station, switches to Companion Mode.
4. **En route** -- as the train passes Kimberley, her phone surfaces the human-reviewed Big Hole story, timed to the view outside.
5. **The Karoo** -- signal drops near Matjiesfontein, but the next stops' story packs were already cached.
6. **Arrival** -- collects a digital "journey passport" stamp for every stop in Cape Town and shares it online.

## 7. Consumer Phasing Plan

Direct response to organizer guidance to "set your solution to be consumer phasing." Rather than a single launch, rollout is staged:

| Phase | What | Who | When |
|---|---|---|---|
| **Phase 0 -- Closed pilot** | 10-15 friends/family walk through Explorer Mode end-to-end, feedback collected directly | Internal team + close contacts | 18-24 Sep 2026 (before hackathon weekend) |
| **Phase 1 -- Limited public pilot** | Companion Mode piloted with one confirmed operator partner (Rovos Rail or Blue Train) on a real, scheduled run | One operator + their existing passengers | 6-31 Oct 2026 |
| **Phase 2 -- Broader public launch** | Explorer Mode opens to the public with no operator dependency; story coverage expanded to all 8 waypoints | General public | Nov 2026 onward |
| **Phase 3 -- 2027 relaunch alignment** | Positioned as the official digital companion for PRASA's relaunched Shosholoza Meyl service | Mass-market domestic tourists | Timed to Shosholoza Meyl's 2027 return |

Full task-level detail, owners, and dates: see `planning/Kasi_Compass_WBS.xlsx`.

## 8. Go-to-Market Strategy

**0-6 months:** Pilot Companion Mode directly with Rovos Rail and/or the Blue Train -- both run this exact route today. Positioned as a complimentary digital add-on differentiating their existing product.

**6-18 months:** License sponsored story placements to Northern & Western Cape tourism boards and heritage sites directly on the route (Kimberley's Big Hole, Matjiesfontein's heritage village).

**Timed to 2027:** Become the official digital companion for PRASA's relaunched Shosholoza Meyl service, landing alongside Geekulcha's own 2027 Train Tourism Hackathon.

**Revenue streams:** sponsored story placements, tourism-board licensing, premium offline "language pack" for international visitors.

## 9. Team Composition

*(Fill in with actual team members -- this is a scored judging criterion.)*

| Role | Name | Background |
|---|---|---|
| Backend / Geospatial Engineer | -- | -- |
| Frontend / Map Animation Developer | -- | -- |
| Content & Localization Lead | -- | -- |
| UX & Cultural Content Lead | -- | -- |
| Partnerships / Go-to-Market Lead | -- | -- |

---

## 10. Repository Structure

```
backend/
  app/story_engine/
    route.py           # Real Pretoria-Cape Town waypoints + coordinates
    geofence.py         # Haversine-based story trigger engine
    content_store.py    # Human-sourced, human-reviewed story content
    memories.py         # Rider-shared memories ("create new / relive old")
    guide.py            # Route Guide: corpus answers, optional Gemini rephrase
    spatial.py          # PostGIS/SQLite corridor geometry + journey telemetry
    eta.py              # Observed-speed ETA, delay, provincial milestones
    journey.py          # Journey Guardian + family tracking links
    tickets.py          # Ticket validation (one-way states, no personal data)
    passport.py         # Journey passport: stamps derived from position history
    api.py               # Integrated FastAPI service (TRL 4 evidence)
  tools/
    translate_stories.py   # OFFLINE Gemini drafts for human review — not in request path
    stop_lookup.py         # Stdlib-only CLI for /story-engine/stop/{id} discovery
  tests/
    test_story_engine.py     # Unit tests (TRL 3 evidence)
    test_integration.py       # End-to-end integration tests (TRL 4 evidence)
    test_memories.py          # Rider memories store (create + relive + validation)
    test_guide.py              # Route Guide matching, corpus grounding, Gemini fallback
    test_translation_tool.py  # AI-guardrail tests (human review, no AI in runtime)
    test_spatial.py           # Corridor geometry, along-track projection, persistence
    test_eta.py               # ETA refusal cases, milestones, staleness
    test_journey.py           # Guardian links + ticket validation invariants
    test_guardian_api.py      # Spatial/Guardian/ticket/passport/QR endpoints
    test_passport_and_extras.py  # Passport stamps, era data, offline pack, QR
  .env.example          # GEMINI_API_KEY, DATABASE_URL and SQLITE_PATH template
  requirements-postgis.txt  # Optional psycopg driver for the PostGIS path
frontend/
  index.html           # Main app: map, story cards, Guardian panel, Memory Vault
  track.html           # Family tracking page (read-only, link-token in the hash)
  sw.js                # Offline story-pack service worker (packs and GETs only)
  js/geo.js             # Shared haversine + along-track progress interpolation
  js/map.js             # MapLibre map, route, markers, animation
  js/app.js             # Mode switching, GPS, story cards
  js/api.js             # Backend API client
  js/guardian.js        # Corridor feed, ETA panel, guardian links, Memory Vault
  js/track.js           # Family tracking view
  js/era-visual.js      # Station Time Machine schematic renderer
  js/offline.js         # Offline story-pack pre-caching
planning/
  Kasi_Compass_WBS.xlsx   # Full work breakdown structure with dates/owners
```

Run tests: `cd backend && PYTHONPATH=. python3 -m pytest tests/ -v`

The app runs with **no API key at all** — that is a supported state. `GEMINI_API_KEY` is needed only for the offline translation tool, and `DATABASE_URL` only to switch the spatial layer from SQLite to PostGIS. Check which one is live at `GET /health`.
