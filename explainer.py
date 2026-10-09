"""
explainer.py
Génération du "POURQUOI" pour chaque marché.
"""


def explain_1x2(market, match_info, lambda_dom, lambda_ext):
    dom = match_info["home_team"]
    ext = match_info["away_team"]

    if market["dom"] > market["ext"] and market["dom"] > market["nul"]:
        return (
            f"{dom} part favori ({market['dom']*100:.1f}%). "
            f"λ attendus : {dom} {lambda_dom} buts — {ext} {lambda_ext} buts."
        )
    elif market["ext"] > market["dom"] and market["ext"] > market["nul"]:
        return (
            f"{ext} part favori malgré l'extérieur ({market['ext']*100:.1f}%). "
            f"λ attendus : {dom} {lambda_dom} — {ext} {lambda_ext}."
        )
    return (
        f"Match équilibré — nul à {market['nul']*100:.1f}%. "
        f"λ proches : {dom} {lambda_dom} vs {ext} {lambda_ext}."
    )


def explain_total_buts(market, lambda_dom, lambda_ext):
    total = lambda_dom + lambda_ext
    over25 = market.get("over_2_5", 0)
    if over25 > 0.55:
        return f"Match à buts attendu — Over 2.5 à {over25*100:.1f}%. Total λ = {total:.2f}."
    if over25 < 0.45:
        return f"Match fermé attendu — Under 2.5 favori. Total λ = {total:.2f}."
    return f"Total de buts incertain (λ total = {total:.2f})."


def explain_btts(market):
    oui = market["oui"]
    if oui > 0.6:
        return f"Les deux équipes devraient marquer ({oui*100:.1f}%)."
    if oui < 0.4:
        return f"BTTS peu probable ({oui*100:.1f}%)."
    return f"BTTS incertain ({oui*100:.1f}%)."


def generate_all_explanations(markets, match_info, lambda_dom, lambda_ext) -> dict:
    return {
        "1X2": explain_1x2(markets["1X2"], match_info, lambda_dom, lambda_ext),
        "total_buts": explain_total_buts(markets["total_buts"], lambda_dom, lambda_ext),
        "btts": explain_btts(markets["btts"]),
    }