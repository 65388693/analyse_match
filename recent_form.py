"""
recent_form.py
Forme pondérée + fallback pour équipes sans données.
"""

# Moyennes de ligue par défaut (fallback)
DEFAULT_XG = 1.35
DEFAULT_XGA = 1.35
DEFAULT_CORNERS = 5.0
DEFAULT_SHOTS = 12.0
DEFAULT_POSSESSION = 50.0


def _parse_score(score_str):
    if not score_str or not isinstance(score_str, str) or ":" not in score_str:
        return None, None
    try:
        h, a = score_str.split(":")
        return int(h), int(a)
    except ValueError:
        return None, None


def compute_weighted_form(matches: list, team: str, n: int = 5,
                          decay: float = 0.85) -> dict:
    """Forme pondérée + séparation dom/ext."""
    team_low = team.lower()
    recent = matches[-n:][::-1]

    dom_m, dom_e, ext_m, ext_e = [], [], [], []
    dom_w, ext_w = [], []

    for i, m in enumerate(recent):
        w = decay ** i
        home = (m.get("home") or "").lower()
        away = (m.get("away") or "").lower()
        sh, sa = _parse_score(m.get("score"))
        if sh is None:
            continue
        if team_low in home:
            dom_m.append(sh); dom_e.append(sa); dom_w.append(w)
        elif team_low in away:
            ext_m.append(sa); ext_e.append(sh); ext_w.append(w)

    def wavg(vals, weights):
        if not vals or not weights or sum(weights) == 0:
            return None
        return sum(v * w for v, w in zip(vals, weights)) / sum(weights)

    return {
        "bm_dom_w": wavg(dom_m, dom_w),
        "be_dom_w": wavg(dom_e, dom_w),
        "bm_ext_w": wavg(ext_m, ext_w),
        "be_ext_w": wavg(ext_e, ext_w),
        "nb_dom": len(dom_m),
        "nb_ext": len(ext_m),
    }


def compute_lambdas_blended(team_dom_data, team_ext_data,
                             decay=0.85, weight_xg=0.6,
                             weight_form=0.4, home_advantage=1.10):
    """λ blended avec FALLBACK sur moyennes de ligue."""
    if not team_dom_data or not team_ext_data:
        return {"lambda_dom": None, "lambda_ext": None}

    # --- Récupération avec fallback ---
    xg_dom = team_dom_data.get("xg_avg") or DEFAULT_XG
    xga_dom = team_dom_data.get("xg_against_avg") or DEFAULT_XGA
    xg_ext = team_ext_data.get("xg_avg") or DEFAULT_XG
    xga_ext = team_ext_data.get("xg_against_avg") or DEFAULT_XGA

    form_dom = compute_weighted_form(team_dom_data.get("matches", []),
                                      team_dom_data.get("team", ""), decay=decay)
    form_ext = compute_weighted_form(team_ext_data.get("matches", []),
                                      team_ext_data.get("team", ""), decay=decay)

    # --- Attaque dom ---
    att_dom = weight_xg * xg_dom
    att_dom += weight_form * (form_dom["bm_dom_w"]
                              if form_dom["bm_dom_w"] is not None
                              else team_dom_data.get("buts_marques_moy") or DEFAULT_XG)

    # --- Défense ext ---
    def_ext = weight_xg * xga_ext
    def_ext += weight_form * (form_ext["be_ext_w"]
                              if form_ext["be_ext_w"] is not None
                              else team_ext_data.get("buts_encaisses_moy") or DEFAULT_XGA)

    lambda_dom = max((att_dom + def_ext) / 2 * home_advantage, 0.15)

    # --- Attaque ext ---
    att_ext = weight_xg * xg_ext
    att_ext += weight_form * (form_ext["bm_ext_w"]
                              if form_ext["bm_ext_w"] is not None
                              else team_ext_data.get("buts_marques_moy") or DEFAULT_XG)

    # --- Défense dom ---
    def_dom = weight_xg * xga_dom
    def_dom += weight_form * (form_dom["be_dom_w"]
                              if form_dom["be_dom_w"] is not None
                              else team_dom_data.get("buts_encaisses_moy") or DEFAULT_XGA)

    lambda_ext = max((att_ext + def_dom) / 2, 0.15)

    return {
        "lambda_dom": round(lambda_dom, 4),
        "lambda_ext": round(lambda_ext, 4),
        "detail": {
            "att_dom": round(att_dom, 4),
            "def_ext": round(def_ext, 4),
            "att_ext": round(att_ext, 4),
            "def_dom": round(def_dom, 4),
            "form_dom": form_dom,
            "form_ext": form_ext,
            "fallback_dom": team_dom_data.get("xg_avg") is None,
            "fallback_ext": team_ext_data.get("xg_avg") is None,
        }
    }