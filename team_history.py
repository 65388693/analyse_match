"""
team_history.py
Récupère les données complètes d'une équipe via get_team.
"""

from api_client import get_cached_team, get_team
from data_cleaner import extract_team_data


def get_team_full(league: str, team: str) -> dict:
    """Récupère et nettoie les données d'une équipe."""
    try:
        data = get_team(league, team)
        return extract_team_data(data)
    except Exception as e:
        print(f"   ⚠️  Erreur récupération {team}: {e}")
        return None


def get_cached_team_full(league: str, team: str) -> dict:
    """Read and clean cached team data without issuing a network request."""
    try:
        data = get_cached_team(league, team)
        return extract_team_data(data) if data is not None else None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None