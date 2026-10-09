"""Normalize global match events and link supported competitions."""

import json
import re
import unicodedata

from api_client import _load_cache

LEAGUE_ALIASES = {
    ("england", "english premier league"): "premier",
    ("england", "premier league"): "premier",
    ("spain", "la liga"): "spain1",
    ("spain", "primera division"): "spain1",
    ("spain", "segunda division"): "spain2",
    ("brazil", "serie a"): "brazil1",
}


def _normalize_label(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _find_analysis_league(country, competition, leagues):
    country_key = _normalize_label(country)
    competition_key = _normalize_label(competition)

    if not country_key or not competition_key:
        return None

    alias = LEAGUE_ALIASES.get((country_key, competition_key))
    if alias:
        return alias

    matches = [
        league
        for league in leagues
        if _normalize_label(league.get("country")) == country_key
        and _normalize_label(league.get("name")) == competition_key
    ]
    if len(matches) == 1:
        return matches[0].get("league")

    discovered = _extract_provider_leagues(_load_cache("list_leagues"))
    matches = [
        league
        for league in discovered
        if _normalize_label(league.get("country")) == country_key
        and _normalize_label(league.get("name")) == competition_key
    ]
    if len(matches) == 1:
        return matches[0].get("league") or matches[0].get("id")
    return None


def _extract_provider_leagues(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    structured = payload.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("leagues", "competitions", "data"):
            if isinstance(structured.get(key), list):
                return structured[key]
    for item in payload.get("content", []):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        try:
            parsed = json.loads(item["text"])
        except ValueError:
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("leagues", "competitions", "data"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
    for key in ("leagues", "competitions", "data"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def build_match_catalog(events, date, leagues):
    """Convert provider events into analysis-shaped records for one date."""
    catalog = []

    for event in events or []:
        league = event.get("league") or {}
        home = event.get("home") or {}
        away = event.get("away") or {}
        status = event.get("status") or {}
        halftime = event.get("halftime") or {}
        penalties = event.get("penalty") or {}
        home_score = home.get("score")
        away_score = away.get("score")
        competition = league.get("name")
        country = league.get("country")

        catalog.append({
            "home_team": home.get("name") or "Équipe inconnue",
            "away_team": away.get("name") or "Équipe inconnue",
            "match_date": date,
            "time": event.get("kickoff") or status.get("display") or "Heure inconnue",
            "real_league_name": competition or "Compétition inconnue",
            "country": country or "Pays inconnu",
            "analysis_league_key": _find_analysis_league(
                country, competition, leagues
            ),
            "source_match_id": event.get("id"),
            "status": status.get("status") or "scheduled",
            "status_display": status.get("display") or "",
            "is_live": bool(status.get("is_live")),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),
            "score": (
                f"{home_score}-{away_score}"
                if home_score is not None and away_score is not None
                else None
            ),
            "halftime_score": (
                f"{halftime['home']}-{halftime['away']}"
                if halftime.get("home") is not None and halftime.get("away") is not None
                else None
            ),
            "penalty_score": (
                f"{penalties['home']}-{penalties['away']}"
                if penalties.get("home") is not None and penalties.get("away") is not None
                else None
            ),
        })

    return sorted(
        catalog,
        key=lambda match: (
            _normalize_label(match["country"]),
            _normalize_label(match["real_league_name"]),
            match["time"],
            _normalize_label(match["home_team"]),
        ),
    )