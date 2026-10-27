"""Le reste de Jarvis : parler sans attendre, accusé immédiat, filtre avant de parler, un seul satellite répond, colis,
tableau au repos, écran du PC (voir, cliquer), gestes de la main."""
import asyncio
import datetime as dt
import importlib
import json
import sys
import threading
import time
import types
from pathlib import Path


from integration_pg import requiert_pg

SAT = Path(__file__).parent.parent / "app" / "data" / "satellite"


# ---------------------------------------------------------------- sans base

def test_decoupage_en_phrases():
    from app.parole import Decoupeur
    d, out = Decoupeur(), []
    for m in ["Il fait 12", " degrés. Demain, M. Dupont passe à 9 h. Ça", " va ? Oui ! Le prix : 3.5 euros, etc. pour finir"]:
        out += d.ajouter(m)
    assert out == ["Il fait 12 degrés.", "Demain, M. Dupont passe à 9 h.", "Ça va ? Oui !"]
    assert d.fin() == "Le prix : 3.5 euros, etc. pour finir" and d.fin() == ""
    longue = Decoupeur().ajouter("mot, " * 80)
    assert longue and len(longue[0]) < 260


def test_accuseur(monkeypatch):
    from app import parole
    monkeypatch.setattr(parole, "DELAI_ACCUSE_S", 0.05)
    monkeypatch.setattr(parole, "DELAI_PATIENCE_S", 0.15)
    monkeypatch.setattr(parole, "DELAI_REFLEXION_S", 0.05)

    async def scenario():
        dits = []

        async def dire(t):
            dits.append(t)
        a = parole.Accuseur(dire, "normal")
        await a.observer({"type": "state", "state": "thinking"})
        await asyncio.sleep(0.08)                                   # le modèle tarde : « Voyons… »
        await a.observer({"type": "tool_call", "name": "weather_get"})
        await asyncio.sleep(0.08)                                   # l'outil traîne : accusé
        await asyncio.sleep(0.15)                                   # et traîne encore : patience
        await a.observer({"type": "tool_result", "name": "weather_get"})
        await a.observer({"type": "tool_call", "name": "web_search"})   # un seul accusé par tour
        await asyncio.sleep(0.08)
        await a.observer({"type": "token", "text": "Il fait beau."})
        await asyncio.sleep(0.2)
        a.fermer()
        rapide = []

        async def dire2(t):
            rapide.append(t)
        b = parole.Accuseur(dire2, "majordome", reflexion=False)
        await b.observer({"type": "tool_call", "name": "device_control"})
        await b.observer({"type": "tool_result", "name": "device_control"})   # outil rapide : rien à dire
        await b.observer({"type": "tool_call", "name": "gmail_search"})
        await asyncio.sleep(0.08)
        await b.observer({"type": "confirm_pending", "name": "x"})
        await b.observer({"type": "tool_call", "name": "poser_question"})
        await asyncio.sleep(0.08)
        return dits, rapide
    dits, rapide = asyncio.run(scenario())
    assert dits[0] in parole._REFLEXION and dits[1] in parole._ATTENTE["meteo"] and dits[2] in parole._PATIENCE and len(dits) == 3, dits
    assert rapide == ["Je parcours votre courrier."]
    assert parole.famille("calendar_list") == "agenda" and parole.famille("gmail_colis") == "mail" and parole.famille("xyz") == "defaut"


def test_filtre_avant_de_parler():
    from app.confidentialite import caviarder
    assert caviarder("Ton jeton est evasat_abcDEF1234567890xyz") == "Ton jeton est une clé secrète"
    assert caviarder("Le mot de passe est Soleil2024!") == "Le mot de passe : masqué"
    assert caviarder("Vire sur FR76 3000 6000 0112 3456 7890 189") == "Vire sur un IBAN"
    assert caviarder("Carte 4970 1234 5678 9012") == "Carte un numéro de carte"
    t = "Écris à jean.dupont@gmail.com ou au 06 12 34 56 78."
    assert caviarder(t) == t and caviarder(t, annonce=True) == "Écris à une adresse mail ou au un numéro de téléphone."
    ordinaire = "Il fait 12 degrés le 25 octobre 2026, à 14 h 30 ; ton colis 6A12345678901 arrive."
    assert caviarder(ordinaire, annonce=True) == ordinaire


def test_colis_analyse():
    from app import colis
    now = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.timezone.utc)
    d = lambda j, h=10: f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.date(2026,10,j).weekday()]}, {j} Oct 2026 {h:02d}:00:00 +0000"  # noqa: E731
    msgs = [
        {"de": "Amazon.fr <confirmation-commande@amazon.fr>", "objet": "Votre commande 405-1234567-1234567 a été expédiée", "date": d(22)},
        {"de": "Amazon.fr <shipment-tracking@amazon.fr>", "objet": "Livraison aujourd'hui : commande 405-1234567-1234567", "date": d(25, 7)},
        {"de": "Vinted <no-reply@vinted.fr>", "objet": "Ton colis est disponible en point relais", "date": d(24)},
        {"de": "Fnac <noreply@fnac.com>", "objet": "Votre commande n°ABC12345 a été livrée", "date": d(21)},       # livré il y a 4 jours : oublié
        {"de": "Cdiscount <promo@cdiscount.com>", "objet": "Livraison gratuite sur tout le site !", "date": d(25)},   # publicité
        {"de": "Lecteurs <club@livres.fr>", "objet": "Un livre pour vous", "date": d(25)},
    ]
    r = colis.analyser(msgs, now)
    assert [(c["marchand"], c["statut"]) for c in r] == [("Amazon.fr", "Livraison aujourd'hui"), ("Vinted", "En point relais")], r
    assert r[0]["numero"] == "405-1234567-1234567" and r[0]["phrase"] == "Amazon.fr arrive aujourd'hui"
    assert colis.DEMANDE.search("où en sont mes colis ?") and not colis.DEMANDE.search("envoie un mail à Paul")


def _client_satellite():
    sys.modules.setdefault("sounddevice", types.SimpleNamespace(InputStream=None, play=None, wait=None, rec=None, query_devices=None, stop=None))
    if str(SAT) not in sys.path:
        sys.path.insert(0, str(SAT))
    return importlib.import_module("satellite"), importlib.import_module("gestes")


def test_satellite_nettoyage_et_niveau():
    import numpy as np
    sat, _g = _client_satellite()
    assert sat.nettoyer("**Rendez-vous** à 14:30 😀, ça coûte 12 € et il fait 18 °C (90 %)") == \
        "Rendez-vous à 14 h 30 , ça coûte 12 euros et il fait 18 degrés (90 pour cent)"
    silence = np.zeros(16000, dtype=np.int16)
    voix = (np.sin(np.arange(16000) / 5) * 3000).astype(np.int16)
    assert sat.niveau(np.concatenate([silence, voix])) > 1500 > sat.niveau(silence)


def _main(points):
    """Main de 21 points à partir de quelques positions (x, y) ; les autres sont interpolées."""
    return [types.SimpleNamespace(x=x, y=y) for x, y in points]


def _main_pose(nom, cx=0.5, cy=0.6):
    # poignet en bas ; chaque doigt : base, articulation, avant-dernière phalange, bout (tendu = bout loin du poignet)
    w = (cx, cy + 0.2)
    def doigt(dx, tendu):
        base = (cx + dx, cy)
        if tendu:
            return [base, (cx + dx, cy - 0.05), (cx + dx, cy - 0.1), (cx + dx, cy - 0.15)]
        return [base, (cx + dx, cy - 0.04), (cx + dx, cy + 0.0), (cx + dx, cy + 0.03)]
    tendus = {"ouverte": (1, 1, 1, 1), "deux": (1, 1, 0, 0), "trois": (1, 1, 1, 0), "index": (1, 0, 0, 0), "poing": (0, 0, 0, 0)}[nom]
    pouce = [(cx - 0.06, cy + 0.12), (cx - 0.1, cy + 0.08), (cx - 0.13, cy + 0.04), (cx - 0.16, cy + 0.0)] if nom == "ouverte" else \
        [(cx - 0.04, cy + 0.12), (cx - 0.05, cy + 0.08), (cx - 0.03, cy + 0.05), (cx - 0.01, cy + 0.04)]
    pts = [w] + pouce
    for dx, t in zip((-0.04, 0.0, 0.04, 0.08), tendus):
        pts += doigt(dx, t)
    return _main(pts)


def test_gestes_vocabulaire_et_modes():
    _sat, g = _client_satellite()
    for nom in ("ouverte", "deux", "trois", "index", "poing"):
        assert g.pose(_main_pose(nom)) == nom, nom
    d, t, actions = g.Detecteur(), 0.0, []

    def tenir(nom, duree, **kw):
        nonlocal t
        fin = t + duree
        while t < fin:
            actions.extend(d.step(t, [_main_pose(nom, **kw)]))
            t += 0.1
    tenir("ouverte", 1.2)
    assert ("touche", "lecture_pause") in actions
    actions.clear(); t += 1.5
    tenir("deux", 1.1)
    assert ("mode", "onglets", "") in actions and d.mode == "onglets"
    actions.clear()
    tenir("ouverte", 0.3, cx=0.5)
    tenir("ouverte", 0.3, cx=0.35)                 # image miroir : la main va vers la DROITE de la personne
    assert ("touche", "onglet_suivant") in actions, actions
    actions.clear()
    tenir("ouverte", 0.3, cx=0.35, cy=0.72)
    assert ("touche", "page_bas") in actions, actions
    actions.clear(); t += 3
    actions.extend(d.step(t, []))
    t += 2.5
    actions.extend(d.step(t, []))
    assert d.mode is None and actions[-1][0] == "mode"
    actions.clear(); t += 1.5
    tenir("index", 1.1)
    assert d.mode == "souris"
    tenir("index", 0.3, cx=0.3)
    assert any(a[0] == "souris" for a in actions)
    actions.clear(); t += 1.5
    tenir("poing", 1.0)
    assert d.mode is None
    deux_mains = [[_main_pose("ouverte", cx=0.4), _main_pose("ouverte", cx=0.6)], [_main_pose("ouverte", cx=0.25), _main_pose("ouverte", cx=0.75)]]
    z = d.step(t, deux_mains[0]) + d.step(t + 0.1, deux_mains[1])
    assert ("zoom", 1) in z


def test_ecran_clic_vise_le_texte(monkeypatch):
    sat, _g = _client_satellite()
    e = sat.Ecran.__new__(sat.Ecran)
    lignes = [{"texte": "Nouveau message", "x": 10, "y": 10, "l": 200, "h": 20},
              {"texte": "Envoyer", "x": 900, "y": 700, "l": 80, "h": 24},
              {"texte": "Annuler l'envoi", "x": 500, "y": 700, "l": 150, "h": 24}]
    monkeypatch.setattr(e, "capture", lambda: (None, 100, 0), raising=False)
    monkeypatch.setattr(e, "lire", lambda img: lignes, raising=False)
    monkeypatch.setattr(sat.Ecran, "fenetre_active", staticmethod(lambda: "Gmail - Chrome"))
    monkeypatch.setattr(sat, "SYSTEME", "Linux")
    monkeypatch.setattr(sat.shutil, "which", lambda n: "/usr/bin/" + n)
    clics = []
    monkeypatch.setattr(sat, "_cmd", lambda a: clics.append(a) or "")
    r = e.cliquer("envoyer")
    assert r == {"ok": True, "clique_sur": "Envoyer", "fenetre": "Gmail - Chrome"} and clics[-1][2:4] == ["1040", "712"]
    r = e.cliquer("annuler")
    assert r["clique_sur"] == "Annuler l'envoi" and int(clics[-1][2]) < 600 + 100
    assert "Je ne vois pas" in e.cliquer("Supprimer")["error"]
    monkeypatch.setattr(sat.Ecran, "fenetre_active", staticmethod(lambda: "Boursorama Banque - Chrome"))
    assert "protégée" in e.cliquer("Envoyer")["error"]


# ---------------------------------------------------------------- avec EVA complète

def _sat(eva, nom, piece):
    c, H, t = eva["c"], eva["H"], eva["t"]
    s = c.post("/api/home/admin/satellites", json={"nom": nom, "piece": piece, "compte": "alice"}, headers=H(t["alice"])).json()
    return s, {"Authorization": f"Bearer {s['jeton']}"}


def _lignes(c, url, S, texte):
    with c.stream("POST", url, json={"texte": texte}, headers=S) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        return [json.loads(x) for x in r.iter_lines() if x.strip()]


@requiert_pg
def test_satellite_parle_au_fil_de_l_eau(eva, monkeypatch):
    from app import parole
    from app.harness import loop
    from app.harness.tools import weather
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    monkeypatch.setattr(parole, "DELAI_ACCUSE_S", 0.1)
    monkeypatch.setattr(parole, "DELAI_REFLEXION_S", 99)

    async def lent(self, city="", days=3, **_):
        await asyncio.sleep(0.5)
        return {"city": city, "current": {"temperature_c": 12}, "forecast": []}
    monkeypatch.setattr(weather.WeatherTool, "execute", lent)
    vus = []
    etapes = iter([
        [("tool_calls", [{"function": {"name": "weather_get", "arguments": {"city": "Paris"}}}])],
        [("content", "Il fait 12 degrés à Paris"), ("content", ". Demain, pluie probable. Ton jeton evasat_abcdefgh12345678 reste secret. "),
         ("content", "Prends un parapluie !")],
        [("content", "Très bien, merci ! Et toi, ta journée se passe bien ?")],
        [("tool_calls", [{"function": {"name": "obs_action", "arguments": {"action": "demarrer_live"}}}])],
        [("content", "C'est fait.")],
    ])

    async def flux(history, tools=None, model=None):
        vus.append({"system": history[0]["content"], "outils": [t["function"]["name"] for t in tools or []]})
        for ev in next(etapes):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    c.put("/api/personality", json={"id": "majordome"}, headers=A)
    s, S = _sat(eva, "Salon", "salon")
    evs = _lignes(c, "/api/satellite/demander_flux", S, "Quel temps fait-il à Paris ?")
    assert evs[0]["attente"] in parole._ATTENTE_MAJORDOME["meteo"], evs
    assert [e["dire"] for e in evs if "dire" in e] == ["Il fait 12 degrés à Paris.", "Demain, pluie probable.",
                                                      "Ton jeton une clé secrète reste secret.", "Prends un parapluie !"]
    assert "evasat_abcdefgh" in evs[-1]["reponse"] and "dire_aussi" not in evs[-1]           # écrit complet pour la fenêtre du PC
    assert "majordome" in vus[0]["system"] and "weather_get" in vus[0]["outils"] and "salon" in vus[0]["system"]

    evs = _lignes(c, "/api/satellite/demander_flux", S, "Comment ça va ?")             # conversation : mode léger, sans outils
    assert vus[2]["outils"] == [] and len(vus[2]["system"]) < 2500 and [e for e in evs if "dire" in e]

    evs = _lignes(c, "/api/satellite/demander_flux", S, "Lance le live sur OBS")
    assert "piloter OBS" in evs[-1]["question"]
    evs = _lignes(c, "/api/satellite/repondre_flux", S, "oui")
    assert evs[-1]["reponse"] == "C'est fait." and evs[0] == {"dire": "C'est fait."}
    assert _lignes(c, "/api/satellite/repondre_flux", S, "oui")[-1]["dire_aussi"]
    evs = _lignes(c, "/api/satellite/demander_flux", S, "Quelle heure est-il ?")
    assert evs == [{"reponse": evs[0]["reponse"], "dire_aussi": True}] and evs[0]["reponse"].startswith("Il est ")
    c.put("/api/personality", json={"id": "normal"}, headers=A)
    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)


@requiert_pg
def test_un_seul_satellite_repond(eva):
    from app import satellites
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    s1, S1 = _sat(eva, "Cuisine", "cuisine")
    seul = c.post("/api/satellite/eveil", json={"score": 3}, headers=S1).json()
    assert seul == {"repondre": True}                                  # un seul satellite à l'écoute : pas d'attente
    s2, S2 = _sat(eva, "Salon", "salon")
    for S in (S1, S2):
        c.post("/api/satellite/bonjour", json={"capacites": ["dire"]}, headers=S)
    satellites._manche = None
    res = {}

    def reclamer(nom, S, score):
        res[nom] = c.post("/api/satellite/eveil", json={"score": score}, headers=S).json()["repondre"]
    th = [threading.Thread(target=reclamer, args=("cuisine", S1, 2.0)), threading.Thread(target=reclamer, args=("salon", S2, 6.5))]
    for x in th:
        x.start()
    for x in th:
        x.join()
    assert res == {"cuisine": False, "salon": True}
    assert c.post("/api/satellite/eveil", json={"score": 9}, headers=S1).json()["repondre"] is False      # même phrase, en retard
    assert c.post("/api/satellite/eveil", json={"score": 1, "suite": True}, headers=S2).json()["repondre"] is True
    satellites._manche = None
    for s in (s1, s2):
        c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)


@requiert_pg
def test_tableau_au_repos_et_colis(eva, monkeypatch):
    from app import google, tableau
    from app.harness.tools import weather
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]

    async def meteo(self, city="", days=3, **_):
        return {"city": "Paris", "current": {"temperature_c": 14.4, "condition": "nuageux"},
                "forecast": [{"temp_min": 8, "temp_max": 16, "precipitation_probability_max": 40}]}
    monkeypatch.setattr(weather.WeatherTool, "execute", meteo)

    async def statut():
        return {"connected": True}
    hier = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S +0000")

    async def chercher(q, limit=10):
        assert "newer_than:" in q
        return {"messages": [{"de": "Vinted <no-reply@vinted.fr>", "objet": "Ton colis est disponible en point relais", "date": hier}]}

    async def agenda(days=7, limit=15):
        return {"evenements": [{"titre": "Dentiste", "debut": (dt.datetime.now() + dt.timedelta(hours=2)).astimezone().isoformat()}]}
    monkeypatch.setattr(google, "status", statut)
    monkeypatch.setattr(google, "gmail_search", chercher)
    monkeypatch.setattr(google, "calendar_list", agenda)
    tableau._cache.clear()
    c.post("/api/notes", json={"text": "Acheter du pain"}, headers=A)
    s, S = _sat(eva, "Bureau", "bureau")
    d = c.get("/api/satellite/tableau", headers=S).json()
    titres = {t["titre"]: t["lignes"] for t in d["tuiles"]}
    assert titres["Météo"][0] == "Paris : 14 °C, nuageux" and "pluie 40 %" in titres["Météo"][1]
    assert titres["Colis"] == ["Vinted : En point relais"] and "Dentiste" in titres["Agenda"][0]
    assert any("Acheter du pain" in x for x in titres["Post-it"])
    assert c.get("/api/satellite/tableau", headers={"Authorization": "Bearer evasat_faux"}).status_code == 401
    r = c.portal.call(lambda: m.registry.get("gmail_colis").execute())
    assert r["resume"] == "Vinted t'attend en point relais." and r["colis"][0]["etape"] == "relais"
    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)


@requiert_pg
def test_ecran_du_pc(eva, monkeypatch):
    from app import autorisations, ollama_client
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]
    s, S = _sat(eva, "PC du bureau", "bureau")
    run = lambda nom, **kw: c.portal.call(lambda: m.registry.get(nom).execute(**kw))      # noqa: E731
    assert "Aucun ordinateur" in run("pc_ecran_voir")["error"]
    c.post("/api/satellite/bonjour", json={"capacites": ["dire", "pc", "ecran"], "systeme": "Windows"}, headers=S)
    fin, recus = threading.Event(), []

    def satellite():
        while not fin.is_set():
            for o in c.post("/api/satellite/ordres", headers=S).json()["ordres"]:
                recus.append(o)
                res = {"ok": True, "texte": "Erreur 0x80070005 : accès refusé", "fenetre": "Windows Update", "image": "aGVsbG8="} \
                    if o["action"] == "voir" else {"ok": True, "clique_sur": o["cible"], "fenetre": "Gmail"}
                c.post("/api/satellite/resultat", json={"id": o["id"], "resultat": res}, headers=S)
    threading.Thread(target=satellite, daemon=True).start()
    time.sleep(0.4)

    async def vision(messages, tools=None, model=None):
        assert messages[0]["images"] == ["aGVsbG8="] and "erreur" in messages[0]["content"]
        return {"message": {"content": "Une fenêtre Windows Update affiche une erreur d'accès refusé."}}
    monkeypatch.setattr(ollama_client, "chat_once", vision)
    r = run("pc_ecran_voir", question="pourquoi j'ai cette erreur ?")
    assert r["texte_a_l_ecran"].startswith("Erreur 0x80070005") and "Windows Update" in r["description"] and r["ordinateur"] == "PC du bureau"
    assert "image" not in r
    r = run("pc_ecran_cliquer", cible="Envoyer")
    assert r["clique_sur"] == "Envoyer" and recus[-1]["type"] == "ecran" and recus[-1]["cible"] == "Envoyer"
    assert m.registry.get("pc_ecran_cliquer").permission.value == "confirm" and autorisations.critique("pc_ecran_cliquer")
    assert m.registry.get("pc_ecran_voir").permission.value == "auto"
    fin.set()
    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)


@requiert_pg
def test_interface_vocale_accuse_reception(eva, monkeypatch):
    from app import parole
    from app.harness import loop
    from app.harness.tools import weather
    monkeypatch.setattr(parole, "DELAI_ACCUSE_S", 0.1)
    monkeypatch.setattr(parole, "DELAI_REFLEXION_S", 99)

    async def lent(self, city="", days=3, **_):
        await asyncio.sleep(0.4)
        return {"city": city, "current": {"temperature_c": 12}, "forecast": []}
    monkeypatch.setattr(weather.WeatherTool, "execute", lent)
    etapes = iter([[("tool_calls", [{"function": {"name": "weather_get", "arguments": {"city": "Paris"}}}])],
                   [("content", "Il fait 12 degrés.")], [("content", "Bonjour !")]])

    async def flux(history, tools=None, model=None):
        for ev in next(etapes):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    c, t = eva["c"], eva["t"]["alice"]
    sid = c.post("/api/sessions", json={"title": "voix"}, headers=eva["H"](t)).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={t}&session={sid}") as w:
        w.send_json({"text": "Quel temps fait-il à Paris ?", "voice": True})
        types_vus = []
        for _ in range(200):
            ev = w.receive_json()
            types_vus.append((ev.get("type"), ev.get("text")))
            if ev.get("type") == "done":
                break
        att = [x for x in types_vus if x[0] == "attente"]
        assert len(att) == 1 and att[0][1] in parole._ATTENTE["meteo"], types_vus
        assert types_vus.index(att[0]) < next(i for i, x in enumerate(types_vus) if x[0] == "token")
        w.send_json({"text": "Bonjour"})                                          # à l'écrit : jamais de phrase d'attente
        vus = []
        for _ in range(200):
            ev = w.receive_json()
            vus.append(ev.get("type"))
            if ev.get("type") == "done":
                break
        assert "attente" not in vus
