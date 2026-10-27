"""Conversations : suppression en masse, rattachement à un projet, fil conducteur (EVA complète + Postgres)."""
from pathlib import Path

from integration_pg import requiert_pg

from app import fil

pytestmark = requiert_pg


def _sql(eva, q, *args):
    from app.db import get_pool

    async def run():
        async with get_pool().acquire() as conn:
            return await conn.fetch(q, *args)
    return eva["c"].portal.call(run)


def _conv(eva, qui, titre, n=2):
    c = eva["c"]
    sid = c.post("/api/sessions", json={"title": titre}, headers=eva["H"](eva["t"][qui])).json()["id"]
    for i in range(n):
        _sql(eva, "INSERT INTO messages (session_id, role, content) VALUES ($1,$2,$3)", sid,
             "user" if i % 2 == 0 else "assistant", f"{titre} message {i}")
    return sid


def test_debut_fenetre():
    h = [{"role": "system"}] + [{"role": "user" if i % 2 == 0 else "assistant"} for i in range(20)]
    assert fil.debut_fenetre(h, 4) == 17 and h[17]["role"] == "user"           # 4 derniers messages, en commençant par la personne
    h2 = [{"role": "system"}, {"role": "user"}, {"role": "assistant", "tool_calls": [1]}, {"role": "tool"}, {"role": "assistant"},
          {"role": "user"}, {"role": "assistant"}]
    assert fil.debut_fenetre(h2, 2) == 5
    assert fil.debut_fenetre(h2, 3) == 5                                        # jamais au milieu d'un tour d'outils
    assert fil.debut_fenetre(h2, 5) == 1                                        # le tour entier (5 messages) tient


def test_suppression_en_masse(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    a = [_conv(eva, "bob", f"Bob {i}") for i in range(3)]
    carla = _conv(eva, "carla", "Carla secrète")
    r = c.post("/api/sessions/supprimer", json={"ids": [a[0], carla]}, headers=H(t["bob"])).json()
    assert r["supprimees"] == 1                                                  # celle de Carla est ignorée
    assert _sql(eva, "SELECT 1 FROM sessions WHERE id=$1", carla)
    assert c.post("/api/sessions/supprimer", json={"personne": "carla"}, headers=H(t["bob"])).status_code == 403
    c.post("/api/sessions/supprimer", json={"tout": True}, headers=H(t["bob"]))
    assert _sql(eva, "SELECT 1 FROM sessions WHERE owner='bob' AND supprime_le IS NULL") == []           # à la corbeille…
    assert c.get("/api/sessions", headers=H(t["bob"])).json()["sessions"] == []
    assert c.post("/api/sessions/corbeille/vider", json={"tout": True}, headers=H(t["bob"])).json()["effacees"] == 3
    assert _sql(eva, "SELECT 1 FROM sessions WHERE owner='bob'") == []                                    # …puis effacées pour de bon
    assert _sql(eva, "SELECT 1 FROM messages WHERE session_id = ANY($1::text[])", a) == []
    assert _sql(eva, "SELECT 1 FROM sessions WHERE id=$1", carla)                # Carla n'est pas touchée
    assert c.post("/api/sessions/supprimer", json={"personne": "carla"}, headers=H(t["alice"])).json()["supprimees"] >= 1
    assert _sql(eva, "SELECT 1 FROM sessions WHERE id=$1 AND supprime_le IS NULL", carla) == []


def test_rattacher_a_un_projet(eva):
    c, H, t, ws, m = eva["c"], eva["H"], eva["t"], eva["ws"], eva["m"]
    from app.harness.cloisonnement import RegistreCloisonne
    reg = RegistreCloisonne(m.registry, ws, "carla", "user")
    c.portal.call(lambda: reg.get("project_init").execute(slug="voyage", name="Voyage", description="Rome en mai"))
    sid = _conv(eva, "carla", "Hôtels à Rome", 4)
    bob = _conv(eva, "bob", "Bob veut voir")
    assert c.post("/api/sessions/rattacher", json={"ids": [bob], "project": "voyage"}, headers=H(t["bob"])).status_code == 403
    assert c.patch(f"/api/sessions/{sid}", json={"project": "inexistant"}, headers=H(t["carla"])).status_code == 404
    assert c.patch(f"/api/sessions/{sid}", json={"project": "voyage"}, headers=H(t["carla"])).status_code == 200
    s = next(x for x in c.get("/api/sessions", headers=H(t["carla"])).json()["sessions"] if x["id"] == sid)
    assert s["project"] == "voyage"
    assert (ws / "projets" / "voyage" / "FIL.md").is_file()
    bloc = c.portal.call(fil.bloc_consignes, sid, ws)
    assert "projet « voyage »" in bloc and "Hôtels à Rome" in bloc
    c.patch(f"/api/sessions/{sid}", json={"project": ""}, headers=H(t["carla"]))
    assert "voyage" not in c.portal.call(fil.bloc_consignes, sid, ws)


def test_fil_conducteur(eva, monkeypatch):
    c, H, t, ws = eva["c"], eva["H"], eva["t"], eva["ws"]
    vus = []

    async def faux_chat(messages, tools=None, model=None):
        vus.append(messages[-1]["content"])
        return {"role": "assistant", "content": "- Objectif : organiser le voyage à Rome\n- Décidé : hôtel près du Colisée"}
    monkeypatch.setattr("app.ollama_client.chat_once", faux_chat)
    sid = _conv(eva, "carla", "Organisation", 20)
    e = c.portal.call(fil.mettre_a_jour, sid, ws)
    assert "Colisée" in e["resume"] and e["en_attente"] == fil.FENETRE            # les 8 derniers restent tels quels
    assert "Organisation message 0" in vus[0] and "Organisation message 19" not in vus[0]
    hist = [{"role": "system", "content": "consignes"}] + [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(20)]
    envoi = c.portal.call(fil.fenetre, sid, hist)
    assert len(envoi) == 1 + fil.FENETRE and envoi[0]["content"] == "consignes"
    assert "Colisée" in c.portal.call(fil.bloc_consignes, sid, ws)
    # trop peu de nouveaux échanges : pas d'appel au modèle
    n = len(vus)
    c.portal.call(fil.mettre_a_jour, sid, ws)
    assert len(vus) == n
    # la personne corrige son fil, et le compile à la demande
    assert c.put(f"/api/sessions/{sid}/fil", json={"resume": "- Hôtel : Via Cavour"}, headers=H(t["carla"])).json()["resume"] == "- Hôtel : Via Cavour"
    assert c.get(f"/api/sessions/{sid}/fil", headers=H(t["bob"])).status_code == 404       # pas le fil des autres
    r = c.post(f"/api/sessions/{sid}/fil", headers=H(t["carla"])).json()
    assert r["en_attente"] == 0 and "Colisée" in r["resume"]
    # sans fil : on garde jusqu'au plafond (rien n'est perdu)
    sid2 = _conv(eva, "carla", "Sans fil", 4)
    assert len(c.portal.call(fil.fenetre, sid2, hist)) == 21
    assert Path(ws).is_dir()


def test_compilation_de_nuit_et_fil_general(eva, monkeypatch):
    from app import compilation, memoire
    appels = {"fil": 0, "souvenirs": 0}

    async def faux_chat(messages, tools=None, model=None):
        if "fil conducteur" in messages[0]["content"]:
            appels["fil"] += 1
            return {"role": "assistant", "content": "- Sujet : la fête d'anniversaire d'Léa\n- Décidé : samedi 14 h"}
        appels["souvenirs"] += 1
        return {"role": "assistant", "content": '[{"texte": "Ma fille Léa a 8 ans", "sorte": "fait"}]'}
    monkeypatch.setattr("app.ollama_client.chat_once", faux_chat)
    c, H, t, ws = eva["c"], eva["H"], eva["t"], eva["ws"]
    courte = _conv(eva, "carla", "Anniversaire", 2)                                  # courte : jamais résumée jusqu'ici
    _sql(eva, "UPDATE messages SET content='ma fille Léa a 8 ans, on fête son anniversaire samedi' WHERE session_id=$1 AND role='user'", courte)
    _sql(eva, "UPDATE sessions SET updated_at = now() - interval '2 hours' WHERE id=$1", courte)
    bilan = c.portal.call(compilation.compiler, ws)
    assert bilan["conversations"] >= 1 and bilan["souvenirs"] >= 1 and bilan["erreurs"] == 0
    assert "anniversaire d'Léa" in c.get(f"/api/sessions/{courte}/fil", headers=H(t["carla"])).json()["resume"]
    assert any("Léa a 8 ans" in s["texte"] for s in c.portal.call(memoire.lister, "carla"))
    # deuxième passe : rien de nouveau, aucun appel au modèle
    n = dict(appels)
    bilan2 = c.portal.call(compilation.compiler, ws)
    assert appels == n and bilan2["conversations"] == 0 and bilan2["souvenirs"] == 0
    # nouvelle conversation de Carla : EVA reçoit le fil général ; Bob ne voit pas celles de Carla
    nouvelle = c.post("/api/sessions", json={"title": "Nouvelle"}, headers=H(t["carla"])).json()["id"]
    assert "anniversaire d'Léa" in c.portal.call(fil.bloc_consignes, nouvelle, ws)
    chez_bob = c.post("/api/sessions", json={"title": "Bob"}, headers=H(t["bob"])).json()["id"]
    assert "Léa" not in c.portal.call(fil.bloc_consignes, chez_bob, ws)
    # réglages et bouton : administrateur seulement
    assert c.put("/api/compilation", json={"heure": 4}, headers=H(t["bob"])).status_code == 403
    assert c.put("/api/compilation", json={"heure": 4}, headers=H(t["alice"])).json()["heure"] == 4
    assert compilation.fenetre(3) == {3, 4, 5} and compilation.fenetre(22) == {22, 23, 0}
    _sql(eva, "DELETE FROM memoire WHERE owner='carla'")                              # les autres tests partent d'une mémoire vide
