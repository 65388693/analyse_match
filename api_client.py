"""
api_client.py
Récupération des données depuis footballcharts-mcp.
"""

import os
import re
import json
import requests
from config import FC_API_KEY, MCP_BASE, CACHE_DIR


# ============================================================
# FONCTION CENTRALE
# ============================================================

def call_mcp(tool_name: str, arguments: dict = None) -> dict:
    """Appelle un outil du serveur MCP footballcharts."""
    if not FC_API_KEY:
        raise RuntimeError("FC_API_KEY manquante dans l'environnement")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {FC_API_KEY}",
    }

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments or {}},
        "id": 1,
    }

    r = requests.post(MCP_BASE, json=payload, headers=headers, stream=True, timeout=60)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code}: {r.text[:500]}")

    for line in r.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    raise Exception(f"MCP Error: {data['error']}")
            except json.JSONDecodeError:
                continue
    raise Exception("Pas de réponse valide du serveur MCP")


# ============================================================
# CACHE LOCAL
# ============================================================

def _cache_path(key: str) -> str:
    r"""
    Convertit une clé en nom de fichier sûr pour Windows.
    Supprime les caractères interdits.
    """
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', key)
    safe = re.sub(r'_+', '_', safe).strip('_')[:150]
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _load_cache(key: str):
    path = _cache_path(key)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(key: str, data):
    path = _cache_path(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cached_call(tool_name: str, arguments: dict = None, cache_key: str = None):
    key = cache_key or f"{tool_name}_{json.dumps(arguments or {}, sort_keys=True)}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    result = call_mcp(tool_name, arguments)
    _save_cache(key, result)
    return result


# ============================================================
# FONCTIONS API
# ============================================================

def list_leagues():
    return cached_call("list_leagues")


def refresh_leagues():
    """Fetch the current league catalog once, reusing the persistent cache."""
    return cached_call("list_leagues", cache_key="list_leagues")


def get_fixtures(league: str):
    return cached_call("get_fixtures", {"league": league},
                       cache_key=f"fixtures_{league}")


def get_match(match_slug: str):
    return cached_call("get_match", {"slug": match_slug},
                       cache_key=f"match_{match_slug}")


def get_team(league: str, team: str):
    return cached_call("get_team", {"league": league, "team": team},
                       cache_key=f"team_{league}_{team}")


def get_cached_team(league: str, team: str):
    """Return team data only when present in the local cache; never call APIs."""
    return _load_cache(f"team_{league}_{team}")


def get_goal_timing(league: str, team: str = None):
    args = {"league": league}
    if team:
        args["team"] = team
    return cached_call("get_goal_timing", args,
                       cache_key=f"timing_{league}_{team or 'all'}")


def get_results_for_team(league: str, team: str, last: int = 5):
    """
    Récupère les N derniers matchs d'une équipe.
    """
    return cached_call("get_results",
                       {"league": league, "team": team, "last": last},
                       cache_key=f"results_{league}_{team}_{last}")