"""
report.py
Rapport avec affichage des 5 derniers matchs.
"""


def _bar(p, width=15):
    if p is None:
        return " " * width
    n = int(round(p * width))
    n = max(0, min(n, width))
    return "█" * n + "░" * (width - n)


def _pct(p):
    if p is None:
        return "  --  "
    return f"{p*100:5.2f}%"


def _row(label, p):
    return f"   {label:<32} {_pct(p):<8} {_bar(p)}"


def _section(title):
    print(f"\n   ┌─ {title} " + "─" * max(0, 60 - len(title)))


def print_recent_matches(team_data, team_name):
    """Affiche les 5 derniers matchs d'une équipe."""
    if not team_data or not team_data.get("forme_lignes"):
        print(f"\n   📋 {team_name} — aucun match récent")
        return
    print(f"\n   📋 {team_name} — 5 derniers matchs ({team_data['forme_str']})")
    print(f"      xG : {team_data.get('xg_avg')}  |  xG contre : {team_data.get('xg_against_avg')}")
    for l in team_data["forme_lignes"]:
        print(f"      • {l}")


def print_report(match_info, analysis_xg, analysis_api, markets, markets_api,
                 explanations, api_probs, team_dom, team_ext,
                 extended=None, adjustments=None, officials=None,
                 show_recent=True):
    line = "=" * 72
    dom = match_info["home_team"]
    ext = match_info["away_team"]

    print("\n" + line)
    print(f"⚽  {dom}  vs  {ext}")
    print(f"📅  {match_info['date']}  •  {match_info['time']}  •  {match_info['league']}")
    print(line)

    # FORME + 5 DERNIERS MATCHS
    if show_recent:
        print_recent_matches(team_dom, dom)
        print_recent_matches(team_ext, ext)

    # BLESSURES
    if adjustments and adjustments.get("blessures"):
        print("\n   🩹 BLESSURES & IMPACT")
        for side, name in [("dom", dom), ("ext", ext)]:
            bl = adjustments["blessures"].get(side, [])
            if bl:
                print(f"      {name} :")
                for p in bl:
                    att = p.get("att_loss", 0) * 100
                    dfk = p.get("def_weak", 0) * 100
                    w = p.get("weight", 1.0)
                    print(f"         • {p['name']} ({p['position']}) [poids {w:.2f}] → att -{att:.0f}%  def +{dfk:.0f}%")
            else:
                print(f"      {name} : aucune blessure")
        print(f"\n      λ FINAL : {dom} {adjustments['lambda_dom_adj']}  |  {ext} {adjustments['lambda_ext_adj']}")

    if officials:
        print(f"\n   👨‍⚖️ ARBITRE : {officials.get('name')}  |  "
              f"Jaunes/m : {officials.get('avg_yellow_cards')}  |  "
              f"Rouges/m : {officials.get('avg_red_cards')}")

    print("\n" + line)
    print("   🎯 TOUS LES MARCHÉS")
    print(line)

    m = markets

    _section("1X2")
    print(_row(f"1 ({dom})", m["1X2"]["dom"]))
    print(_row("X (Nul)", m["1X2"]["nul"]))
    print(_row(f"2 ({ext})", m["1X2"]["ext"]))

    _section("DOUBLE CHANCE")
    print(_row("1X", m["double_chance"]["1X"]))
    print(_row("12", m["double_chance"]["12"]))
    print(_row("X2", m["double_chance"]["X2"]))

    _section("TOTAL BUTS")
    for k in ["over_0_5", "over_1_5", "over_2_5", "over_3_5", "over_4_5", "over_5_5"]:
        if k in m["total_buts"]:
            print(_row(k.replace("_", " ").upper(), m["total_buts"][k]))

    _section("BTTS")
    print(_row("Oui", m["btts"]["oui"]))
    print(_row("Non", m["btts"]["non"]))

    _section("BUTS PAR ÉQUIPE")
    for equipe, key in [(dom, "dom"), (ext, "ext")]:
        for k, p in m["buts_par_equipe"][key].items():
            print(_row(f"{equipe} {k} but(s)", p))

    _section("SCORES EXACTS (top 10)")
    for s in m["score_exact"]:
        print(_row(s["score"], s["prob"]))

    _section("NOMBRE EXACT DE BUTS")
    for k, p in m["total_exact"].items():
        print(_row(k.replace("_", " "), p))

    _section("HANDICAP EUROPÉEN")
    for h, vals in m["handicap_europeen"].items():
        print(_row(f"{h} → 1", vals["dom"]))
        print(_row(f"{h} → X", vals["nul"]))
        print(_row(f"{h} → 2", vals["ext"]))

    _section("HANDICAP ASIATIQUE (WIN/PUSH/LOSE)")
    for h, vals in m["handicap_asiatique"].items():
        print(_row(f"{h} → WIN", vals.get("win")))
        push = vals.get("push")
        if push is not None:
            print(_row(f"{h} → PUSH", push))
        print(_row(f"{h} → LOSE", vals.get("lose")))

    _section("CLEAN SHEET & WIN TO NIL")
    for k, p in m["clean_sheet"].items():
        print(_row(k.replace("_", " "), p))
    for k, p in m["win_to_nil"].items():
        print(_row(k.replace("_", " "), p))

    if extended:
        _section("MI-TEMPS — 1X2")
        ht = extended["ht_1x2"]
        print(_row(f"1 ({dom}) HT", ht["dom"]))
        print(_row("X HT", ht["nul"]))
        print(_row(f"2 ({ext}) HT", ht["ext"]))

        _section("MI-TEMPS — TOTAL BUTS")
        for k, p in extended["ht_total_buts"].items():
            print(_row(k.replace("_", " ").upper(), p))

        _section("MI-TEMPS — SCORES EXACTS")
        for s in extended["score_exact_ht"]:
            print(_row(s["score"], s["prob"]))

        _section("QUI MARQUE EN PREMIER ?")
        fs = extended["first_scorer"]
        print(_row(f"{dom}", fs["dom"]))
        print(_row(f"{ext}", fs["ext"]))
        print(_row("Aucun but", fs["no_goal"]))

        if extended.get("corners"):
            _section("CORNERS")
            c = extended["corners"]
            print(f"   Corners dom (moyenne) : {c.get('corners_dom', 0):.2f}")
            print(f"   Corners ext (moyenne) : {c.get('corners_ext', 0):.2f}")
            print(f"   Corners total (λ)     : {c.get('corners_total', 0):.2f}")
            for k, p in c.items():
                if k.startswith("over_"):
                    print(_row(k.replace("_", " ").upper(), p))

        if extended.get("cards"):
            _section("CARTONS")
            for k, p in extended["cards"].items():
                print(_row(k.replace("_", " ").upper(), p))

    if api_probs:
        print("\n" + line)
        print("   🔬 COMPARAISON — Modèle vs API")
        print(line)
        print(f"   {'Marché':<20} {'Nous':<10} {'API':<10} {'Écart':<10}")
        print(f"   {'-'*50}")
        for key, label in [("dom", dom), ("nul", "Nul"), ("ext", ext)]:
            ours = m["1X2"][key]
            theirs = api_probs["1X2"][key]
            diff = (ours - theirs) * 100
            sign = "+" if diff >= 0 else ""
            print(f"   {label:<20} {_pct(ours):<10} {_pct(theirs):<10} {sign}{diff:.2f}%")

    print("\n" + line)
    print("   🎲 Voici les résultats possibles — à vous de choisir.")
    print(line + "\n")