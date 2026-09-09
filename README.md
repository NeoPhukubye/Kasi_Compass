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
- **Companion Mode** — for riders actually on a train on this corridor, GPS-based geofencing auto-unlocks each stop's story as the train physically passes that point.

### Content model: human-sourced first, AI assistive only

Following direct feedback from Geekulcha organizers to align this build "more to a sense of reality" and reduce AI reliance, the content pipeline has been redesigned:

- **Every story is authored and reviewed by a human** — sourced from local narrators, heritage sites, and tourism-board partners along the route (see `backend/app/story_engine/content_store.py`, where every entry carries a `source` and `reviewed_by` field).
- **AI has exactly one allowed role**: drafting a first-pass translation of an already human-approved story into another official South African language, for a human (ideally first-language speaker) to review before it's ever published. AI is never called at request time — nothing in the runtime request path depends on an AI service being available.
- This removes AI-outage/hallucination risk from the critical path entirely, and keeps the commitment to telling each place's story with input from people who actually live there.

## 4. Technological Architecture

```
Rider (Explorer or Companion Mode, web/PWA)
        |
        v
FastAPI Gateway  (app/story_engine/api.py)
        |
        v
Story & Route Engine (Python)
  - Geofence trigger engine (haversine distance vs. waypoint radius)
  - Route/waypoint graph (real Pretoria-Cape Town stations + coordinates)
  - Human-sourced content store (no AI call in the runtime path)
        |
        v
PostGIS (production) / in-process data (current lab build)
        |
        v
MapLibre animated frontend (train position animates along the real route;
human-authored story cards surface as each waypoint is reached)
```

## 5. Technology Readiness Level: TRL 4

Per organizer guidance to build to **TRL 4** ahead of the hackathon weekend, this project has moved from isolated proof-of-concept components to a validated, integrated system in a lab environment:

**TRL 3 evidence (isolated components, already had this):**
- Geofence-triggered story engine — haversine distance logic (`app/story_engine/geofence.py`)
- Real route/waypoint data model (`app/story_engine/route.py`)
- 9 passing unit tests (`backend/tests/test_story_engine.py`)

**TRL 4 evidence (integrated system, validated together — new):**
- A single running FastAPI service (`app/story_engine/api.py`) that wires the route data, geofence engine, and human-sourced content store together into one request path -- `GET /journey/position?lat=...&lon=...` returns the correct triggered waypoint *and* its human-reviewed story in one call, with no manual glue code between modules.
- **5 end-to-end integration tests** (`backend/tests/test_integration.py`) that exercise this actual running app via `TestClient` -- real HTTP requests in, real JSON responses out -- including a test that confirms every returned story carries a human reviewer, not an AI attribution.
- **14/14 tests passing** across both suites.

**Not yet reached (TRL 5+):**
- No live GPS feed from an actual train -- Companion Mode is validated against known coordinates in this lab environment, not yet tested onboard a moving train.
- No user testing yet with real riders -- that's the explicit purpose of the Phase 3 closed pilot below.
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
    api.py               # Integrated FastAPI service (TRL 4 evidence)
  tests/
    test_story_engine.py   # Unit tests (TRL 3 evidence)
    test_integration.py     # End-to-end integration tests (TRL 4 evidence)
planning/
  Kasi_Compass_WBS.xlsx   # Full work breakdown structure with dates/owners
```

Run tests: `cd backend && PYTHONPATH=. python3 -m pytest tests/ -v`
