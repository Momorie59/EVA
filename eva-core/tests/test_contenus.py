"""Suivi de contenus : idées, étapes, partage, annonce Discord, outils d'EVA, module coupé."""
from datetime import date, timedelta

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_contenus(eva, monkeypatch):
    from app import connecteurs as cx, profiles
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    A, B = H(t["alice"]), H(t["bob"])
    assert c.get("/api/contenus", headers=A).status_code == 404
    c.put("/api/modules", json={"contenus": True}, headers=A)
    tok = profiles.user_var.set("alice")
    try:
        idee = c.portal.call(lambda: m.registry.get("contenu_idee").execute(titre="Test du NAS ThinkCentre", plateformes=["youtube", "pas-une"]))
    finally:
        profiles.user_var.reset(tok)
    assert idee["etat"] == "Idée"
    demain = (date.today() + timedelta(days=2)).isoformat()
    r = c.patch(f"/api/contenus/{idee['id']}", json={"etat": "montage", "date_prevue": demain}, headers=A).json()
    assert r["etat"] == "montage" and r["plateformes"] == ["youtube"]
    assert c.get("/api/contenus", headers=B).json()["contenus"] == []                       # privé
    assert c.patch(f"/api/contenus/{idee['id']}", json={"etat": "publie"}, headers=B).status_code == 400
    c.patch(f"/api/contenus/{idee['id']}", json={"partage": True}, headers=A)
    vu = c.get("/api/contenus", headers=B).json()
    assert [x["titre"] for x in vu["contenus"]] == ["Test du NAS ThinkCentre"]               # chaîne de la famille
    assert c.patch(f"/api/contenus/{idee['id']}", json={"partage": False}, headers=B).status_code == 400   # seul l'auteur
    assert c.delete(f"/api/contenus/{idee['id']}", headers=B).status_code == 403
    tok = profiles.user_var.set("alice")
    try:
        res = c.portal.call(lambda: m.registry.get("contenu_lister").execute())
        assert res["cette_semaine"][0]["titre"] == "Test du NAS ThinkCentre" and res["par_etape"]["Montage"] == 1
        av = c.portal.call(lambda: m.registry.get("contenu_avancer").execute(id=idee["id"], etat="publie", lien="https://youtu.be/abc", notes="Bonne audience"))
    finally:
        profiles.user_var.reset(tok)
    assert av["etat"] == "Publié"
    pub = c.get("/api/contenus?etat=publie", headers=A).json()["contenus"][0]
    assert pub["date_publiee"] == date.today().isoformat() and pub["lien"] == "https://youtu.be/abc" and "Bonne audience" in pub["notes"]
    envoye = {}

    async def faux_discord(salon, message):
        envoye.update(salon=salon, message=message)
        return {"ok": True, "salon": "annonces"}
    monkeypatch.setattr(cx, "discord_envoyer", faux_discord)
    assert c.post(f"/api/contenus/{idee['id']}/annoncer", json={}, headers=A).json()["ok"]
    assert envoye["message"] == "🎬 Nouveau : **Test du NAS ThinkCentre** (Youtube)\nhttps://youtu.be/abc"
    assert c.post("/api/contenus", json={"titre": " "}, headers=A).status_code == 400
