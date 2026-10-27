"""Banc d'essai des outils (modèle simulé, rien d'exécuté) et corbeille des conversations (30 jours)."""
import time

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_banc_essai(eva, monkeypatch):
    from app import banc_essai, ollama_client
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    vus = []

    async def modele(messages, tools=None, model=None):
        phrase = messages[-1]["content"]
        noms = [t["function"]["name"] for t in (tools or [])]
        vus.append((phrase, model, noms))
        if "temps" in phrase:
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "weather_get", "arguments": {}}}]}}
        if "lumière" in phrase:
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "list_add", "arguments": {}}}]}}
        return {"message": {"content": "Bonjour !"}}
    monkeypatch.setattr(ollama_client, "chat_once", modele)
    monkeypatch.setattr(banc_essai, "CAS", [("Quel temps fait-il demain à Lille ?", {"weather_get"}), ("Allume la lumière du salon", {"device_control"}),
                                           ("Bonjour EVA, comment ça va ?", {banc_essai.AUCUN}), ("Rappelle-moi de sortir le gâteau dans 10 minutes", {"rappel_creer"}),
                                           ("Fais un truc introuvable", {"outil_qui_n_existe_pas"})])
    r = c.post("/api/self/banc", json={"modele": "qwen2.5:7b"}, headers=A).json()
    assert r["ok"] and r["modele"] == "qwen2.5:7b"
    for _ in range(100):
        d = c.get("/api/self/banc", headers=A).json()
        if not d["etat"]["en_cours"] and d["passages"]:
            break
        time.sleep(0.1)
    p = d["passages"][0]
    v = {l["phrase"][:10]: l["verdict"] for l in p["lignes"]}
    assert p["modele"] == "qwen2.5:7b" and p["score"] == 2 and p["total"] == 5, p
    assert v == {"Quel temps": "ok", "Allume la ": "mauvais_outil", "Bonjour EV": "ok", "Rappelle-m": "aucun_outil", "Fais un tr": "pas_propose"}
    assert all(m == "qwen2.5:7b" for _p, m, _n in vus) and "weather_get" in vus[0][2]
    assert c.post("/api/self/banc", json={}, headers=eva["H"](eva["t"]["bob"])).status_code == 403
    assert len(banc_essai.CAS) == 5


def test_corbeille_des_conversations(eva):
    from app import sessions
    c, H, t = eva["c"], eva["H"], eva["t"]
    B = H(t["bob"])
    sid = c.post("/api/sessions", json={}, headers=B).json()["id"]
    c.portal.call(lambda: sessions.ensure_session(sid, "Ma conversation à garder", "bob"))
    assert c.delete(f"/api/sessions/{sid}", headers=B).json()["ok"]
    assert sid not in [s["id"] for s in c.get("/api/sessions", headers=B).json()["sessions"]]
    cb = c.get("/api/sessions/corbeille", headers=B).json()
    assert cb["jours"] == 30 and [x["id"] for x in cb["conversations"]] == [sid]
    assert sid not in [x["id"] for x in c.get("/api/sessions/corbeille", headers=H(t["carla"])).json()["conversations"]]
    assert c.post("/api/sessions/corbeille/restaurer", json={"ids": [sid]}, headers=H(t["carla"])).json()["restaurees"] == 0
    assert c.post("/api/sessions/corbeille/restaurer", json={"ids": [sid]}, headers=B).json()["restaurees"] == 1
    assert sid in [s["id"] for s in c.get("/api/sessions", headers=B).json()["sessions"]]
    c.delete(f"/api/sessions/{sid}", headers=B)

    async def vieillir():
        from app.db import get_pool
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE sessions SET supprime_le = now() - interval '31 days' WHERE id=$1", sid)
        return await sessions.purger_corbeille()
    assert c.portal.call(vieillir) == 1
    assert c.get("/api/sessions/corbeille", headers=B).json()["conversations"] == []
    sid2 = c.post("/api/sessions", json={}, headers=B).json()["id"]
    c.delete(f"/api/sessions/{sid2}", headers=B)
    assert c.post("/api/sessions/corbeille/vider", json={"tout": True}, headers=B).json()["effacees"] == 1
