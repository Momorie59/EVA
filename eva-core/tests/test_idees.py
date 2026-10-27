"""Point 5 : routines de la maison (heure, capteur), listes privées, rayons du magasin, TV / Chromecast."""
from datetime import datetime
from zoneinfo import ZoneInfo

from integration_pg import requiert_pg


def test_rayons():
    from app.rayons import rayon, ranger
    assert rayon("2 litres de lait") == "Crèmerie, œufs" and rayon("pommes de terre") == "Fruits et légumes"
    assert rayon("sauce tomate") == "Épicerie salée" and rayon("papier toilette") == "Hygiène, beauté" and rayon("truc") == "Divers"
    assert [r for r, _ in ranger(["lessive", "pain", "pommes"])] == ["Fruits et légumes", "Boulangerie", "Entretien, maison"]


def test_jours_heures():
    from app import routines
    assert routines.jours_de("en semaine") == [0, 1, 2, 3, 4] and routines.jours_de("le week-end") == [5, 6]
    assert routines.jours_de("lundi et jeudi") == [0, 3] and routines.jours_de("") == list(range(7))
    assert routines.heure_de("7h30") == "07:30" and routines.heure_de("22:00") == "22:00"
    assert routines._vrai("26.5", ">", "26") and not routines._vrai("on", "=", "off") and routines._vrai("on", "=", "ouverte")
    assert routines._vrai("below_horizon", "=", "nuit")


@requiert_pg
def test_routines(eva, monkeypatch):
    from app import devices, homeassistant, routines
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    fait = []

    async def scene(q):
        return {"name": "Bonne nuit", "id": 1} if "nuit" in q.lower() else None

    async def lancer(s):
        fait.append(("scene", s["name"]))
        return {"results": []}

    async def piloter(q, action="state", value=None, room="", dtype=""):
        fait.append(("appareil", q, action))
        return {"ok": True}

    async def rien():
        return []
    monkeypatch.setattr(devices, "find_scene", scene)
    monkeypatch.setattr(devices, "run_scene", lancer)
    monkeypatch.setattr(devices, "control", piloter)
    monkeypatch.setattr(devices, "reload", rien)
    monkeypatch.setattr(devices, "scene_needs_confirm", lambda n: False)
    monkeypatch.setattr(devices, "needs_confirm", lambda a: "volet" in a.get("device", ""))
    r = c.portal.call(lambda: eva["m"].registry.get("routine_creer").execute(nom="Bonne nuit", heure="22h", jours="tous les jours", scene="bonne nuit"))
    assert r["ok"] and r["routine"] == "tous les jours à 22 h → scène « bonne nuit »", r
    v = c.post("/api/home/routines", json={"nom": "Ventilo", "declencheur": {"type": "capteur", "entite": "sensor.salon_temperature",
                                                                            "condition": ">", "valeur": "26"},
                                          "actions": [{"type": "appareil", "appareil": "ventilateur", "action": "on"},
                                                      {"type": "appareil", "appareil": "volet salon", "action": "off"}]}, headers=A).json()
    assert v["id"]
    assert c.post("/api/home/routines", json={"nom": "x", "declencheur": {"type": "heure", "heure": "25:00"}, "actions": [{"type": "notifier", "texte": "a"}]},
                  headers=A).status_code == 400
    lst = c.get("/api/home/routines", headers=A).json()["routines"]
    assert {x["nom"] for x in lst} >= {"Bonne nuit", "Ventilo"}

    temp = {"v": "24"}

    async def etat(e):
        return {"state": temp["v"]}
    monkeypatch.setattr(homeassistant, "get_state", etat)
    tz = ZoneInfo("Europe/Paris")
    assert c.portal.call(lambda: routines.verifier(datetime(2026, 11, 2, 21, 59, tzinfo=tz))) == 0
    assert c.portal.call(lambda: routines.verifier(datetime(2026, 11, 2, 22, 0, tzinfo=tz))) == 1 and ("scene", "Bonne nuit") in fait
    assert c.portal.call(lambda: routines.verifier(datetime(2026, 11, 2, 22, 0, tzinfo=tz))) == 0             # une fois par minute
    temp["v"] = "27"
    assert c.portal.call(lambda: routines.verifier(datetime(2026, 11, 2, 22, 1, tzinfo=tz))) == 1
    assert ("appareil", "ventilateur", "on") in fait and not any(f[1] == "volet salon" for f in fait if f[0] == "appareil")   # sensible : pas seul
    assert c.portal.call(lambda: routines.verifier(datetime(2026, 11, 2, 22, 2, tzinfo=tz))) == 0             # toujours vrai : pas de répétition
    v2 = next(x for x in c.get("/api/home/routines", headers=A).json()["routines"] if x["nom"] == "Ventilo")
    assert any("sensible" in x for x in v2["dernier"]["compte"])
    assert "en pause" in c.portal.call(lambda: eva["m"].registry.get("routine_gerer").execute(routine="ventilo", action="pause"))["info"]
    for x in c.get("/api/home/routines", headers=A).json()["routines"]:
        c.delete(f"/api/home/routines/{x['id']}", headers=A)


@requiert_pg
def test_listes_privees_et_rayons(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    A, B = H(t["alice"]), H(t["bob"])
    p = c.post("/api/lists", json={"name": "Idées cadeaux", "prive": True}, headers=A).json()
    assert p["prive"]
    c.post(f"/api/lists/{p['id']}/items", json={"items": ["un livre"]}, headers=A)
    assert p["id"] not in [l["id"] for l in c.get("/api/lists", headers=B).json()["lists"]]
    assert c.get(f"/api/lists/{p['id']}", headers=B).status_code == 404
    assert c.post(f"/api/lists/{p['id']}/items", json={"items": ["x"]}, headers=B).status_code == 404
    b = c.post("/api/lists", json={"name": "Idées cadeaux", "prive": True}, headers=B).json()     # même nom, autre personne
    assert b["id"] != p["id"]
    lst = c.get("/api/lists", headers=A).json()["lists"]
    assert next(l for l in lst if l["id"] == p["id"])["prive"] and next(l for l in lst if l["name"] == "Courses")["prive"] is False
    courses = next(l for l in lst if l["name"] == "Courses")
    c.post(f"/api/lists/{courses['id']}/items", json={"items": ["lessive", "2 litres de lait", "pommes"]}, headers=A)
    items = c.get(f"/api/lists/{courses['id']}", headers=B).json()["items"]
    assert {i["text"]: i["rayon"] for i in items}["lessive"] == "Entretien, maison"
    txt = c.get(f"/api/lists/{courses['id']}/texte", headers=A).json()["texte"]
    assert txt.index("Fruits et légumes") < txt.index("Crèmerie") < txt.index("Entretien") and "• lessive" in txt
    autre = next(i for i in c.get(f"/api/lists/{p['id']}", headers=A).json()["items"])
    assert c.delete(f"/api/lists/{courses['id']}/items/{autre['id']}", headers=A).json()["ok"] is False     # élément d'une autre liste
    from app import lists as L
    from app import profiles

    async def en_tant_que_alice():
        jeton = profiles.user_var.set("alice")
        try:
            return await eva["m"].registry.get("list_add").execute(items=["une écharpe"], list="cadeaux de Noël", prive=True)
        finally:
            profiles.user_var.reset(jeton)
    r = c.portal.call(en_tant_que_alice)
    assert r.get("privee") and r["list"] == "cadeaux de Noël"
    for lid in (p["id"], b["id"]):
        c.delete(f"/api/lists/{lid}", headers=A if lid == p["id"] else B)
    noel = next(l for l in c.get("/api/lists", headers=A).json()["lists"] if l["name"] == "cadeaux de Noël")
    assert noel["prive"] and noel["id"] not in [l["id"] for l in c.get("/api/lists", headers=B).json()["lists"]]
    c.delete(f"/api/lists/{noel['id']}", headers=A)
    c.post(f"/api/lists/{courses['id']}/clear-done", headers=A)
    assert L


def test_tv_youtube():
    from app import cast
    assert cast.id_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3") == "dQw4w9WgXcQ"
    assert cast.id_youtube("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ" and cast.id_youtube("dernière vidéo de Cyprien") is None


def test_coloriage():
    import re
    from app import images
    from app.harness.selection import GROUPS
    assert images.wants_image("creer moi un coloriage de banane") == "coloriage de banane"
    assert images.wants_image("une page à colorier de dinosaure") and images.wants_image("un mandala avec des fleurs")
    assert images.est_coloriage("coloriage de banane") and images.est_coloriage("banana coloring page") and not images.est_coloriage("une banane")
    assert any("image_generate" in noms and p.search("colorie une banane") for noms, p in GROUPS)
    assert re.search("line art", images.STYLE_COLORIAGE)


def test_coloriage_style_envoye(monkeypatch):
    import asyncio
    from app import images
    vu = {}

    class Rep:
        status_code = 200

        def json(self):
            import base64
            return {"images": [base64.b64encode(b"\\x89PNG").decode()]}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **k):
            vu.update(json or {})
            return Rep()
    monkeypatch.setattr(images.httpx, "AsyncClient", Client)
    try:
        asyncio.run(images.generate("coloriage de banane", {"url": "http://x", "kind": "a1111", "negative": "blurry", "model": "", "token": ""}))
    except Exception:  # noqa: BLE001 — le format de réponse importe peu ici
        pass
    assert "line art" in vu.get("prompt", "") and "shading" in vu.get("negative_prompt", "")


def test_liste_mes_recettes_sans_fichiers():
    from app.harness import selection as S
    noms = ["fs_list", "fs_read", "fs_tree", "recette_chercher", "recette_lire", "list_show", "rappel_lister", "docs_search"]
    assert "fs_list" not in S.select_tool_names(["liste moi mes recettes"], noms)
    assert "recette_chercher" in S.select_tool_names(["liste moi mes recette"], noms)
    assert "fs_list" in S.select_tool_names(["montre le fichier recettes.pdf"], noms)
    assert "fs_list" not in S.select_tool_names(["quels sont mes rappels ?"], noms)
