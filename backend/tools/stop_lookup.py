"""
CLI lookup for the Kasi Compass story-engine — fetch a stop's historical
narrative, heritage sites, and local stalls from the running backend.

Deliberately stdlib-only (urllib) so it needs no dependency that the lean
backend image (requirements.txt) doesn't already have. Run it against a
local uvicorn server, e.g.:

    cd backend && uvicorn app.story_engine.api:app --port 8000
    python3 tools/stop_lookup.py kimberley
    python3 tools/stop_lookup.py          # defaults to johannesburg_park

"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000/story-engine"


def fetch_stop_details(stop_id: str) -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/stop/{stop_id}", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Error: stop '{stop_id}' returned HTTP {exc.code}.")
        return
    except urllib.error.URLError as exc:
        print(f"Connection failed: {exc.reason}")
        return

    data = payload.get("data", {})
    print(f"\n--- {data.get('stop_name')} ---")
    if data.get("lat") is not None and data.get("lon") is not None:
        print(f"[Location]: {data['lat']}, {data['lon']}")

    print(f"\n[History]:\n{data.get('historical_narrative')}")

    print("\n[Heritage Sites]:")
    for site in data.get("heritage_sites", []):
        print(f" * {site['name']} ({site.get('era', '')}): {site.get('description', '')}")

    print("\n[Local Stalls]:")
    for stall in data.get("local_stalls", []):
        print(f" * {stall['name']} [{stall.get('category', '')}]: {stall.get('description', '')}")


if __name__ == "__main__":
    stop_arg = sys.argv[1] if len(sys.argv) > 1 else "johannesburg_park"
    fetch_stop_details(stop_arg)