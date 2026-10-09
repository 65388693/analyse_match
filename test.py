"""
symbiose.py
Symbiose des APIs avec sélection interactive du match.

1. Tu choisis le match dans The Odds API
2. On récupère les cotes
3. On cherche blessures/arbitre sur Live Football API (hors U19/B)
4. On récupère la forme locale sur football-charts
"""

import json
import requests
from config import FC_API_KEY, LIVE_FOOTBALL_KEY, ODDS_API_KEY

# ============================================================
# CLÉS API
# ============================================================

CHAMPIONS_LEAGUE_KEY = "soccer_uefa_champs_league"


# ============================================================
# MAPPING LIGUES LOCALES
# ============================================================

TEAM_TO_LEAGUE = {
    # Premier League
    "arsenal": "premier", "chelsea": "premier", "liverpool": "premier",
    "manchester city": "premier", "manchester united": "premier",
    "tottenham": "premier", "newcastle": "premier", "aston villa": "premier",
    "brighton": "premier", "west ham": "premier", "everton": "premier",
    "fulham": "premier", "crystal palace": "premier", "brentford": "premier",
    "wolves": "premier", "nottingham forest": "premier", "bournemouth": "premier",
    "leicester": "premier", "ipswich": "premier", "southampton": "premier",

    # LaLiga
    "real madrid": "spain1", "barcelona": "spain1", "atletico madrid": "spain1",
    "atlético madrid": "spain1", "sevilla": "spain1", "valencia": "spain1",
    "villarreal": "spain1", "real betis": "spain1", "athletic bilbao": "spain1",
    "real sociedad": "spain1", "osasuna": "spain1", "celta vigo": "spain1",
    "rayo vallecano": "spain1", "girona": "spain1", "alaves": "spain1",
    "getafe": "spain1", "mallorca": "spain1", "las palmas": "spain1",
    "espanyol": "spain1", "leganes": "spain1", "valladolid": "spain1",

    # Serie A
    "inter": "italy1", "inter milan": "italy1", "milan": "italy1",
    "juventus": "italy1", "napoli": "italy1", "roma": "italy1",
    "as roma": "italy1", "lazio": "italy1", "atalanta": "italy1",
    "fiorentina": "italy1", "bologna": "italy1", "como": "italy1",

    # Bundesliga
    "bayern munich": "germany1", "borussia dortmund": "germany1",
    "rb leipzig": "germany1", "bayer leverkusen": "germany1",
    "eintracht frankfurt": "germany1", "stuttgart": "germany1",
    "vfb stuttgart": "germany1",

    # Ligue 1
    "psg": "france1", "paris saint-germain": "france1",
    "paris saint germain": "france1",
    "marseille": "france1", "lyon": "france1", "monaco": "france1",
    "lille": "france1", "nice": "france1", "lens": "france1",
    "rc lens": "france1",

    # Portugal
    "porto": "portugal1", "benfica": "portugal1", "sporting lisbon": "portugal1",
    "sporting cp": "portugal1", "braga": "portugal1",

    # Netherlands
    "ajax": "holland1", "psv": "holland1", "psv eindhoven": "holland1",
    "feyenoord": "holland1", "az alkmaar": "holland1",

    # Turkey
    "galatasaray": "turkey1", "fenerbahce": "turkey1", "besiktas": "turkey1",

    # Autres
    "club brugge": "belgium1", "anderlecht": "belgium1",
    "shakhtar donetsk": "russia",  # approximation
    "slavia praha": "czech1", "viktoria plzen": "czech1",
    "slovan bratislava": "slovenia1",  # approximation
    "lask": "austria1", "salzburg": "austria1",
    "bodo/glimt": "norway", "bodø/glimt": "norway",
    "viking": "norway", "viking fk": "norway",
    "aek athens": "greece1",
    "sabah": "azer",
    "real betis": "spain1",
}


def find_league(team_name: str):
    """Trouve la ligue football-charts d'une équipe."""
    name_low = team_name.lower().strip()
    # Cherche le match le plus long d'abord (plus précis)
    best_match = None
    best_len = 0
    for key, league in TEAM_TO_LEAGUE.items():
        if key in name_low or name_low in key:
            if len(key) > best_len:
                best_match = league
                best_len = len(key)
    return best_match


# ============================================================
# ÉTAPE 1 : THE ODDS API — Matchs à venir
# ============================================================

def get_upcoming_events():
    """Liste les matchs à venir de Champions League (GRATUIT)."""
    print("\n" + "=" * 70)
    print("   📅 MATCHS CHAMPIONS LEAGUE À VENIR")
    print("=" * 70)

    url = f"https://api.the-odds-api.com/v4/sports/{CHAMPIONS_LEAGUE_KEY}/events"
    params = {"apiKey": ODDS_API_KEY}

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return []

        events = r.json()
        print(f"\n✅ {len(events)} matchs à venir\n")

        for i, ev in enumerate(events, 1):
            home = ev.get("home_team", "?")
            away = ev.get("away_team", "?")
            time = ev.get("commence_time", "?")
            print(f"   {i:>3}. {home} vs {away}")
            print(f"        🕐 {time}")
            print()

        return events

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return []


def choose_event(events: list):
    """Laisse l'utilisateur choisir un match."""
    if not events:
        return None

    while True:
        choix = input(f"\n👉 Numéro du match (1-{len(events)}) : ").strip()
        if choix.isdigit() and 1 <= int(choix) <= len(events):
            return events[int(choix) - 1]
        print("   ⚠️  Choix invalide, réessaie.")


# ============================================================
# ÉTAPE 1b : THE ODDS API — Cotes
# ============================================================

def get_match_odds(event_id: str, home: str, away: str):
    """Récupère les cotes du match choisi."""
    print("\n" + "=" * 70)
    print(f"   💰 COTES — {home} vs {away}")
    print("=" * 70)

    url = f"https://api.the-odds-api.com/v4/sports/{CHAMPIONS_LEAGUE_KEY}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"Status : {r.status_code}")
        print(f"💳 Crédits : {r.headers.get('x-requests-remaining')}")

        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return None

        data = r.json()
        bookmakers = data.get("bookmakers", [])
        print(f"✅ {len(bookmakers)} bookmakers\n")

        best = {"home": 0, "draw": 0, "away": 0}
        best_bk = {"home": "", "draw": "", "away": ""}

        for bk in bookmakers:
            bk_name = bk.get("title", "?")
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                for o in mk.get("outcomes", []):
                    name = o.get("name", "")
                    price = o.get("price", 0)
                    if name == home and price > best["home"]:
                        best["home"] = price
                        best_bk["home"] = bk_name
                    elif name == away and price > best["away"]:
                        best["away"] = price
                        best_bk["away"] = bk_name
                    elif name.lower() == "draw" and price > best["draw"]:
                        best["draw"] = price
                        best_bk["draw"] = bk_name

        print(f"   🎯 Meilleures cotes :")
        print(f"      1 ({home:<22}) : {best['home']:.2f}  ({best_bk['home']})")
        print(f"      X (Nul)                       : {best['draw']:.2f}  ({best_bk['draw']})")
        print(f"      2 ({away:<22}) : {best['away']:.2f}  ({best_bk['away']})")

        return best

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None


# ============================================================
# ÉTAPE 2 : LIVE FOOTBALL API — Blessures & Arbitre
# ============================================================

def live_football_find_match(home: str, away: str, date: str):
    """Cherche le match_id sur Live Football API (exclut U19/U21/B)."""
    print("\n" + "=" * 70)
    print(f"   🩹 LIVE FOOTBALL API — Recherche match_id ({date})")
    print("=" * 70)

    url = "https://live-football-api.com/api/v1/matches"
    params = {"date": date, "api_key": LIVE_FOOTBALL_KEY, "lang": "en"}

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return None

        data = r.json()
        matches = data.get("data", {}).get("matches", [])
        print(f"✅ {len(matches)} matchs ce jour-là")

        # Mots à exclure (équipes de jeunes/réserve/féminines)
        EXCLUDE = ["u19", "u21", "u23", "u18", "u20", "u17",
                   "women", "féminin", "feminin", " b", " ii", "reserve"]

        home_low = home.lower().strip()
        away_low = away.lower().strip()

        candidates = []

        for m in matches:
            h = m.get("home", {}).get("name", "").lower()
            a = m.get("away", {}).get("name", "").lower()

            # Exclut les équipes de jeunes/réserve
            if any(ex in h or ex in a for ex in EXCLUDE):
                continue

            # Match exact ou partiel
            h_match = home_low in h or h in home_low
            a_match = away_low in a or a in away_low

            if h_match and a_match:
                candidates.append(m)

        if not candidates:
            print(f"\n⚠️  Match {home} vs {away} introuvable (hors U19/B)")
            return None

        # Prend le premier candidat
        m = candidates[0]
        mid = m.get("id")
        print(f"\n✅ MATCH TROUVÉ : {m['home']['name']} vs {m['away']['name']}")
        print(f"   🆔 {mid}")

        if len(candidates) > 1:
            print(f"   ⚠️  {len(candidates)} candidats trouvés, premier sélectionné")

        return mid

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None


def live_football_injuries(match_id: str):
    """Récupère les blessures."""
    print("\n" + "=" * 70)
    print("   🩹 BLESSURES")
    print("=" * 70)

    url = "https://live-football-api.com/api/v1/injuries"
    params = {"match_id": match_id, "api_key": LIVE_FOOTBALL_KEY, "lang": "en"}

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return None

        data = r.json()
        print(f"💳 Crédits : {data.get('credits_remaining', '?')}")

        inj = data.get("data", {}).get("injuries", {})
        home_inj = inj.get("home", [])
        away_inj = inj.get("away", [])

        if not home_inj and not away_inj:
            print(f"\n   ✅ Aucune blessure déclarée pour ce match")
        else:
            for side, lst in [("Domicile", home_inj), ("Extérieur", away_inj)]:
                if lst:
                    print(f"\n   {side} :")
                    for p in lst:
                        name = p.get("player", p.get("name", "?"))
                        pos = p.get("position", "?")
                        reason = p.get("reason", p.get("injury", "?"))
                        print(f"      • {name} ({pos}) — {reason}")

        return inj

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None


def live_football_officials(match_id: str):
    """Récupère l'arbitre (avec valeurs par défaut si vide)."""
    print("\n" + "=" * 70)
    print("   👨‍⚖️ ARBITRE")
    print("=" * 70)

    DEFAULT_YELLOW = 4.0
    DEFAULT_RED = 0.20

    url = "https://live-football-api.com/api/v1/officials"
    params = {"match_id": match_id, "api_key": LIVE_FOOTBALL_KEY, "lang": "en"}

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return None

        data = r.json()
        print(f"💳 Crédits : {data.get('credits_remaining', '?')}")

        officials = data.get("data", {}).get("officials", [])
        main = None
        for o in officials:
            if o.get("role") == "Main":
                main = o
                break

        if not main:
            print(f"\n   ⚠️  Arbitre non désigné")
            print(f"   📊 Valeurs par défaut utilisées :")
            print(f"      Cartons jaunes/m : {DEFAULT_YELLOW}")
            print(f"      Cartons rouges/m : {DEFAULT_RED}")
            return {"avg_yellow_cards": DEFAULT_YELLOW, "avg_red_cards": DEFAULT_RED}

        yc = main.get("avg_yellow_cards") or DEFAULT_YELLOW
        rc = main.get("avg_red_cards") or DEFAULT_RED

        print(f"\n   👨‍⚖️ {main.get('name')}")
        print(f"      Cartons jaunes/m : {yc}")
        print(f"      Cartons rouges/m : {rc}")

        return {"avg_yellow_cards": yc, "avg_red_cards": rc}

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None


# ============================================================
# ÉTAPE 3 : FOOTBALL-CHARTS — Forme locale
# ============================================================

def fc_get_team(league: str, team: str):
    """Récupère les données d'une équipe via football-charts."""
    print("\n" + "=" * 70)
    print(f"   📊 FOOTBALL-CHARTS — {team} ({league})")
    print("=" * 70)

    url = "https://mcp.football-charts.com/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {FC_API_KEY}",
    }

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_team", "arguments": {"league": league, "team": team}},
        "id": 1,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, stream=True, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur : {r.text[:300]}")
            return None

        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "result" in data:
                        sc = data["result"].get("structuredContent", {})
                        stats = sc.get("stats", {})
                        ranking = sc.get("ranking", {})
                        print(f"✅ Données reçues")
                        print(f"   Position : {ranking.get('position')}e  |  "
                              f"Points : {ranking.get('points')}")
                        print(f"   xG : {stats.get('xg_avg')}  |  "
                              f"xG contre : {stats.get('xg_against_avg')}")
                        print(f"   Corners : {stats.get('corners_avg')}  |  "
                              f"Possession : {stats.get('possession_avg')}%")
                        return sc
                except json.JSONDecodeError:
                    continue

        print("⚠️  Pas de résultat")
        return None

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("   🧬 SYMBIOSE DES APIs")
    print("=" * 70)

    # 1. Matchs à venir
    events = get_upcoming_events()

    if not events:
        print("\n❌ Aucun match à venir")
        exit()

    # 2. Sélection interactive
    match = choose_event(events)
    home = match["home_team"]
    away = match["away_team"]
    date = match["commence_time"][:10]
    event_id = match["id"]

    print(f"\n✅ Match sélectionné : {home} vs {away}")
    print(f"   📅 {date}")

    # 3. Cotes The Odds API
    get_match_odds(event_id, home, away)

    # 4. Live Football API
    live_mid = live_football_find_match(home, away, date)
    if live_mid:
        live_football_injuries(live_mid)
        live_football_officials(live_mid)
    else:
        print("\n⚠️  Blessures et arbitre non disponibles")

    # 5. football-charts : forme locale
    home_league = find_league(home)
    away_league = find_league(away)

    if home_league:
        fc_get_team(home_league, home)
    else:
        print(f"\n⚠️  Ligue locale de {home} non trouvée dans le mapping")

    if away_league:
        fc_get_team(away_league, away)
    else:
        print(f"\n⚠️  Ligue locale de {away} non trouvée dans le mapping")

    print("\n✅ FIN DE LA SYMBIOSE")