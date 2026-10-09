"""
interactive.py
Interface interactive avec mode "tous les matchs du jour".
"""

import json
import os
from datetime import datetime
from api_client import get_fixtures


def _extract_matches(fixtures):
    if isinstance(fixtures, list):
        return fixtures
    if isinstance(fixtures, dict):
        if "structuredContent" in fixtures:
            sc = fixtures["structuredContent"]
            if isinstance(sc, dict) and "matches" in sc:
                return sc["matches"]
        if "content" in fixtures:
            try:
                text = fixtures["content"][0]["text"]
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "matches" in parsed:
                    return parsed["matches"]
            except (KeyError, IndexError, json.JSONDecodeError):
                pass
        if "matches" in fixtures:
            return fixtures["matches"]
    return []


def load_leagues():
    path = os.path.join("data", "leagues.json")
    if not os.path.exists(path):
        raise Exception("❌ data/leagues.json introuvable")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def group_by_country(leagues):
    par_pays = {}
    for lg in leagues:
        par_pays.setdefault(lg.get("country", "Inconnu"), []).append(lg)
    return par_pays


def choose_country(par_pays):
    pays_list = sorted(par_pays.keys())
    print("\n" + "=" * 60)
    print("   🌍 CHOIX DU PAYS")
    print("=" * 60)
    for i, p in enumerate(pays_list, 1):
        print(f"   {i:>3}. {p}")
    print(f"   {len(pays_list)+1:>3}. 🚪 QUITTER")
    while True:
        c = input("\n👉 Numéro : ").strip()
        if c.isdigit():
            n = int(c)
            if 1 <= n <= len(pays_list):
                return pays_list[n - 1]
            if n == len(pays_list) + 1:
                return None
        print("   ⚠️  Invalide")


def choose_league(par_pays, pays):
    ligues = par_pays[pays]
    print("\n" + "=" * 60)
    print(f"   🏆 CHAMPIONNATS — {pays}")
    print("=" * 60)
    for i, lg in enumerate(ligues, 1):
        saisons = ", ".join(lg.get("seasons", [])[:1])
        print(f"   {i:>3}. {lg['name']:<35} ({saisons})")
    print(f"   {len(ligues)+1:>3}. ↩️  RETOUR")
    while True:
        c = input("\n👉 Numéro : ").strip()
        if c.isdigit():
            n = int(c)
            if 1 <= n <= len(ligues):
                return ligues[n - 1]
            if n == len(ligues) + 1:
                return None
        print("   ⚠️  Invalide")


def ask_date():
    print("\n" + "=" * 60)
    print("   📅 DATE DU MATCH")
    print("=" * 60)
    print("   Format : YYYY-MM-DD  (ex: 2026-09-18)")
    print("   → 'q' pour quitter")
    while True:
        d = input("\n👉 Date : ").strip()
        if d.lower() == "q":
            return None
        try:
            datetime.strptime(d, "%Y-%m-%d")
            return d
        except ValueError:
            print("   ⚠️  Invalide")


def get_matches_for_date(league_key, date):
    """Récupère TOUS les matchs d'une ligue à une date."""
    fixtures = get_fixtures(league_key)
    matchs = _extract_matches(fixtures)
    return [m for m in matchs if m.get("match_date") == date]


def choose_match_mode(matchs):
    """Search and page through the global schedule, then return one match."""
    page_size = 30
    query = ""
    page = 0

    while True:
        filtered = [
            match for match in matchs
            if query in " ".join((
                match["home_team"],
                match["away_team"],
                match["country"],
                match["real_league_name"],
            )).casefold()
        ]
        page_count = max(1, (len(filtered) + page_size - 1) // page_size)
        page = min(page, page_count - 1)
        start = page * page_size
        current = filtered[start:start + page_size]

        print("\n" + "=" * 86)
        print(f"   MATCHS DU JOUR : {len(matchs)} | résultats : {len(filtered)} | page {page + 1}/{page_count}")
        print("=" * 86)
        for offset, match in enumerate(current, start + 1):
            availability = "LIGUE COUVERTE" if match.get("analysis_league_key") else "agenda seulement"
            event_state = match.get("score") or match.get("status_display") or match["status"]
            print(
                f"{offset:>3}. {match['time']:<8} {match['home_team']} - {match['away_team']}"
                f" | {event_state} | {match['real_league_name']} ({match['country']}) [{availability}]"
            )

        print("\nNuméro = analyser | n = suivant | p = précédent | /texte = rechercher | * = tout | q = retour")
        choice = input("👉 Choix : ").strip()
        if choice.lower() == "q":
            return None
        if choice.lower() == "n":
            page = min(page + 1, page_count - 1)
            continue
        if choice.lower() == "p":
            page = max(page - 1, 0)
            continue
        if choice == "*":
            query = ""
            page = 0
            continue
        if choice.startswith("/"):
            query = choice[1:].casefold().strip()
            page = 0
            continue
        if choice.isdigit():
            selected_index = int(choice) - 1
            if start <= selected_index < start + len(current):
                selected = filtered[selected_index]
                if not selected.get("analysis_league_key"):
                    print("   ⚠️  Cette compétition n'est pas reliée au catalogue statistique local.")
                    continue
                return selected
        print("   ⚠️  Choix invalide")