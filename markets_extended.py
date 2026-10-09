"""
markets_extended.py
Marchés étendus avec fallback + plafonds.
"""

from scipy.stats import poisson
from poisson_model import build_score_matrix, normalize_matrix


DEFAULT_CORNERS = 5.0
MAX_RED_PROBA = 0.12  # plafond 12%


def market_first_scorer(lambda_dom, lambda_ext):
    lam_total = lambda_dom + lambda_ext
    p_no_goal = poisson.pmf(0, lam_total)
    p_at_least_one = 1 - p_no_goal
    return {
        "dom": (lambda_dom / lam_total) * p_at_least_one,
        "ext": (lambda_ext / lam_total) * p_at_least_one,
        "no_goal": p_no_goal,
    }


def market_ht_1x2(lam_ht_dom, lam_ht_ext):
    from markets import market_1x2
    matrix = normalize_matrix(build_score_matrix(lam_ht_dom, lam_ht_ext))
    return market_1x2(matrix)


def market_ht_total_buts(lam_ht_dom, lam_ht_ext):
    lam_total = lam_ht_dom + lam_ht_ext
    return {
        "ht_over_0_5": 1 - poisson.pmf(0, lam_total),
        "ht_over_1_5": 1 - poisson.cdf(1, lam_total),
        "ht_over_2_5": 1 - poisson.cdf(2, lam_total),
    }


def market_score_exact_ht(lam_ht_dom, lam_ht_ext, top=5):
    matrix = normalize_matrix(build_score_matrix(lam_ht_dom, lam_ht_ext))
    scores = []
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            scores.append({"score": f"{i}-{j}", "prob": matrix[i][j]})
    scores.sort(key=lambda x: x["prob"], reverse=True)
    return scores[:top]


def market_cards(officials):
    """Cartons avec plafond sur le rouge."""
    if not officials:
        return {}
    yc = officials.get("avg_yellow_cards") or 4.0
    rc = min(officials.get("avg_red_cards") or 0.20, 0.15)  # cap à 0.15

    result = {}
    for ligne in (2.5, 3.5, 4.5, 5.5, 6.5):
        result[f"yellow_over_{str(ligne).replace('.', '_')}"] = 1 - poisson.cdf(int(ligne), yc)

    red_yes = min(1 - poisson.pmf(0, rc), MAX_RED_PROBA)
    result["red_yes"] = red_yes
    result["red_no"] = 1 - red_yes
    result["source"] = (
        "referee_average"
        if officials.get("name") not in (None, "Non désigné")
        else "generic_fallback"
    )
    return result


def market_corners(team_dom_data, team_ext_data):
    """Corners avec FALLBACK sur moyenne de ligue."""
    if not team_dom_data or not team_ext_data:
        return {}

    c_dom = team_dom_data.get("corners_avg") or DEFAULT_CORNERS
    c_ext = team_ext_data.get("corners_avg") or DEFAULT_CORNERS
    total = c_dom + c_ext
    if total <= 0:
        total = DEFAULT_CORNERS * 2

    result = {
        "corners_dom": c_dom,
        "corners_ext": c_ext,
        "corners_total": total,
        "source": "team_average" if (
            team_dom_data.get("corners_avg") is not None
            and team_ext_data.get("corners_avg") is not None
        ) else "generic_fallback",
    }
    for ligne in (7.5, 8.5, 9.5, 10.5, 11.5):
        key = str(ligne).replace(".", "_")
        under = poisson.cdf(int(ligne), total)
        result[f"over_{key}"] = 1 - under
        result[f"under_{key}"] = under
    return result


def debug_model(lambda_dom, lambda_ext, matrix, markets, extended=None):
    print("\n" + "=" * 60)
    print("   🔍 MODEL DEBUG")
    print("=" * 60)
    print(f"\n   λ_dom = {lambda_dom:.6f}  |  λ_ext = {lambda_ext:.6f}")
    print(f"   λ_total = {lambda_dom + lambda_ext:.6f}")

    total = sum(sum(row) for row in matrix)
    ok = "✅" if abs(total - 1) < 1e-9 else "❌"
    print(f"   Checksum matrice : {total:.9f}  {ok}")

    m1x2 = markets["1X2"]
    print(f"\n   1X2 : {m1x2['dom']*100:.2f}% / {m1x2['nul']*100:.2f}% / {m1x2['ext']*100:.2f}%")

    print(f"   Top scores :")
    for s in markets["score_exact"][:3]:
        print(f"      {s['score']} : {s['prob']*100:.2f}%")

    print("=" * 60 + "\n")