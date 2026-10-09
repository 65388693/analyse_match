"""Build conservative daily football picks from cached models and 1xBet odds."""

from itertools import combinations
import math
import re

OUTCOMES = (
    ("dom", "1"),
    ("nul", "N"),
    ("ext", "2"),
)
MAX_CANDIDATES = 18
MAX_LEGS = 6
PICKS_PER_GROUP = 5
MODEL_VERSION = "poisson-dixon-coles-v1"

TIERS = {
    "prudent": {"label": "Prudents", "minimum_odds": 2.0, "maximum_odds": 10.0},
    "moyen": {"label": "Moyens", "minimum_odds": 10.0, "maximum_odds": 100.0},
    "grosse_cote": {"label": "Grosses cotes", "minimum_odds": 100.0, "maximum_odds": 5000.0},
}


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_1xbet(bookmaker):
    return "1xbet" in _normalized(bookmaker.get("key")) or "1xbet" in _normalized(
        bookmaker.get("name")
    )


def _one_x_bet_prices(odds):
    bookmaker = next(
        (item for item in odds.get("bookmakers", []) if _is_1xbet(item)),
        None,
    )
    if not bookmaker:
        return None
    return bookmaker


def _make_candidates(analysis, odds):
    match = analysis.get("match") or {}
    market = (analysis.get("markets") or {}).get("1X2") or {}
    bookmaker = _one_x_bet_prices(odds)
    if not bookmaker:
        return []

    home = str(match.get("home_team") or "").strip()
    away = str(match.get("away_team") or "").strip()
    match_id = str(match.get("source_match_id") or "")
    if not home or not away or not match_id:
        return []

    candidates = []
    for outcome_key, label in OUTCOMES:
        probability = market.get(outcome_key)
        price = bookmaker.get(outcome_key)
        if not isinstance(probability, (int, float)) or not 0 < probability < 1:
            continue
        if not isinstance(price, (int, float)) or not math.isfinite(float(price)) or price <= 1:
            price = None
        expected_return = probability * price - 1 if price is not None else None

        selected = home if outcome_key == "dom" else away if outcome_key == "ext" else "Match nul"
        candidates.append({
            "key": f"{match_id}:{outcome_key}",
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "teams": (home.casefold(), away.casefold()),
            "competition": match.get("league"),
            "country": match.get("country"),
            "label": f"{label} · {selected}",
            "selection": outcome_key,
            "odds": float(price) if price is not None else None,
            "probability": float(probability),
            "expected_return": expected_return,
            "data_quality": (analysis.get("data_quality") or {}).get("label", "limited"),
            "bookmaker": bookmaker.get("name") or bookmaker.get("key") or "1xBet",
        })
    return candidates


def _combo_key(legs):
    return tuple(sorted(leg["key"] for leg in legs))


def _build_combinations(candidates, tier, used_combinations):
    settings = TIERS[tier]
    combinations_found = []
    max_legs = min(MAX_LEGS, len(candidates))

    for leg_count in range(2, max_legs + 1):
        for legs in combinations(candidates, leg_count):
            key = _combo_key(legs)
            if key in used_combinations:
                continue

            teams = [team for leg in legs for team in leg["teams"]]
            match_ids = [leg["match_id"] for leg in legs]
            if len(set(teams)) != len(teams) or len(set(match_ids)) != len(match_ids):
                continue

            total_odds = 1.0
            combined_probability = 1.0
            for leg in legs:
                total_odds *= leg["odds"]
                combined_probability *= leg["probability"]
            if not settings["minimum_odds"] <= total_odds < settings["maximum_odds"]:
                continue

            combinations_found.append({
                "key": key,
                "legs": list(legs),
                "total_odds": total_odds,
                "estimated_probability": combined_probability,
                "expected_return": combined_probability * total_odds - 1,
                "independence_assumption": True,
            })

    combinations_found.sort(
        key=lambda item: (
            item["expected_return"],
            item["estimated_probability"],
            -item["total_odds"],
        ),
        reverse=True,
    )

    selected = combinations_found[:PICKS_PER_GROUP]
    used_combinations.update(item["key"] for item in selected)
    for item in selected:
        item.pop("key", None)
    return selected


def build_daily_picks(analyses_with_odds, *, skipped=None):
    """Create singles and three disjoint combo tiers from 1xBet-priced 1X2 picks."""
    observations = []
    candidates = []
    missing_1xbet = 0
    matches_with_1xbet = set()
    for analysis, odds in analyses_with_odds:
        bookmaker = _one_x_bet_prices(odds)
        if not bookmaker:
            missing_1xbet += 1
            continue
        match = analysis.get("match") or {}
        if match.get("source_match_id") is not None:
            matches_with_1xbet.add(str(match["source_match_id"]))
        match_candidates = _make_candidates(analysis, odds)
        observations.extend(match_candidates)
        candidates.extend(
            candidate for candidate in match_candidates
            if candidate["expected_return"] is not None
            and candidate["expected_return"] > 0
        )

    candidates.sort(
        key=lambda item: (
            item["expected_return"],
            item["probability"],
            item["odds"],
        ),
        reverse=True,
    )
    candidates = candidates[:MAX_CANDIDATES]
    combo_candidates = [
        candidate for candidate in candidates
        if candidate["data_quality"] == "usable"
    ]

    singles = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item["probability"], item["expected_return"]),
        reverse=True,
    )[:PICKS_PER_GROUP * 2]:
        singles.append({
            key: value for key, value in candidate.items()
            if key not in {"teams", "key"}
        })

    used_combinations = set()
    combo_groups = {
        tier: _build_combinations(combo_candidates, tier, used_combinations)
        for tier in ("prudent", "moyen", "grosse_cote")
    }

    return {
        "market_scope": "Résultat final 1X2 uniquement",
        "bookmaker": "1xBet",
        "singles": singles,
        "combos": combo_groups,
        "coverage": {
            "matches_with_1xbet_odds": len(matches_with_1xbet),
            "candidate_selections": len(candidates),
            "combo_eligible_selections": len(combo_candidates),
            "model_outcomes_recorded": len(observations),
            "matches_without_1xbet_odds": missing_1xbet,
            "skipped": skipped or {},
        },
        "method_note": (
            "Probabilités issues du modèle Poisson/Dixon-Coles non calibré sur un historique "
            "de paris 1xBet. La probabilité d'un combiné multiplie les probabilités des "
            "sélections et suppose des matchs indépendants; ce n'est pas une garantie ni "
            "une performance mesurée. Les combinés excluent les analyses à données limitées "
            "et les sélections partagent zéro équipe et zéro match."
        ),
        "empty_note": (
            "Aucune sélection 1xBet avec valeur estimée positive et données suffisantes. "
            "Ne pas forcer un pari quand le modèle et les cotes ne montrent pas d'écart."
        ),
        "_observations": observations,
    }
