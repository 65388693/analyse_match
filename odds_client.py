"""Odds API client for current football 1X2 prices."""

from datetime import datetime, timezone
import re
import threading
import time
import unicodedata

import requests

from config import ODDS_API_KEY

BASE_URL = "https://api.the-odds-api.com/v4"
REGION = "eu"
MARKET = "h2h"
SPORTS_TTL = 6 * 60 * 60
ODDS_TTL = 90

_cache_lock = threading.Lock()
_sports_cache = {"expires": 0.0, "data": None}
_odds_cache = {}
_sports_fetch_lock = threading.Lock()
_odds_fetch_locks = {}

LEAGUE_SPORT_ALIASES = {
    ("england", "premier league"): "soccer_epl",
    ("england", "english premier league"): "soccer_epl",
    ("england", "championship"): "soccer_efl_champ",
    ("spain", "laliga"): "soccer_spain_la_liga",
    ("spain", "la liga"): "soccer_spain_la_liga",
    ("spain", "laliga2"): "soccer_spain_segunda_division",
    ("spain", "segunda division"): "soccer_spain_segunda_division",
    ("france", "ligue 1"): "soccer_france_ligue_one",
    ("france", "ligue 2"): "soccer_france_ligue_two",
    ("germany", "bundesliga"): "soccer_germany_bundesliga",
    ("germany", "2 bundesliga"): "soccer_germany_bundesliga2",
    ("italy", "serie a"): "soccer_italy_serie_a",
    ("italy", "serie b"): "soccer_italy_serie_b",
    ("netherlands", "eredivisie"): "soccer_netherlands_eredivisie",
    ("portugal", "liga portugal"): "soccer_portugal_primeira_liga",
    ("portugal", "primeira liga"): "soccer_portugal_primeira_liga",
    ("brazil", "serie a"): "soccer_brazil_campeonato",
    ("brazil", "serie a betano"): "soccer_brazil_campeonato",
    ("argentina", "primera division"): "soccer_argentina_primera_division",
    ("usa", "mls"): "soccer_usa_mls",
    ("united states", "mls"): "soccer_usa_mls",
    ("australia", "a league"): "soccer_australia_aleague",
    ("japan", "j1 league"): "soccer_japan_j_league",
    ("turkey", "super lig"): "soccer_turkey_super_league",
    ("scotland", "premiership"): "soccer_spl",
    ("ireland", "premier division"): "soccer_league_of_ireland",
    ("belgium", "jupiler pro league"): "soccer_belgium_first_div",
    ("denmark", "superliga"): "soccer_denmark_superliga",
    ("norway", "eliteserien"): "soccer_norway_eliteserien",
    ("sweden", "allsvenskan"): "soccer_sweden_allsvenskan",
    ("finland", "veikkausliiga"): "soccer_finland_veikkausliiga",
    ("poland", "ekstraklasa"): "soccer_poland_ekstraklasa",
    ("russia", "premier league"): "soccer_russia_premier_league",
    ("saudi arabia", "saudi professional league"): "soccer_saudi_arabia_pro_league",
    ("mexico", "liga mx"): "soccer_mexico_ligamx",
    ("europe", "uefa champions league"): "soccer_uefa_champs_league",
    ("europe", "champions league"): "soccer_uefa_champs_league",
    ("europe", "uefa europa league"): "soccer_uefa_europa_league",
    ("europe", "europa league"): "soccer_uefa_europa_league",
    ("europe", "uefa conference league"): "soccer_uefa_europa_conference_league",
    ("europe", "conference league"): "soccer_uefa_europa_conference_league",
}


def _normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _team_key(value):
    tokens = _normalize(value).split()
    while tokens and tokens[-1] in {"fc", "cf", "sc", "afc", "fk", "club"}:
        tokens.pop()
    return " ".join(tokens)


def _team_matches(first, second):
    first_key = _team_key(first)
    second_key = _team_key(second)
    return bool(first_key and second_key and first_key == second_key)


def _api_get(path, params):
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            params={**params, "apiKey": ODDS_API_KEY},
            timeout=20,
        )
    except requests.RequestException:
        return None, "network_error"
    if response.status_code != 200:
        return None, response.status_code
    try:
        return response.json(), None
    except ValueError:
        return None, "invalid_json"


def _get_sports():
    now = time.monotonic()
    with _cache_lock:
        if _sports_cache["data"] is not None and _sports_cache["expires"] > now:
            return _sports_cache["data"], None

    with _sports_fetch_lock:
        now = time.monotonic()
        with _cache_lock:
            if _sports_cache["data"] is not None and _sports_cache["expires"] > now:
                return _sports_cache["data"], None

        data, error = _api_get("/sports", {})
        if error:
            return None, error
        sports = [
            item for item in data
            if isinstance(item, dict) and str(item.get("key", "")).startswith("soccer_")
        ] if isinstance(data, list) else []
        with _cache_lock:
            _sports_cache["data"] = sports
            _sports_cache["expires"] = time.monotonic() + SPORTS_TTL
        return sports, None


def _resolve_sport(match, sports):
    country = _normalize(match.get("country"))
    competition = _normalize(match.get("real_league_name"))
    key = LEAGUE_SPORT_ALIASES.get((country, competition))
    available = {sport.get("key"): sport for sport in sports}
    if key in available:
        return available[key]

    comp_tokens = set(competition.split()) - {"league", "division", "the", "football"}
    country_tokens = set(country.split()) - {"the"}
    ranked = []
    for sport in sports:
        searchable = " ".join((
            _normalize(sport.get("title")),
            _normalize(sport.get("description")),
            _normalize(sport.get("key")),
        ))
        score = sum(token in searchable.split() for token in comp_tokens)
        if competition and competition in searchable:
            score += 3
        if country_tokens and all(token in searchable.split() for token in country_tokens):
            score += 4
        if score:
            ranked.append((score, sport))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
        return ranked[0][1]
    return None


def _sport_odds(sport_key, force_refresh=False):
    now = time.monotonic()
    with _cache_lock:
        cached = _odds_cache.get(sport_key)
        if not force_refresh and cached and cached[0] > now:
            return cached[1], None
        fetch_lock = _odds_fetch_locks.setdefault(sport_key, threading.Lock())

    with fetch_lock:
        now = time.monotonic()
        with _cache_lock:
            cached = _odds_cache.get(sport_key)
            if cached and cached[0] > now:
                return cached[1], None

        data, error = _api_get(
            f"/sports/{sport_key}/odds",
            {"regions": REGION, "markets": MARKET, "oddsFormat": "decimal"},
        )
        if error:
            return None, error
        events = data if isinstance(data, list) else []
        with _cache_lock:
            _odds_cache[sport_key] = (time.monotonic() + ODDS_TTL, events)
        return events, None


def _event_matches(event, match):
    return (
        _team_matches(event.get("home_team"), match.get("home_team"))
        and _team_matches(event.get("away_team"), match.get("away_team"))
    )


def _event_date_distance(event, match_date):
    try:
        event_time = datetime.fromisoformat(
            str(event.get("commence_time", "")).replace("Z", "+00:00")
        )
        event_date = event_time.astimezone(timezone.utc).date()
        requested_date = datetime.strptime(match_date, "%Y-%m-%d").date()
        return abs((event_date - requested_date).days)
    except (TypeError, ValueError):
        return 99


def _extract_h2h(event):
    bookmakers = []
    best = {"home": None, "draw": None, "away": None}
    for bookmaker in event.get("bookmakers", []):
        market = next(
            (item for item in bookmaker.get("markets", []) if item.get("key") == "h2h"),
            None,
        )
        if not market:
            continue
        prices = {"home": None, "draw": None, "away": None}
        for outcome in market.get("outcomes", []):
            name = _normalize(outcome.get("name"))
            price = outcome.get("price")
            if not isinstance(price, (int, float)) or price <= 1:
                continue
            if _team_matches(name, event.get("home_team")):
                prices["home"] = float(price)
            elif _team_matches(name, event.get("away_team")):
                prices["away"] = float(price)
            elif name in {"draw", "tie", "the draw", "empate"}:
                prices["draw"] = float(price)
        if any(value is not None for value in prices.values()):
            bookmakers.append({
                "key": bookmaker.get("key"),
                "name": bookmaker.get("title") or bookmaker.get("key"),
                **prices,
            })
            for side, price in prices.items():
                if price is not None and (best[side] is None or price > best[side]):
                    best[side] = price
    return bookmakers, best


def get_match_odds(match, force_refresh=False):
    """Return current 1X2 odds for a fixture, without exposing the API key."""
    if not ODDS_API_KEY:
        return {"available": False, "reason": "Odds API non configurée."}

    sports, error = _get_sports()
    if error:
        reason = "Clé Odds API refusée." if error == 401 else (
            "Limite de requêtes Odds API atteinte." if error == 429
            else "Odds API temporairement indisponible."
        )
        return {"available": False, "reason": reason}

    sport = _resolve_sport(match, sports)
    if not sport:
        return {"available": False, "reason": "Compétition non couverte par Odds API."}

    events, error = _sport_odds(sport["key"], force_refresh=force_refresh)
    if error:
        reason = "Clé Odds API refusée." if error == 401 else (
            "Limite de requêtes Odds API atteinte." if error == 429
            else "Odds API temporairement indisponible."
        )
        return {"available": False, "reason": reason}

    candidates = [event for event in events if _event_matches(event, match)]
    candidates = [
        event for event in candidates
        if _event_date_distance(event, match.get("match_date", "")) <= 1
    ]
    if not candidates:
        return {"available": False, "reason": "Aucune cote actuelle trouvée pour ce match."}

    event = min(candidates, key=lambda item: _event_date_distance(item, match["match_date"]))
    bookmakers, best = _extract_h2h(event)
    if not bookmakers:
        return {"available": False, "reason": "Les bookmakers ne proposent pas de cote 1X2 pour ce match."}

    return {
        "available": True,
        "sport": sport.get("title") or sport.get("key"),
        "event": {
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "commence_time": event.get("commence_time"),
        },
        "best": best,
        "bookmakers": bookmakers,
    }
