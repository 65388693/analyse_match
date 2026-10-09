"""
markets.py
Tous les marchés dérivés de LA MÊME matrice de scores.
"""

from scipy.stats import poisson


def _sum(matrix, cond):
    return sum(matrix[i][j] for i in range(len(matrix))
               for j in range(len(matrix[i])) if cond(i, j))


# ============================================================
# 1X2
# ============================================================

def market_1x2(matrix):
    return {
        "dom": _sum(matrix, lambda i, j: i > j),
        "nul": _sum(matrix, lambda i, j: i == j),
        "ext": _sum(matrix, lambda i, j: i < j),
    }


def market_double_chance(matrix):
    m = market_1x2(matrix)
    return {
        "1X": m["dom"] + m["nul"],
        "12": m["dom"] + m["ext"],
        "X2": m["nul"] + m["ext"],
    }


def market_draw_no_bet(matrix):
    result = market_1x2(matrix)
    decisive = result["dom"] + result["ext"]
    if decisive <= 0:
        return {"dom": 0.5, "ext": 0.5}
    return {
        "dom": result["dom"] / decisive,
        "ext": result["ext"] / decisive,
    }


def market_total_parity(matrix):
    odd = _sum(matrix, lambda home, away: (home + away) % 2 == 1)
    return {"odd": odd, "even": 1 - odd}


def market_winning_margin(matrix):
    return {
        "dom_1": _sum(matrix, lambda home, away: home - away == 1),
        "dom_2": _sum(matrix, lambda home, away: home - away == 2),
        "dom_3_plus": _sum(matrix, lambda home, away: home - away >= 3),
        "ext_1": _sum(matrix, lambda home, away: away - home == 1),
        "ext_2": _sum(matrix, lambda home, away: away - home == 2),
        "ext_3_plus": _sum(matrix, lambda home, away: away - home >= 3),
    }


# ============================================================
# TOTAL BUTS
# ============================================================

def market_total_buts(lambda_dom, lambda_ext, lignes=(0.5, 1.5, 2.5, 3.5, 4.5, 5.5)):
    lam_total = lambda_dom + lambda_ext
    result = {}
    for ligne in lignes:
        key = str(ligne).replace(".", "_")
        n = int(ligne)
        p_under = poisson.cdf(n, lam_total)
        result[f"over_{key}"] = 1 - p_under
        result[f"under_{key}"] = p_under
    return result


# ============================================================
# BTTS
# ============================================================

def market_btts(matrix):
    oui = _sum(matrix, lambda i, j: i >= 1 and j >= 1)
    return {"oui": oui, "non": 1 - oui}


# ============================================================
# BUTS PAR ÉQUIPE
# ============================================================

def market_buts_par_equipe(matrix):
    result = {"dom": {}, "ext": {}}
    for k in range(4):
        if k < 3:
            result["dom"][str(k)] = _sum(matrix, lambda i, j, kk=k: i == kk)
            result["ext"][str(k)] = _sum(matrix, lambda i, j, kk=k: j == kk)
        else:
            result["dom"]["3+"] = _sum(matrix, lambda i, j: i >= 3)
            result["ext"]["3+"] = _sum(matrix, lambda i, j: j >= 3)
    return result


# ============================================================
# SCORES EXACTS (TRI CORRECT sur valeur brute)
# ============================================================

def market_score_exact(matrix, top=10):
    scores = []
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            scores.append({"score": f"{i}-{j}", "prob": matrix[i][j]})
    scores.sort(key=lambda x: x["prob"], reverse=True)
    return scores[:top]


# ============================================================
# NOMBRE EXACT DE BUTS
# ============================================================

def market_total_exact(lambda_dom, lambda_ext, max_buts=5):
    lam_total = lambda_dom + lambda_ext
    result = {}
    for k in range(max_buts):
        result[f"exact_{k}"] = poisson.pmf(k, lam_total)
    result[f"exact_{max_buts}+"] = 1 - poisson.cdf(max_buts - 1, lam_total)
    return result


# ============================================================
# HANDICAP ASIATIQUE (avec PUSH)
# ============================================================

def market_handicap_asiatique(matrix, handicaps=(-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0)):
    """
    Convention : adjusted = (i - j) + handicap.
    Lignes entières → PUSH géré.
    """
    result = {}
    for h in handicaps:
        win, push, lose = 0.0, 0.0, 0.0
        for i in range(len(matrix)):
            for j in range(len(matrix[i])):
                adj = (i - j) + h
                p = matrix[i][j]
                if abs(adj) < 1e-9:
                    push += p
                elif adj > 0:
                    win += p
                else:
                    lose += p
        is_integer = abs(h - int(h)) < 1e-9
        result[f"ah_{h:+.1f}"] = {
            "win": win,
            "push": push if is_integer else None,
            "lose": lose,
        }
    return result


# ============================================================
# HANDICAP EUROPÉEN
# ============================================================

def market_handicap_europeen(matrix, handicaps=(-2, -1, 1, 2)):
    result = {}
    for h in handicaps:
        dom_win = _sum(matrix, lambda i, j, hh=h: i + hh > j)
        nul = _sum(matrix, lambda i, j, hh=h: i + hh == j)
        ext_win = _sum(matrix, lambda i, j, hh=h: i + hh < j)
        result[f"hcp_{h:+d}"] = {"dom": dom_win, "nul": nul, "ext": ext_win}
    return result


# ============================================================
# CLEAN SHEET / WIN TO NIL
# ============================================================

def market_clean_sheet(matrix):
    return {
        "dom_clean_sheet": _sum(matrix, lambda i, j: j == 0),
        "ext_clean_sheet": _sum(matrix, lambda i, j: i == 0),
    }


def market_win_to_nil(matrix):
    return {
        "dom_win_to_nil": _sum(matrix, lambda i, j: i > j and j == 0),
        "ext_win_to_nil": _sum(matrix, lambda i, j: j > i and i == 0),
    }


# ============================================================
# PIPELINE
# ============================================================

def compute_all_markets(matrix, lambda_dom, lambda_ext) -> dict:
    return {
        "1X2": market_1x2(matrix),
        "double_chance": market_double_chance(matrix),
        "draw_no_bet": market_draw_no_bet(matrix),
        "total_parity": market_total_parity(matrix),
        "winning_margin": market_winning_margin(matrix),
        "total_buts": market_total_buts(lambda_dom, lambda_ext),
        "btts": market_btts(matrix),
        "buts_par_equipe": market_buts_par_equipe(matrix),
        "score_exact": market_score_exact(matrix, top=10),
        "total_exact": market_total_exact(lambda_dom, lambda_ext),
        "handicap_asiatique": market_handicap_asiatique(matrix),
        "handicap_europeen": market_handicap_europeen(matrix),
        "clean_sheet": market_clean_sheet(matrix),
        "win_to_nil": market_win_to_nil(matrix),
    }