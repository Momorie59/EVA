"""« EVA comme Claude » : question à choix, vrais fichiers, actions critiques jamais « toujours »."""
from integration_pg import requiert_pg

pytestmark = requiert_pg


def _scenario(monkeypatch, etapes):
    from app.harness import loop
    vus = []
    it = iter(etapes)

    async def flux(history, tools=None, model=None):
        vus.append({"history": list(history), "tools": [t["function"]["name"] for t in tools or []]})
        for ev in next(it):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    return vus


def _appel(outil, **args):
    return ("tool_calls", [{"function": {"name": outil, "arguments": args}}])


def _ouvrir(eva):
    c, t = eva["c"], eva["t"]["alice"]
    sid = c.post("/api/sessions", json={"title": "claude"}, headers=eva["H"](t)).json()["id"]
    return c.websocket_connect(f"/ws/chat?token={t}&session={sid}")


def _jusqua(w, types):
    evs = []
    for _ in range(200):
        ev = w.receive_json()
        evs.append(ev)
        if ev.get("type") in types:
            return ev, evs
    raise AssertionError(f"pas de {types} : {[e.get('type') for e in evs]}")


def test_question_puis_document(eva, monkeypatch):
    vus = _scenario(monkeypatch, [
        [_appel("poser_question", question="Quel format ?", choix=["Word", "PDF"])],
        [_appel("document_creer", format="pdf", nom="Compte rendu", titre="Compte rendu", contenu="# Compte rendu\n\n- point 1\n- point 2")],
        [("content", "Voilà ton compte rendu en PDF.")],
    ])
    with _ouvrir(eva) as w:
        w.send_json({"text": "fais-moi un compte rendu de la réunion en document"})
        q, _ = _jusqua(w, {"question_request"})
        assert q["question"] == "Quel format ?" and q["choix"] == ["Word", "PDF"] and not q["plusieurs"]
        w.send_json({"type": "question_response", "id": q["id"], "reponses": ["PDF"]})
        res, _ = _jusqua(w, {"tool_result"})
        assert res["name"] == "poser_question" and res["result"]["reponse"] == "PDF"
        doc, _ = _jusqua(w, {"tool_result"})
        assert doc["name"] == "document_creer" and doc["result"]["verification"]["ok"], doc
        assert doc["result"]["path"].startswith("exports/") and doc["result"]["download"]
        _jusqua(w, {"done"})
    assert "poser_question" in vus[0]["tools"] and "document_creer" in vus[0]["tools"]
    r = eva["c"].get(doc["result"]["download"].replace("path=", "path="), headers=eva["H"](eva["t"]["alice"]))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_reponse_ecrite_au_lieu_de_cliquer(eva, monkeypatch):
    _scenario(monkeypatch, [
        [_appel("poser_question", question="Pour combien de personnes ?", choix=["2", "4"])],
        [("content", "Noté, pour 6.")],
    ])
    with _ouvrir(eva) as w:
        w.send_json({"text": "fais une liste de courses"})
        _jusqua(w, {"question_request"})
        w.send_json({"text": "pour 6 en fait"})
        _jusqua(w, {"question_closed"})
        res, _ = _jusqua(w, {"tool_result"})
        assert res["result"]["reponse"] == "pour 6 en fait"
        _jusqua(w, {"done"})


def test_action_critique_jamais_toujours(eva, monkeypatch):
    from app import autorisations
    _scenario(monkeypatch, [
        [_appel("fs_delete", path="exports/rien.txt")],
        [("content", "D'accord.")],
    ])
    with _ouvrir(eva) as w:
        w.send_json({"text": "supprime le fichier exports/rien.txt"})
        conf, _ = _jusqua(w, {"confirm_request"})
        assert conf["critique"] is True
        w.send_json({"type": "confirm_response", "approved": True, "always": True})
        _jusqua(w, {"done"})
    assert not eva["c"].portal.call(autorisations.allowed, "alice", "fs_delete")
    assert "fs_delete" not in eva["c"].portal.call(autorisations.lister, "alice")


def test_plan_et_verification_avant_de_conclure(eva, monkeypatch):
    vus = _scenario(monkeypatch, [
        [_appel("plan_taches", titre="Budget", etapes=["Chercher les prix", "Faire le tableau", "Vérifier"])],
        [_appel("plan_taches", maj=[{"n": 1, "etat": "fait"}, {"n": 2, "etat": "fait"}])],
        [("content", "C'est prêt.")],                                   # conclut trop tôt : « Vérifier » n'est pas coché
        [_appel("plan_taches", maj=[{"n": 3, "etat": "fait"}])],
        [("content", "Vérifié : tout est bon.")],
    ])
    c, t = eva["c"], eva["t"]["alice"]
    sid = c.post("/api/sessions", json={"title": "plan"}, headers=eva["H"](t)).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={t}&session={sid}") as w:
        w.send_json({"text": "prépare le budget en plusieurs étapes"})
        plans_vus, texte = [], ""
        for _ in range(300):
            ev = w.receive_json()
            if ev.get("type") == "plan":
                plans_vus.append([e["etat"] for e in ev["plan"]["etapes"]])
            if ev.get("type") == "token":
                texte += ev["text"]
            if ev.get("type") == "done":
                break
    assert plans_vus[0] == ["a_faire"] * 3 and plans_vus[-1] == ["fait"] * 3
    assert "Vérification automatique" in vus[3]["history"][-1]["content"] and "Vérifier" in vus[3]["history"][-1]["content"]
    assert texte == "C'est prêt.\n\nVérifié : tout est bon."
    data = c.get(f"/api/sessions/{sid}/messages", headers=eva["H"](t)).json()
    assert data["plan"]["titre"] == "Budget" and data["messages"][-1]["content"] == "C'est prêt.\n\nVérifié : tout est bon."


def test_tache_de_fond(eva, monkeypatch):
    import time as _t
    from app.harness import loop
    principal = iter([[_appel("tache_de_fond", titre="Comparatif", consigne="Compare A et B, fais un Excel et envoie-le par e-mail à x@y.fr")],
                      [("content", "C'est lancé en fond.")]])
    fond = iter([[_appel("document_creer", format="xlsx", nom="Comparatif", feuilles=[{"nom": "A vs B", "lignes": [["Critère", "A", "B"], ["Prix", "10", "12"]]}])],
                 [_appel("gmail_send", to="x@y.fr", subject="s", body="b")],
                 [("content", "Comparatif terminé : A est moins cher.")]])

    async def flux(history, tools=None, model=None):
        src = fond if "TÂCHE EN FOND" in history[0]["content"] else principal
        for ev in next(src):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    c, t = eva["c"], eva["t"]["alice"]
    H = eva["H"](t)
    sid = c.post("/api/sessions", json={"title": "fond"}, headers=H).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={t}&session={sid}") as w:
        w.send_json({"text": "compare A et B en fond et préviens-moi quand c'est fini"})
        res, _ = _jusqua(w, {"tool_result"})
        assert res["name"] == "tache_de_fond" and res["result"]["ok"], res
        _jusqua(w, {"done"})
        fin = _t.time() + 20
        while _t.time() < fin:
            lst = c.get("/api/taches-fond", headers=H).json()["taches"]
            if lst and lst[0]["etat"] not in ("en_attente", "en_cours"):
                break
            c.portal.call(lambda: __import__("asyncio").sleep(0.2))
        assert lst[0]["etat"] == "fini", lst
        assert lst[0]["fichiers"][0]["path"].startswith("exports/Comparatif") and lst[0]["refus"] == ["gmail_send"]
        ev, _ = _jusqua(w, {"proactive"})
        assert "Tâche en fond terminée : Comparatif" in ev["text"] and "A est moins cher" in ev["text"] and "gmail_send" in ev["text"]
    msgs = c.get(f"/api/sessions/{sid}/messages", headers=H).json()["messages"]
    assert "Tâche en fond terminée" in msgs[-1]["content"]
    assert c.get("/api/taches-fond", headers=eva["H"](eva["t"]["bob"])).json()["taches"] == []       # pas celles des autres
