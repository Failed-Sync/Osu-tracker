"""
Fetches current osu! performance rankings for one or more countries and
appends the result as a new timestamped snapshot in data/history.json.

This script is meant to be run by the GitHub Actions workflow
(.github/workflows/update-data.yml) on a schedule. It reads credentials
from the OSU_CLIENT_ID / OSU_CLIENT_SECRET environment variables, which
the workflow populates from repo secrets -- they are never written to
disk or committed.

To track more countries, add their ISO 3166-1 alpha-2 codes to COUNTRIES
below. Each country adds one extra API call per run.

Note on pagination: the rankings endpoint returns up to 50 players per
request. This script fetches a single page per country, which is enough
for any country with fewer than 50 ranked players. If you add a country
with a larger competitive scene, see the osu! API docs for cursor-based
pagination: https://osu.ppy.sh/docs/index.html#get-ranking
"""

import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---- Configuration ----------------------------------------------------
COUNTRIES = ["BW"]          # ISO 3166-1 alpha-2 codes to track
MODE = "osu"                 # osu, taiko, fruits, mania
MAX_SNAPSHOTS_KEPT = 2000    # rough cap so history.json doesn't grow forever

HERE = Path(__file__).resolve().parent
HISTORY_PATH = HERE.parent / "data" / "history.json"

AUTH_URL = "https://osu.ppy.sh/oauth/token"
API_URL = "https://osu.ppy.sh/api/v2"


def get_token() -> str:
    client_id = os.environ["OSU_CLIENT_ID"]
    client_secret = os.environ["OSU_CLIENT_SECRET"]

    resp = requests.post(
        AUTH_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "public",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_country_rankings(token: str, country: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = requests.get(
        f"{API_URL}/rankings/{MODE}/performance",
        headers=headers,
        params={"country": country},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    players = []
    for entry in data.get("ranking", []):
        players.append(
            {
                "user_id": entry["user"]["id"],
                "username": entry["user"]["username"],
                "country": country,
                "global_rank": entry["global_rank"],
                "country_rank": entry.get("country_rank"),
                "pp": entry["pp"],
                "accuracy": round(entry["hit_accuracy"], 2),
            }
        )
    return players


def load_history() -> dict:
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"snapshots": []}


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
        f.write("\n")


def main() -> None:
    token = get_token()

    all_players = []
    for country in COUNTRIES:
        all_players.extend(fetch_country_rankings(token, country))
        time.sleep(0.5)  # small pause between countries, be polite to the API

    snapshot = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "players": all_players,
    }

    history = load_history()
    history["snapshots"].append(snapshot)

    if len(history["snapshots"]) > MAX_SNAPSHOTS_KEPT:
        history["snapshots"] = history["snapshots"][-MAX_SNAPSHOTS_KEPT:]

    save_history(history)
    print(f"Saved snapshot with {len(all_players)} players at {snapshot['timestamp']}")


if __name__ == "__main__":
    main()
