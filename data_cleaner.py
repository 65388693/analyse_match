"""
data_cleaner.py
Extraction des données API.
"""


def _unwrap(data):
    if isinstance(data, dict) and "structuredContent" in data:
        return data["structuredContent"]
    return data


def _parse_score(score_str):
    if not score_str or not isinstance(score_str, str) or ":" not in score_str:
        return None, None
    try:
        h, a = score_str.split(":")
        return int(h), int(a)
    except ValueError:
        return None, None


def extract_lambdas_api(match):
    try:
        raw = match["model_predictions"]["dc_v2"]["raw"]
        return {
            "lambda_dom": float(raw["expected_home_goals"]),
            "lambda_ext": float(raw["expected_away_goals"]),
        }
    except (KeyError, TypeError):
        return {"lambda_dom": None, "lambda_ext": None}


def extract_api_probabilities(match):
    try:
        cal = match["model_predictions"]["dc_v2"]["calibrated"]
        raw = match["model_predictions"]["dc_v2"]["raw"]
        return {
            "1X2": {
                "dom": float(cal.get("home", raw.get("home", 0))),
                "nul": 1 - float(cal.get("home", 0)) - float(cal.get("away", 0)),
                "ext": float(cal.get("away", raw.get("away", 0))),
            },
            "total_buts": {
                "over_1_5": float(cal.get("over_1.5", raw.get("over_1.5", 0))),
                "over_2_5": float(cal.get("over_2.5", raw.get("over_2.5", 0))),
                "over_3_5": float(cal.get("over_3.5", raw.get("over_3.5", 0))),
            },
            "btts": {
                "oui": float(cal.get("btts_yes", raw.get("btts_yes", 0))),
                "non": 1 - float(cal.get("btts_yes", raw.get("btts_yes", 0))),
            },
        }
    except (KeyError, TypeError):
        return None


def extract_match_info(match):
    return {
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "date": match.get("match_date"),
        "time": match.get("time"),
        "league": match.get("real_league_name"),
        "country": match.get("country"),
        "slug": match.get("slug"),
        "source_match_id": match.get("source_match_id"),
        "halftime_score": match.get("halftime_score"),
        "penalty_score": match.get("penalty_score"),
    }


def extract_team_data(team_data):
    sc = _unwrap(team_data)
    if not isinstance(sc, dict):
        return None
    stats = sc.get("stats")
    ranking = sc.get("ranking")
    matches = sc.get("matches")
    stats = stats if isinstance(stats, dict) else {}
    ranking = ranking if isinstance(ranking, dict) else {}
    matches = matches if isinstance(matches, list) else []
    team_name = str(sc.get("team") or "").strip().casefold()

    forme_lignes = []
    v, n, d = 0, 0, 0
    buts_marques, buts_encaisses = [], []

    for m in matches[-5:]:
        home = m.get("home", "")
        away = m.get("away", "")
        sh, sa = _parse_score(m.get("score"))
        outcome = m.get("outcome", "?")
        date = m.get("date", "?")
        if sh is None:
            continue
        if outcome == "W": v += 1
        elif outcome == "D": n += 1
        elif outcome == "L": d += 1
        venue = str(m.get("venue") or "").strip().upper()
        if venue in {"H", "HOME"}:
            buts_marques.append(sh)
            buts_encaisses.append(sa)
        elif venue in {"A", "AWAY"}:
            buts_marques.append(sa)
            buts_encaisses.append(sh)
        elif team_name == str(home).strip().casefold():
            buts_marques.append(sh)
            buts_encaisses.append(sa)
        elif team_name == str(away).strip().casefold():
            buts_marques.append(sa)
            buts_encaisses.append(sh)
        forme_lignes.append(f"{date}  {home} {sh}-{sa} {away}  [{outcome}]")

    nb = len(buts_marques)

    return {
        "team": sc.get("team", "?"),
        "matches": matches,   # ⚠️ important pour recent_form
        "xg_avg": stats.get("xg_avg"),
        "xg_against_avg": stats.get("xg_against_avg"),
        "corners_avg": stats.get("corners_avg"),
        "shots_avg": stats.get("shots_avg"),
        "possession_avg": stats.get("possession_avg"),
        "goal_bins": sc.get("goal_bins", []),
        "time_bins": sc.get("time_bins", []),
        "first_goal_bins": sc.get("first_goal_bins", []),
        "forme_str": f"{v}V-{n}N-{d}D",
        "forme_lignes": forme_lignes,
        "buts_marques_moy": round(sum(buts_marques)/nb, 2) if nb else 0,
        "buts_encaisses_moy": round(sum(buts_encaisses)/nb, 2) if nb else 0,
        "position": ranking.get("position"),
        "points": ranking.get("points"),
        "played": ranking.get("played"),
    }