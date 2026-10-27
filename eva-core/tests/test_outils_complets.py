"""Ce qu'EVA refusait à tort : photo de recette (dessinée ou existante), modifier et partager une recette, rappels et minuteurs,
tâches automatiques depuis la conversation, déplacer/supprimer un rendez-vous, carnets, illustrer le wiki, noter une dépense,
demandes d'évolution."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from integration_pg import requiert_pg

pytestmark = requiert_pg


def _png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 120, 40)).save(b, "PNG")
    return b.getvalue()


def _run(eva, nom, **kw):
    return eva["c"].portal.call(lambda: eva["m"].registry.get(nom).execute(**kw))


def test_recette_avec_photo_modifier_partager(eva, monkeypatch):
    from app import images, medias
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    c.put("/api/modules", json={"recettes": True, "wiki": True}, headers=A)
    vus = []

    async def config():
        return {"url": "http://imagegen:7860", "enhance": False}

    async def dessiner(prompt, cfg=None, negative=None):
        vus.append(prompt)
        return _png()
    monkeypatch.setattr(images, "get_config", config)
    monkeypatch.setattr(images, "generate", dessiner)
    r = _run(eva, "recette_creer", titre="Paella", personnes=4, prep_min=20, cuisson_min=30,
             ingredients=["300 g de riz", "1 poivron"], etapes=["Faire revenir.", "Cuire le riz."], photo="generer")
    assert r["creee"]["titre"] == "Paella" and "dessinée par EVA" in r["photo"], r
    assert "Paella" in vus[0] and "culinaire" in vus[0]
    rec = c.get(f"/api/recettes/{r['creee']['id']}", headers=A).json()
    photo1 = rec["photo"]
    assert photo1 and medias.chemin(photo1)[1].read_bytes()[:4] == b"\x89PNG"
    assert c.get(f"/api/public/medias/{photo1}").status_code == 200

    m = _run(eva, "recette_modifier", recette="paella", personnes=6, notes="Avec du chorizo.", photo="derniere")
    assert m["modifiee"]["titre"] == "Paella" and set(m["champs"]) >= {"personnes", "notes", "photo"}
    rec = c.get(f"/api/recettes/{r['creee']['id']}", headers=A).json()
    assert rec["personnes"] == 6 and rec["photo"] != photo1
    import pytest
    with pytest.raises(medias.MediaError):
        medias.chemin(photo1)                                            # l'ancienne photo est effacée du NAS

    rr = _run(eva, "recette_creer", titre="Paella au Cookeo", personnes=4, ingredients=["300 g de riz", "500 g de moules", "1 poivron"],
              etapes=["Mode Dorer : faire revenir le poivron.", "Ajouter le riz et les moules, cuisson sous pression 8 min."])
    x = _run(eva, "recette_modifier", recette="paella au cookeo", remplacer="moule", par="300 g de crevettes")
    assert "remplacé" in x["changement"] and "300 g crevettes" in " ".join(x["ingredients"]) or "300 g de crevettes" in " ".join(x["ingredients"]), x
    rec2 = c.get(f"/api/recettes/{rr['creee']['id']}", headers=A).json()
    assert "moule" not in str(rec2).lower() and "crevettes" in rec2["etapes"][1]["texte"]
    x = _run(eva, "recette_modifier", recette="paella au cookeo", remplacer="poivron", par="poulet")
    assert any("poulet" in i for i in x["ingredients"]) and "1 poulet" in x["ingredients"]
    x = _run(eva, "recette_modifier", recette="paella au cookeo", remplacer="poulet")
    rec2 = c.get(f"/api/recettes/{rr['creee']['id']}", headers=A).json()
    assert len(rec2["ingredients"]) == 2 and rec2["etapes"][0]["texte"] == "Mode Dorer : faire revenir.", rec2["etapes"]
    assert "n'apparaît pas" in _run(eva, "recette_modifier", recette="paella au cookeo", remplacer="chorizo", par="x")["error"]
    c.delete(f"/api/recettes/{rr['creee']['id']}", headers=A)

    p = _run(eva, "recette_partager", recette="Paella")
    assert p["lien"].startswith("/api/public/recettes/") and c.get(p["lien"]).status_code == 200
    assert "introuvable" in _run(eva, "recette_modifier", recette="Couscous", notes="x")["error"]

    async def sans_serveur():
        return {"url": "", "enhance": False}
    monkeypatch.setattr(images, "get_config", sans_serveur)
    r2 = _run(eva, "recette_creer", titre="Crêpes", ingredients=["250 g de farine"], etapes=["Mélanger."], photo="generer")
    assert r2["creee"] and "sans photo" in r2["photo"] and "serveur d'images" in r2["photo"]     # la recette est gardée quand même

    monkeypatch.setattr(images, "get_config", config)
    w = _run(eva, "wiki_ecrire", titre="Le potager", contenu="Tomates, courgettes.", image="generer")
    assert "Illustration ajoutée" in w["image"]
    page = c.get(f"/api/wiki/{w['creee']['id']}", headers=A).json()
    assert page["contenu"].startswith("![Le potager](/api/public/medias/")
    for rid in (r["creee"]["id"], r2["creee"]["id"]):
        c.delete(f"/api/recettes/{rid}", headers=A)
    c.delete(f"/api/wiki/{w['creee']['id']}", headers=A)
    c.put("/api/modules", json={"recettes": False, "wiki": False}, headers=A)


def test_rappels_et_minuteurs(eva, monkeypatch):
    from app import rappels
    from app.connections import connection_manager
    c = eva["c"]
    r = _run(eva, "rappel_creer", texte="sortir le gâteau du four", quand="dans 10 minutes")
    assert r["ok"] and r["sonnera"].startswith("aujourd'hui") or r["sonnera"].startswith("demain")
    q = _run(eva, "rappel_creer", texte="prendre le café", quand="demain à 8h", recurrence="jour")
    assert q["sonnera"] == "demain à 8 h puis tous les jours"
    assert "pas compris" in _run(eva, "rappel_creer", texte="x", quand="quand tu veux")["error"]
    lst = _run(eva, "rappel_lister")["rappels"]
    assert [x["texte"] for x in lst] == ["sortir le gâteau du four", "prendre le café"]

    recus = []

    async def livrer(sid, msg):
        recus.append(msg)

    async def crochets(msg):
        recus.append(("hook", msg["text"]))
    monkeypatch.setattr(connection_manager, "_deliver", livrer)
    monkeypatch.setattr(connection_manager, "_hooks", crochets)

    async def avancer():
        from app.db import get_pool
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE rappels SET quand = now() - interval '1 second'")
        return await rappels.verifier()
    assert c.portal.call(avancer) == 2
    assert ("hook", "⏰ Rappel : sortir le gâteau du four") in recus
    restants = _run(eva, "rappel_lister")["rappels"]
    assert [x["texte"] for x in restants] == ["prendre le café"]                           # le quotidien revient demain
    assert datetime.fromisoformat(c.portal.call(lambda: rappels.lister(""))[0]["quand"]) > datetime.now(ZoneInfo("Europe/Paris"))
    assert _run(eva, "rappel_annuler", texte="café")["annules"]
    assert _run(eva, "rappel_lister")["rappels"] == []


def test_agents_depuis_la_conversation(eva, monkeypatch):
    from app import agents
    r = _run(eva, "agent_planifier", objectif="Chaque matin à 7h30, donne-moi la météo et mes rendez-vous du jour")
    assert r["ok"] and r["quand"] == "planifié (30 7 * * *)" and r["prochain"], r
    lst = _run(eva, "agent_lister")["agents"]
    a = next(x for x in lst if x["id"] == r["id"])
    assert a["actif"]
    assert "pause" in _run(eva, "agent_gerer", id=r["id"], action="pause")["info"]
    assert c_agent(eva, r["id"])["enabled"] is False
    assert "supprimé" in _run(eva, "agent_gerer", id=r["id"], action="supprimer")["info"]
    assert "introuvable" in _run(eva, "agent_gerer", id=r["id"], action="lancer")["error"]
    assert eva["m"].registry.get("agent_planifier").permission.value == "confirm"
    assert agents  # module bien chargé


def c_agent(eva, aid):
    from app import agents
    return eva["c"].portal.call(lambda: agents.get_agent(aid))


def test_agenda_deplacer_supprimer(eva, monkeypatch):
    from app import google
    appels = []

    async def jeton():
        return "tok"

    async def http(method, url, **kw):
        appels.append((method, url.rsplit("/", 1)[-1], kw.get("json")))
        return 200, ({"id": "evt12345", "summary": "Dentiste", "start": {"dateTime": kw["json"]["start"]["dateTime"]}} if method == "PATCH" else {})
    monkeypatch.setattr(google, "access_token", jeton)
    monkeypatch.setattr(google, "_http", http)
    r = _run(eva, "calendar_modifier", id="evt12345", start="2026-11-03T15:00:00+01:00", end="2026-11-03T16:00:00+01:00")
    assert r["modifie"] and r["debut"] == "2026-11-03T15:00:00+01:00"
    assert appels[-1][0] == "PATCH" and appels[-1][1] == "evt12345" and set(appels[-1][2]) == {"start", "end"}
    assert _run(eva, "calendar_supprimer", id="evt12345") == {"supprime": True} and appels[-1][0] == "DELETE"
    assert "invalide" in _run(eva, "calendar_supprimer", id="../x")["error"]
    assert "fuseau" in _run(eva, "calendar_modifier", id="evt12345", start="2026-11-03T15:00:00")["error"]


def test_carnets(eva):
    r = _run(eva, "carnet_ecrire", carnet="Vacances", section="Bretagne", page="À emporter", texte="- crème solaire")
    assert r["ok"] and r["cree"] == ["carnet", "section"] or r["cree"] == ["carnet", "section", "page"], r
    r = _run(eva, "carnet_ecrire", carnet="vacances", section="bretagne", page="à emporter", texte="- masque de plongée")
    assert r["cree"] is None
    lu = _run(eva, "carnet_lire", carnet="Vacances", page="emporter")
    assert lu["pages"][0]["texte"] == "- crème solaire\n\n- masque de plongée"
    assert any(x["carnet"] == "Vacances" for x in _run(eva, "carnet_lister")["carnets"])
    assert "introuvable" in _run(eva, "carnet_lire", carnet="Travaux")["error"]


def test_finances_noter_et_budget(eva):
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    c.put("/api/modules", json={"finances": True}, headers=A)
    r = _run(eva, "finances_noter", libelle="Marché du samedi", montant=-12.5)
    assert r["ok"] and r["compte"] == "Espèces" and r["montant"] == -12.5 and r["categorie"] == "Alimentation", r
    assert "Montant" in _run(eva, "finances_noter", libelle="x", montant=0)["error"]
    b = _run(eva, "finances_budget", categorie="Alimentation", montant=300)
    assert b["ok"]
    ops = _run(eva, "finances_operations", recherche="marché")
    assert "Marché du samedi" in str(ops)
    c.put("/api/modules", json={"finances": False}, headers=A)


def test_demandes_evolution(eva):
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    r = _run(eva, "evolution_demander", texte="Réserver une table au restaurant", exemple="réserve-moi une table chez Mario samedi")
    assert r["ok"] and not r["deja_demandee"]
    assert _run(eva, "evolution_demander", texte="réserver une table au restaurant")["deja_demandee"]
    d = c.get("/api/self/demandes", headers=A).json()["demandes"]
    x = next(y for y in d if y["texte"] == "Réserver une table au restaurant")
    assert x["fois"] == 2 and x["statut"] == "a_faire"
    d = c.patch(f"/api/self/demandes/{x['id']}", json={"statut": "faite"}, headers=A).json()["demandes"]
    assert next(y for y in d if y["id"] == x["id"])["statut"] == "faite"
    assert c.patch(f"/api/self/demandes/{x['id']}", json={"statut": "x"}, headers=eva["H"](eva["t"]["bob"])).status_code == 403
    assert "evolution_demander" in eva["m"].registry.names()
    from app.config import settings
    assert "evolution_demander" in settings.system_prompt and "recette_modifier" in settings.system_prompt
