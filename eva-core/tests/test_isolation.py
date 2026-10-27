"""Isolation entre personnes et quotas, sur l'application EVA complète et une vraie base Postgres.

Lancement : EVA_TEST_PG=postgresql://eva@127.0.0.1:55432/postgres python -m pytest tests/test_isolation.py -q
Sans EVA_TEST_PG, ces tests sont ignorés."""
from pathlib import Path

from integration_pg import requiert_pg

pytestmark = requiert_pg


def _message(eva, sid, texte, role="user"):
    from app.memory import save_message
    return eva["c"].portal.call(save_message, sid, role, texte)


# ------------------------------------------------------------------ conversations
def test_conversations_cloisonnees(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    sid = c.post("/api/sessions", json={"title": "Projet secret de Bob"}, headers=H(t["bob"])).json()["id"]
    _message(eva, sid, "Mon code de portail est 4242")
    listes = {n: [s["id"] for s in c.get("/api/sessions", headers=H(t[n])).json()["sessions"]] for n in t}
    assert sid in listes["bob"] and sid in listes["alice"] and sid not in listes["carla"]
    assert c.get(f"/api/sessions/{sid}/messages", headers=H(t["carla"])).status_code in (403, 404)
    assert c.get(f"/api/sessions/{sid}/messages", headers=H(t["bob"])).status_code == 200
    assert c.delete(f"/api/sessions/{sid}", headers=H(t["carla"])).status_code in (403, 404)
    found = c.get("/api/sessions/search?q=portail", headers=H(t["carla"])).json()["results"]
    assert not any(r.get("id") == sid or r.get("session_id") == sid for r in found)


# ------------------------------------------------------------------ fichiers
def test_fichiers_deposes_et_telechargement(eva):
    c, H, t, ws = eva["c"], eva["H"], eva["t"], eva["ws"]
    r = c.post("/api/uploads?name=releve-bob.pdf", content=b"%PDF-1.4 releve de Bob", headers=H(t["bob"]))
    assert r.status_code == 200
    chemin = r.json()["path"]
    url = f"/api/files/download?path={chemin}"
    assert c.get(url, headers=H(t["bob"])).status_code == 200
    assert c.get(url, headers=H(t["alice"])).status_code == 200
    assert c.get(url, headers=H(t["carla"])).status_code == 403
    for interdit in ("papiers/papiers.db", "backups/eva-20261022-080000.zip", "skills/x/SKILL.md"):
        (ws / interdit).parent.mkdir(parents=True, exist_ok=True)
        (ws / interdit).write_bytes(b"secret")
        assert c.get(f"/api/files/download?path={interdit}", headers=H(t["carla"])).status_code == 403
        assert c.get(f"/api/files/download?path={interdit}", headers=H(t["alice"])).status_code == 200


def test_papiers_reserves(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    assert c.get("/api/papiers/etat", headers=H(t["carla"])).status_code == 403
    assert c.get("/api/papiers/etat", headers=H(t["alice"])).status_code == 200


def test_outils_fichiers_cloisonnes(eva):
    from app.harness.cloisonnement import RegistreCloisonne
    c, m, ws = eva["c"], eva["m"], eva["ws"]
    (ws / "uploads").mkdir(exist_ok=True)
    bob = RegistreCloisonne(m.registry, ws, "bob", "user")
    carla = RegistreCloisonne(m.registry, ws, "carla", "user")
    run = lambda reg, outil, **kw: c.portal.call(lambda: reg.get(outil).execute(**kw))   # noqa: E731
    assert "refusé" in run(carla, "fs_read", path="uploads/releve-bob.pdf")["error"]
    assert "refusé" in run(carla, "fs_read", path="papiers/papiers.db")["error"]
    assert "refusé" in run(carla, "fs_list", path=".")["error"]
    assert "refusé" in run(carla, "fs_tree", path="projets")["error"]
    assert "refusé" in run(carla, "fs_write", path="skills/piege/SKILL.md", content="x")["error"]
    assert "content" in run(bob, "fs_read", path="uploads/releve-bob.pdf") or "text" in run(bob, "fs_read", path="uploads/releve-bob.pdf")
    noms = [e["name"] for e in run(carla, "fs_list", path="uploads")["entries"]]
    assert "releve-bob.pdf" not in noms                                     # la liste est filtrée
    assert "error" not in run(carla, "project_init", slug="potager", name="Potager", description="Mon potager")
    assert "refusé" in run(bob, "fs_read", path="projets/potager/README.md")["error"]
    assert "refusé" in run(bob, "project_log_decision", slug="potager", title="x", decision="y", reason="z")["error"]
    assert "refusé" in run(bob, "code_agent", slug="potager", consigne="lis tout le code de Carla")["error"]
    r = run(carla, "file_deliver", name="liste.txt", content="tomates")
    from app import acces
    assert acces.proprietaire(ws, "exports", Path(r["path"]).name) == "carla"
    assert c.get(f"/api/files/download?path={r['path']}", headers=eva["H"](eva["t"]["bob"])).status_code == 403


# ------------------------------------------------------------------ quotas
def test_quotas(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    deja = c.get("/api/access/quotas", headers=H(t["alice"])).json()["usage"]["carla"]["heure"]   # messages d'autres tests
    lim = deja + 2
    assert c.put("/api/access/quotas", json={"personnes": {"carla": {"heure": lim, "jour": lim + 50}}}, headers=H(t["carla"])).status_code == 403
    assert c.put("/api/access/quotas", json={"personnes": {"carla": {"heure": lim, "jour": lim + 50}}}, headers=H(t["alice"])).status_code == 200
    sid = c.post("/api/sessions", json={"title": "Carla"}, headers=H(t["carla"])).json()["id"]
    _message(eva, sid, "un")
    _message(eva, sid, "deux")
    usage = c.get("/api/access/quotas", headers=H(t["alice"])).json()["usage"]
    assert usage["carla"]["heure"] == lim
    with c.websocket_connect(f"/ws/chat?token={t['carla']}&session={sid}") as w:
        w.send_json({"text": "trois ?"})
        texte = ""
        for _ in range(50):
            ev = w.receive_json()
            if ev.get("type") == "token":
                texte += ev.get("text", "")
            if ev.get("type") == "done":
                break
    assert f"limite de {lim} messages par heure" in texte
    c.put("/api/access/quotas", json={"personnes": {}}, headers=H(t["alice"]))      # les tests suivants ne sont pas limités
    from app import quotas
    assert c.portal.call(quotas.depasse, "alice", "admin") is None          # l'administrateur n'a pas de limite
