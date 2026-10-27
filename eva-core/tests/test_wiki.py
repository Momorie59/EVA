"""Wiki (module activable) : espaces famille/perso, historique, conflit d'édition, médias, outils d'EVA, droits."""
from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_module_coupe_par_defaut_puis_active(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    assert c.get("/api/wiki", headers=H(t["alice"])).status_code == 404                   # coupé par défaut
    assert c.put("/api/modules", json={"wiki": True}, headers=H(t["bob"])).status_code == 403
    r = c.put("/api/modules", json={"wiki": True}, headers=H(t["alice"])).json()
    assert next(m for m in r["modules"] if m["id"] == "wiki")["actif"] is True
    assert c.get("/api/wiki", headers=H(t["bob"])).status_code == 200


def test_pages_famille_perso_historique(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    c.put("/api/modules", json={"wiki": True}, headers=H(t["alice"]))
    p = c.post("/api/wiki", json={"espace": "famille", "titre": "Code wifi invités", "contenu": "Réseau **Maison-Invités**, mot de passe : soleil42"},
               headers=H(t["bob"])).json()
    perso = c.post("/api/wiki", json={"espace": "perso", "titre": "Mes idées cadeaux", "contenu": "Un vélo pour Léa"}, headers=H(t["bob"])).json()
    titres = {n: [x["titre"] for x in c.get("/api/wiki", headers=H(t[n])).json()["pages"]] for n in ("bob", "carla", "alice")}
    assert "Code wifi invités" in titres["carla"] and "Mes idées cadeaux" in titres["bob"]
    assert "Mes idées cadeaux" not in titres["carla"] and "Mes idées cadeaux" not in titres["alice"]   # perso : pas même l'admin
    assert c.get(f"/api/wiki/{perso['id']}", headers=H(t["carla"])).status_code == 404
    # Carla modifie la page famille : l'ancienne version est gardée et se restaure
    p2 = c.put(f"/api/wiki/{p['id']}", json={"contenu": "Réseau Maison-Invités, mot de passe : lune77", "base": p["updated_at"]},
               headers=H(t["carla"])).json()
    assert "lune77" in p2["contenu"] and p2["updated_by"] == "carla" and p2["versions"] == 1
    conflit = c.put(f"/api/wiki/{p['id']}", json={"contenu": "écrasé", "base": p["updated_at"]}, headers=H(t["bob"]))
    assert conflit.status_code == 409 and "carla" in conflit.json()["detail"]
    v = c.get(f"/api/wiki/{p['id']}/versions", headers=H(t["bob"])).json()["versions"]
    assert len(v) == 1 and v[0]["auteur"] == "bob"
    r = c.post(f"/api/wiki/{p['id']}/versions/{v[0]['id']}/restaurer", headers=H(t["bob"])).json()
    assert "soleil42" in r["contenu"] and r["versions"] == 2
    assert c.get("/api/wiki/titre?t=code wifi invités", headers=H(t["carla"])).json()["id"] == p["id"]
    # suppression : auteur ou admin seulement
    assert c.delete(f"/api/wiki/{p['id']}", headers=H(t["carla"])).status_code == 403
    assert c.delete(f"/api/wiki/{p['id']}", headers=H(t["alice"])).status_code == 200


def test_outils_eva_et_medias(eva):
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    c.put("/api/modules", json={"wiki": True}, headers=H(t["alice"]))
    c.post("/api/wiki", json={"espace": "famille", "titre": "Chaudière", "contenu": "Pour relancer la chaudière, appuyer 5 secondes sur le bouton reset rouge."},
           headers=H(t["alice"]))
    from app import profiles
    tok = profiles.user_var.set("carla")
    try:
        res = c.portal.call(lambda: m.registry.get("wiki_chercher").execute(q="relancer la chaudière"))
        assert res["pages"] and "reset rouge" in res["pages"][0]["contenu"]
        lu = c.portal.call(lambda: m.registry.get("wiki_lire").execute(titre="Chaudière"))
        assert "5 secondes" in lu["contenu"]
    finally:
        profiles.user_var.reset(tok)
    up = c.post("/api/medias?module=wiki&nom=schema.png", content=b"\x89PNG\r\n\x1a\nfaux", headers=H(t["bob"]))
    assert up.status_code == 200
    url = up.json()["url"]
    assert c.get(url).status_code == 200                                  # l'adresse suffit (pour afficher dans la page)
    assert c.get("/api/public/medias/0123456789abcdef0123456789abcdef.png").status_code == 404
    assert c.post("/api/medias?module=wiki&nom=virus.exe", content=b"MZ", headers=H(t["bob"])).status_code == 400
    c.put("/api/modules", json={"wiki": False}, headers=H(t["alice"]))
    assert c.get(url).status_code == 404 and c.get("/api/wiki", headers=H(t["bob"])).status_code == 404   # module coupé : tout disparaît
