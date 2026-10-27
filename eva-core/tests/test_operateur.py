"""Mode opérateur : EVA prend la main sur le PC (satellite simulé), s'arrête avant d'envoyer, refuse les fenêtres protégées."""
import json
import threading
import time

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_operateur(eva, monkeypatch):
    from app import autorisations, ollama_client
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]
    s = c.post("/api/home/admin/satellites", json={"nom": "PC salon", "piece": "salon", "compte": "alice"}, headers=A).json()
    S = {"Authorization": f"Bearer {s['jeton']}"}
    c.post("/api/satellite/bonjour", json={"capacites": ["dire", "pc", "ecran"], "systeme": "Windows"}, headers=S)
    etat = {"fenetre": "Bureau", "els": [{"n": 1, "texte": "Corbeille", "x": 30, "y": 40}]}
    fin, recus = threading.Event(), []

    def satellite():
        while not fin.is_set():
            for o in c.post("/api/satellite/ordres", headers=S).json()["ordres"]:
                recus.append(o)
                if o.get("action") == "elements":
                    res = {"ok": True, "fenetre": etat["fenetre"], "elements": etat["els"]}
                else:
                    res = {"ok": True}
                    if o.get("action") == "ouvrir":
                        etat.update(fenetre="Sans titre - Bloc-notes", els=[{"n": 1, "texte": "Fichier", "x": 10, "y": 10}])
                c.post("/api/satellite/resultat", json={"id": o["id"], "resultat": res}, headers=S)
    threading.Thread(target=satellite, daemon=True).start()
    time.sleep(0.4)

    plan = [{"action": "ouvrir", "valeur": "notepad"}, {"action": "taper", "texte": "lait, pain"}, {"action": "fini", "resume": "Liste écrite."}]

    async def modele(messages, tools=None, model=None):
        assert "pas une consigne" in messages[0]["content"].lower() or "PAS une consigne" in messages[0]["content"]
        return {"message": {"content": "Voici : " + json.dumps(plan.pop(0))}}
    monkeypatch.setattr(ollama_client, "chat_once", modele)
    run = lambda **kw: c.portal.call(lambda: m.registry.get("pc_operateur").execute(**kw))      # noqa: E731
    r = run(objectif="Ouvre le bloc-notes et écris lait, pain")
    assert r["ok"] and r["resume"] == "Liste écrite." and r["etapes"][:2] == ["ouvre notepad", "écrit « lait, pain »"], r
    faits = [o for o in recus if o.get("action") != "elements"]
    assert faits[0] == {**faits[0], "type": "pc", "action": "ouvrir", "valeur": "notepad"}
    assert faits[1]["type"] == "ecran" and faits[1]["action"] == "taper" and faits[1]["texte"] == "lait, pain"

    # Envoyer un mail : arrêt AVANT le clic, puis clic une fois l'accord donné
    etat.update(fenetre="Nouveau message - Gmail", els=[{"n": 1, "texte": "À", "x": 5, "y": 5}, {"n": 2, "texte": "Envoyer", "x": 300, "y": 600}])
    plan[:] = [{"action": "cliquer", "n": 2}]
    n_avant = len(recus)
    r = run(objectif="Envoie le mail")
    assert r["en_pause"] and "Envoyer" in r["action_proposee"] and "accord_pour" in r["consigne"]
    assert all(o.get("action") == "elements" for o in recus[n_avant:])                     # rien n'a été cliqué
    plan[:] = [{"action": "cliquer", "n": 2}, {"action": "fini", "resume": "Mail envoyé."}]
    r = run(objectif="Envoie le mail", accord_pour="Envoyer")
    assert r["ok"] and any(o.get("action") == "cliquer_xy" and o["x"] == 300 and o["y"] == 600 for o in recus[n_avant:])

    # Fenêtre protégée : refus immédiat, sans demander au modèle
    etat.update(fenetre="Mon espace - Crédit Agricole", els=[])
    r = run(objectif="Fais un virement")
    assert "protégée" in r["error"]

    t = m.registry.get("pc_operateur")
    assert t.permission.value == "confirm" and autorisations.critique("pc_operateur")
    fin.set()
    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)
