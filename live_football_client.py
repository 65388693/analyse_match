"""
live_football_client.py
Client Live Football API — blessures, arbitre.
"""

import os
import json
import re
import requests
from config import CACHE_DIR, LIVE_FOOTBALL_KEY

BASE_URL = "https://live-football-api.com/api/v1"


def _cache_path(key: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', key)
    safe = re.sub(r'_+', '_', safe).strip('_')[:150]
    return os.path.join(CACHE_DIR, f"lf_{safe}.json")


def _load_cache(key):
    path = _cache_path(key)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(key, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _call(endpoint, params):
    if not LIVE_FOOTBALL_KEY:
        return None
    full_params = {**params, "api_key": LIVE_FOOTBALL_KEY, "lang": "en"}
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=full_params, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def get_matches_for_date(date: str, force_refresh: bool = False):
    """Return the global match schedule for a date, cached by date."""
    cache_key = f"matches_{date}"
    cached = None if force_refresh else _load_cache(cache_key)
    if cached is not None:
        return cached

    data = _call("matches", {"date": date})
    if not isinstance(data, dict):
        return None

    matches = data.get("data", {}).get("matches")
    if not isinstance(matches, list):
        return None

    _save_cache(cache_key, matches)
    return matches


def get_cached_matches_for_date(date: str):
    """Read a date's fixtures without requesting them from the provider."""
    return _load_cache(f"matches_{date}")


def find_match(home: str, away: str, date: str):
    cache_key = f"find_{date}_{home}_{away}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    matches = get_matches_for_date(date)
    if matches is None:
        return None

    EXCLUDE = ["u19", "u21", "u23", "u18", "u20", "u17",
               "women", "féminin", "feminin", " b", " ii", "reserve"]

    home_low = home.lower().strip()
    away_low = away.lower().strip()

    for m in matches:
        h = m.get("home", {}).get("name", "").lower()
        a = m.get("away", {}).get("name", "").lower()
        if any(ex in h or ex in a for ex in EXCLUDE):
            continue
        if (home_low in h or h in home_low) and (away_low in a or a in away_low):
            mid = m.get("id")
            _save_cache(cache_key, mid)
            return mid
    return None


def get_injuries(match_id: str):
    if not match_id:
        return None
    cache_key = f"inj_{match_id}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    data = _call("injuries", {"match_id": match_id})
    if not data:
        return None

    inj = data.get("data", {}).get("injuries", {})
    _save_cache(cache_key, inj)
    return inj


def get_cached_injuries(match_id: str):
    return _load_cache(f"inj_{match_id}") if match_id else None


def get_officials(match_id: str):
    if not match_id:
        return None
    cache_key = f"off_{match_id}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    data = _call("officials", {"match_id": match_id})
    if not data:
        return None

    officials = data.get("data", {}).get("officials", [])
    main = None
    for o in officials:
        if o.get("role") == "Main":
            main = {
                "name": o.get("name"),
                "avg_yellow_cards": o.get("avg_yellow_cards") or 4.0,
                "avg_red_cards": o.get("avg_red_cards") or 0.20,
            }
            break

    if not main:
        main = {"name": "Non désigné", "avg_yellow_cards": 4.0, "avg_red_cards": 0.20}

    _save_cache(cache_key, main)
    return main


def get_cached_officials(match_id: str):
    return _load_cache(f"off_{match_id}") if match_id else None