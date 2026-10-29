"""Inventaire et prêts : ranger, retrouver, prêter, rendre, objets privés, module coupé."""


def test_inventaire(eva):
    from app import inventaire
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    assert c.get("/api/inventaire", headers=H(t["alice"])).status_code == 404                       # module coupé par défaut
    c.put("/api/modules", json={"inventaire": True}, headers=H(t["alice"]))
    A, B = H(t["alice"]), H(t["bob"])
    o = c.post("/api/inventaire", json={"nom": "La perceuse", "emplacement": "garage > établi > tiroir 2"}, headers=A).json()
    assert o["emplacement"] == "Garage › Établi › Tiroir 2" and o["nouveau"]
    o2 = c.post("/api/inventaire", json={"nom": "perceuses", "emplacement": "cellier"}, headers=B).json()
    assert not o2["nouveau"] and o2["id"] == o["id"] and o2["emplacement"] == "Cellier"                # même objet, déplacé
    c.post("/api/inventaire", json={"nom": "Journal intime", "emplacement": "chambre", "prive": True}, headers=B)
    assert not any(x["nom"] == "Journal intime" for x in c.get("/api/inventaire", headers=A).json()["objets"])   # privé
    ou = c.portal.call(lambda: inventaire.ou_est("alice", "où est la perceuse"))
    assert ou["trouve"] is False or "Cellier" in ou["phrase"]
    ou = c.portal.call(lambda: inventaire.ou_est("alice", "perceuse"))
    assert "Cellier" in ou["phrase"]
    p = c.post("/api/inventaire/prets", json={"objet": "perceuse", "personne": "Paul", "retour": "2020-01-01"}, headers=A).json()
    assert p["dans_inventaire"] and p["en_retard"]
    ou = c.portal.call(lambda: inventaire.ou_est("alice", "perceuse"))
    assert "prêté à Paul" in ou["phrase"]
    c.post("/api/inventaire/prets", json={"objet": "scie sauteuse", "personne": "Marie", "sens": "emprunte"}, headers=A)
    assert "emprunté à Marie" in c.portal.call(lambda: inventaire.ou_est("alice", "scie"))["phrase"]
    rendus = c.portal.call(lambda: inventaire.rendre("alice", "perceuse", "paul"))
    assert len(rendus) == 1
    assert "Cellier" in c.portal.call(lambda: inventaire.ou_est("alice", "perceuse"))["phrase"]
    assert c.post(f"/api/inventaire/prets/{p['id']}/rendu", headers=A).status_code == 404               # déjà rendu
    r = c.portal.call(lambda: m.registry.get("inventaire_preter").execute(objet="tondeuse", personne="Luc"))
    assert r["ok"] and not r["dans_inventaire"]
    assert any("tondeuse" in x for x in c.portal.call(lambda: m.registry.get("inventaire_prets").execute())["prets"])
    assert c.delete(f"/api/inventaire/{o['id']}", headers=A).json()["ok"]
    c.put("/api/modules", json={"inventaire": False}, headers=A)
