"""
main.py
Boucle principale + analyse groupée.
"""

import math

from interactive import (
    load_leagues, ask_date, choose_match_mode,
)
from match_catalog import build_match_catalog
from team_history import get_cached_team_full, get_team_full
from data_cleaner import (
    extract_lambdas_api, extract_api_probabilities, extract_match_info,
)
from recent_form import compute_lambdas_blended
from poisson_model import analyze_with_lambdas
from markets import compute_all_markets
from markets_extended import (
    market_first_scorer, market_ht_1x2, market_ht_total_buts,
    market_score_exact_ht, market_cards, market_corners,
)
from explainer import generate_all_explanations
from report import print_report
from adjustments import adjust_lambdas
from live_football_client import (
    find_match as lf_find,
    get_cached_injuries,
    get_cached_officials,
    get_injuries,
    get_matches_for_date as get_live_matches_for_date,
    get_officials,
)


DEBUG = False


def _timing_summary(team_data):
    counts = {}
    for entry in (team_data or {}).get("first_goal_bins", []):
        if isinstance(entry, dict) and entry.get("time") != "No Goal":
            try:
                counts[entry["time"]] = counts.get(entry["time"], 0) + int(entry.get("count", 0))
            except (TypeError, ValueError):
                continue
    total = sum(counts.values())
    if total <= 0:
        return {"available": False, "events": 0, "intervals": []}
    return {
        "available": True,
        "events": total,
        "intervals": [
            {"interval": name, "count": count, "probability": count / total}
            for name, count in counts.items()
        ],
    }


def log_succes(msg): print(f"   ✅ {msg}")
def log_erreur(msg): print(f"   ❌ {msg}")


def analyze_match_data(lk, match, *, cached_only=False):
    """Calculate one match and return JSON-friendly report sections."""
    mi = extract_match_info(match)
    team_loader = get_cached_team_full if cached_only else get_team_full
    td = team_loader(lk, mi["home_team"])
    te = team_loader(lk, mi["away_team"])
    if not td or not te:
        raise ValueError("Profils équipe absents du cache ou de la source statistique.")

    lam = compute_lambdas_blended(td, te)
    if not lam["lambda_dom"] or not lam["lambda_ext"]:
        lam = extract_lambdas_api(match)
    if not lam["lambda_dom"] or not lam["lambda_ext"]:
        raise ValueError(
            "Les statistiques nécessaires pour ces deux équipes sont indisponibles."
        )

    injuries_dom, injuries_ext, officials = [], [], None
    match_id = match.get("source_match_id")
    if cached_only:
        inj = get_cached_injuries(match_id) or {}
        injuries_dom = inj.get("home", [])
        injuries_ext = inj.get("away", [])
        officials = get_cached_officials(match_id)
    else:
        try:
            mid_lf = lf_find(mi["home_team"], mi["away_team"], mi["date"])
            if mid_lf:
                inj = get_injuries(mid_lf) or {}
                injuries_dom = inj.get("home", [])
                injuries_ext = inj.get("away", [])
                officials = get_officials(mid_lf)
        except Exception:
            pass

    adj = adjust_lambdas(
        lam["lambda_dom"], lam["lambda_ext"], injuries_dom, injuries_ext
    )
    lambda_dom = adj["lambda_dom_adj"]
    lambda_ext = adj["lambda_ext_adj"]
    analysis = analyze_with_lambdas(lambda_dom, lambda_ext, use_dixon_coles=True)
    markets = compute_all_markets(analysis["matrix"], lambda_dom, lambda_ext)

    half_time_basis = "football_charts_model"
    try:
        raw = match["model_predictions"]["dc_v2"]["raw"]
        half_total = float(raw.get("expected_ht_goals", 0))
    except (KeyError, TypeError, ValueError):
        half_total = 0
    if half_total > 0:
        home_ratio = lambda_dom / (lambda_dom + lambda_ext)
        lambda_ht_dom = half_total * home_ratio
        lambda_ht_ext = half_total * (1 - home_ratio)
    else:
        half_time_basis = "estimated_from_full_match_lambdas"
        lambda_ht_dom = lambda_dom * 0.40
        lambda_ht_ext = lambda_ext * 0.40

    extended = {
        "ht_1x2": market_ht_1x2(lambda_ht_dom, lambda_ht_ext),
        "ht_total_buts": market_ht_total_buts(lambda_ht_dom, lambda_ht_ext),
        "second_half_1x2": market_ht_1x2(
            max(lambda_dom - lambda_ht_dom, 0.05),
            max(lambda_ext - lambda_ht_ext, 0.05),
        ),
        "second_half_total_buts": market_ht_total_buts(
            max(lambda_dom - lambda_ht_dom, 0.05),
            max(lambda_ext - lambda_ht_ext, 0.05),
        ),
        "team_to_score_both_halves": {
            "dom": (1 - math.exp(-lambda_ht_dom))
            * (1 - math.exp(-max(lambda_dom - lambda_ht_dom, 0.05))),
            "ext": (1 - math.exp(-lambda_ht_ext))
            * (1 - math.exp(-max(lambda_ext - lambda_ht_ext, 0.05))),
        },
        "first_scorer": market_first_scorer(lambda_dom, lambda_ext),
        "score_exact_ht": market_score_exact_ht(lambda_ht_dom, lambda_ht_ext),
        "cards": market_cards(officials),
        "corners": market_corners(td, te),
    }
    extended["goals_by_period"] = {
        "first_half_expected_goals": round(lambda_ht_dom + lambda_ht_ext, 4),
        "second_half_expected_goals": round(
            max(lambda_dom + lambda_ext - lambda_ht_dom - lambda_ht_ext, 0), 4
        ),
        "first_half_score_exact": market_score_exact_ht(
            lambda_ht_dom, lambda_ht_ext, top=9
        ),
        "second_half_score_exact": market_score_exact_ht(
            max(lambda_dom - lambda_ht_dom, 0.05),
            max(lambda_ext - lambda_ht_ext, 0.05),
            top=9,
        ),
    }
    timing = {
        "home": _timing_summary(td),
        "away": _timing_summary(te),
    }
    timing_events = sum(
        item["events"] for item in timing.values() if item["available"]
    )
    timing_counts = {}
    for team_timing in timing.values():
        for item in team_timing["intervals"]:
            timing_counts[item["interval"]] = (
                timing_counts.get(item["interval"], 0) + item["count"]
            )
    timing["combined"] = {
        "available": timing_events > 0,
        "events": timing_events,
        "intervals": [
            {
                "interval": interval,
                "count": count,
                "probability": count / timing_events,
            }
            for interval, count in timing_counts.items()
        ] if timing_events else [],
    }
    played_counts = [
        value for value in ((td or {}).get("played"), (te or {}).get("played"))
        if value is not None
    ]
    minimum_history = min(played_counts) if played_counts else 0
    both_xg_available = bool(
        (td or {}).get("xg_avg") is not None
        and (te or {}).get("xg_avg") is not None
    )
    data_quality = {
        "label": "limited" if minimum_history < 8 or not both_xg_available else "usable",
        "minimum_team_matches": minimum_history,
        "both_teams_have_xg": both_xg_available,
        "note": (
            "Historique court et/ou xG manquants; les moyennes de buts de repli pèsent davantage."
            if minimum_history < 8 or not both_xg_available
            else "Historique et xG disponibles; cela ne constitue pas une validation prédictive."
        ),
    }
    penalty_score = match.get("penalty_score")
    explanations = generate_all_explanations(
        markets, mi, lambda_dom, lambda_ext
    )

    def team_summary(team_data):
        if not team_data:
            return None
        return {
            "team": team_data.get("team"),
            "form": team_data.get("forme_str"),
            "xg": team_data.get("xg_avg"),
            "xg_against": team_data.get("xg_against_avg"),
            "position": team_data.get("position"),
            "points": team_data.get("points"),
            "recent_matches": team_data.get("forme_lignes", []),
        }

    return {
        "match": mi,
        "lambda_home": lambda_dom,
        "lambda_away": lambda_ext,
        "model": {
            "name": "Poisson avec correction Dixon-Coles",
            "half_time_basis": half_time_basis,
            "team_history_matches": {
                "home": (td or {}).get("played"),
                "away": (te or {}).get("played"),
            },
            "xg_available": {
                "home": (td or {}).get("xg_avg") is not None,
                "away": (te or {}).get("xg_avg") is not None,
            },
            "penalty_model": False,
        },
        "markets": markets,
        "extended": extended,
        "goal_timing": timing,
        "data_quality": data_quality,
        "penalties": {
            "known_event_score": penalty_score,
            "prediction": None,
            "availability": (
                "observed_for_completed_match" if penalty_score
                else "no_reliable_history_available"
            ),
        },
        "explanations": explanations,
        "teams": {
            "home": team_summary(td),
            "away": team_summary(te),
        },
        "_team_data": {"home": td, "away": te},
        "adjustments": adj,
        "officials": officials,
        "api_probabilities": extract_api_probabilities(match),
        "cache_only": cached_only,
        "data_sources": {
            "team_profiles": "local_cache" if cached_only else "football_charts",
            "injuries": "local_cache" if cached_only and injuries_dom + injuries_ext else "unavailable" if cached_only else "live_football",
            "officials": "local_cache" if cached_only and officials else "unavailable" if cached_only else "live_football",
            "additional_api_requests": 0 if cached_only else None,
        },
    }


def analyze_match_cached(lk, match):
    """Analyze from local team/incident caches only; never make network calls."""
    try:
        return analyze_match_data(lk, match, cached_only=True)
    except Exception:
        return None


def analyze_one_match(lk, match, show_recent=True):
    """Analyse UN match et affiche le rapport historique du terminal."""
    try:
        data = analyze_match_data(lk, match)
        print_report(
            data["match"],
            {
                "lambda_dom": data["lambda_home"],
                "lambda_ext": data["lambda_away"],
            },
            None,
            data["markets"],
            None,
            data["explanations"],
            data["api_probabilities"],
            data["_team_data"]["home"],
            data["_team_data"]["away"],
            extended=data["extended"],
            adjustments=data["adjustments"],
            officials=data["officials"],
            show_recent=show_recent,
        )
        return True
    except Exception as exc:
        log_erreur(
            f"Erreur analyse {match.get('home_team')} vs "
            f"{match.get('away_team')} : {exc}"
        )
        return False


def main_loop():
    """Browse the global daily schedule and analyze one selected match."""
    print("\n" + "=" * 60)
    print("   🧠 ANALYSE FOOTBALL — MOTEUR POISSON")
    print("=" * 60)

    while True:
        try:
            leagues = load_leagues()
            date = ask_date()
            if date is None:
                print("\n👋 À bientôt !\n")
                break

            print(f"\n🔍 Chargement du calendrier mondial pour le {date}...")
            events = get_live_matches_for_date(date)

            if events is None:
                print("\n   ❌ Calendrier indisponible. Vérifie la connexion et la clé Live Football API.")
                input("\n   ⏎ Appuie sur Entrée pour revenir à l'accueil...")
                continue

            matchs = build_match_catalog(events, date, leagues)
            if not matchs:
                print(f"\n   ❌ Aucun match trouvé le {date}")
                input("\n   ⏎ Appuie sur Entrée pour revenir à l'accueil...")
                continue

            selected = choose_match_mode(matchs)
            if selected is None:
                continue

            print(f"\n✅ Ligue statistique associée : {selected['analysis_league_key']}")
            analyze_one_match(
                selected["analysis_league_key"],
                selected,
                show_recent=True,
            )

            input("\n   ⏎ Appuie sur Entrée pour revenir à l'accueil...")

        except KeyboardInterrupt:
            print("\n\n👋 Interruption. À bientôt !\n")
            break
        except Exception as e:
            print(f"\n❌ Erreur : {e}")
            input("\n   ⏎ Appuie sur Entrée pour continuer...")


if __name__ == "__main__":
    from web_app import serve

    serve()