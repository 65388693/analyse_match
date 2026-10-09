"""
adjustments.py
Ajustement des λ selon les blessures — pondération douce.
"""

# Impact par position (une seule blessure)
IMPACT = {
    "GK": {"att_loss": 0.00, "def_weak": 0.08},
    "DF": {"att_loss": 0.00, "def_weak": 0.05},  # réduit (5% au lieu de 10%)
    "MF": {"att_loss": 0.06, "def_weak": 0.04},
    "FW": {"att_loss": 0.12, "def_weak": 0.00},
}


def _parse_position(pos: str) -> str:
    if not pos:
        return "MF"
    p = pos.upper()
    if "GK" in p or "GOAL" in p or "GARDIEN" in p:
        return "GK"
    if "DF" in p or "DEF" in p or "DEFEN" in p:
        return "DF"
    if "FW" in p or "ATT" in p or "FORWARD" in p:
        return "FW"
    return "MF"


def adjust_lambdas(lambda_dom: float, lambda_ext: float,
                   injuries_dom: list, injuries_ext: list) -> dict:
    """
    Ajustement DOUX : utilise une décroissance exponentielle par blessure
    pour éviter que 5 blessures = +50%.
    """
    def cumulative_impact(injuries):
        att_loss = 0.0
        def_weak = 0.0
        for i, player in enumerate(injuries or []):
            pos = _parse_position(player.get("position", ""))
            impact = IMPACT.get(pos, {"att_loss": 0.03, "def_weak": 0.02})
            # Pondération : 1er joueur = 100%, 2e = 70%, 3e = 50%, 4e = 35%...
            weight = 0.7 ** i
            att_loss += impact["att_loss"] * weight
            def_weak += impact["def_weak"] * weight
        return att_loss, def_weak

    dom_att, dom_def = cumulative_impact(injuries_dom)
    ext_att, ext_def = cumulative_impact(injuries_ext)

    # Plafonne à 30%
    dom_att = min(dom_att, 0.30)
    dom_def = min(dom_def, 0.30)
    ext_att = min(ext_att, 0.30)
    ext_def = min(ext_def, 0.30)

    lambda_dom_adj = lambda_dom * (1 - dom_att) * (1 + ext_def)
    lambda_ext_adj = lambda_ext * (1 - ext_att) * (1 + dom_def)

    details = {"dom": [], "ext": []}
    for inj_list, side in [(injuries_dom or [], "dom"), (injuries_ext or [], "ext")]:
        for i, player in enumerate(inj_list):
            pos = _parse_position(player.get("position", ""))
            impact = IMPACT.get(pos, {"att_loss": 0.03, "def_weak": 0.02})
            weight = 0.7 ** i
            details[side].append({
                "name": player.get("player", player.get("name", "?")),
                "position": pos,
                "att_loss": impact["att_loss"] * weight,
                "def_weak": impact["def_weak"] * weight,
                "weight": weight,
            })

    return {
        "lambda_dom_adj": round(max(lambda_dom_adj, 0.15), 4),
        "lambda_ext_adj": round(max(lambda_ext_adj, 0.15), 4),
        "lambda_dom_orig": round(lambda_dom, 4),
        "lambda_ext_orig": round(lambda_ext, 4),
        "dom_att_loss": round(dom_att, 4),
        "dom_def_weak": round(dom_def, 4),
        "ext_att_loss": round(ext_att, 4),
        "ext_def_weak": round(ext_def, 4),
        "blessures": details,
    }