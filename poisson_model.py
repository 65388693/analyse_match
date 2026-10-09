"""
poisson_model.py
Moteur Poisson unique — source de vérité pour TOUS les marchés.
"""

from scipy.stats import poisson
from config import MAX_GOALS


def _dixon_coles_tau(i, j, lambda_dom, lambda_ext, rho=-0.05):
    if i == 0 and j == 0:
        return 1 - lambda_dom * lambda_ext * rho
    elif i == 0 and j == 1:
        return 1 + lambda_dom * rho
    elif i == 1 and j == 0:
        return 1 + lambda_ext * rho
    elif i == 1 and j == 1:
        return 1 - rho
    return 1.0


def build_score_matrix(lambda_dom: float, lambda_ext: float,
                       use_dixon_coles: bool = True) -> list:
    matrix = []
    for i in range(MAX_GOALS + 1):
        row = []
        for j in range(MAX_GOALS + 1):
            p = poisson.pmf(i, lambda_dom) * poisson.pmf(j, lambda_ext)
            if use_dixon_coles:
                p *= _dixon_coles_tau(i, j, lambda_dom, lambda_ext)
            row.append(max(p, 0))
        matrix.append(row)
    return matrix


def normalize_matrix(matrix: list) -> list:
    total = sum(sum(row) for row in matrix)
    if total == 0:
        raise ValueError("Matrice de scores vide")
    return [[p / total for p in row] for row in matrix]


def analyze_with_lambdas(lambda_dom: float, lambda_ext: float,
                          use_dixon_coles: bool = True) -> dict:
    matrix = build_score_matrix(lambda_dom, lambda_ext, use_dixon_coles)
    matrix = normalize_matrix(matrix)

    total = sum(sum(row) for row in matrix)
    assert abs(total - 1.0) < 1e-9, f"Matrice non normalisée : {total}"

    return {
        "lambda_dom": round(lambda_dom, 6),
        "lambda_ext": round(lambda_ext, 6),
        "matrix": matrix,
        "checksum": round(total, 9),
    }