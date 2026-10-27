"""Apprentissage par les erreurs : ratés notés, leçon proposée par un modèle, vérifiée au banc d'essai, puis appliquée."""
import json

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_rates_lecons_et_application(eva, monkeypatch):
    from app import lecons, ollama_client
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]
    run = c.portal.call

    async def vider():
        from app.db import get_pool
        async with get_pool().acquire() as conn:
            await conn.execute("DELETE FROM rates"); await conn.execute("DELETE FROM lecons")
    run(vider)                                               # d'autres tests ont pu noter des ratés
    run(lambda: lecons.observer("alice", "s1", "liste moi mes recettes", "Voici les fichiers de ton espace de travail : …", ["fs_list"], [], ""))
    run(lambda: lecons.observer("alice", "s1", "non je voulais mes recettes de cuisine", "…", [], [], "liste moi mes recettes"))
    run(lambda: lecons.observer("alice", "s1", "commande-moi un taxi", "Je ne peux pas commander de taxi.", [], [], ""))
    run(lambda: lecons.observer("alice", "s1", "quelle heure est-il", "Il est 21 h.", [], [], ""))          # pas un raté
    e = c.get("/api/self/lecons", headers=A).json()
    assert e["en_attente"] == 2 and {r["genre"] for r in e["rates"]} == {"correction", "incapable"}
    assert c.get("/api/self/lecons", headers=eva["H"](eva["t"]["bob"])).status_code == 403

    async def modele(messages, tools=None, model=None):
        contenu = messages[-1]["content"]
        if tools:                                                   # banc d'essai : le modèle du jour, avec la leçon dans la demande
            if "Leçons apprises" in contenu and "recette_chercher" in contenu:
                return {"message": {"content": "", "tool_calls": [{"function": {"name": "recette_chercher", "arguments": {}}}]}}
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "fs_list", "arguments": {}}}]}}
        if contenu.startswith("Demande : liste"):
            return {"message": {"content": json.dumps({"possible": True, "outil": "recette_chercher", "exemple": "liste mes recettes",
                                                       "consigne": "q vide pour toutes les recettes du livre."})}}
        return {"message": {"content": json.dumps({"possible": False, "manque": "Commander un taxi"})}}
    monkeypatch.setattr(ollama_client, "chat_once", modele)

    # le banc d'essai rejoue la demande en ajoutant la note de leçon : on l'injecte comme le fait la conversation
    from app import banc_essai
    vrai = banc_essai.essayer

    async def essayer(phrase, attendus, modele_, registry):
        return await vrai(phrase + lecons.note(lecons.pour(phrase)), attendus, modele_, registry)
    monkeypatch.setattr(banc_essai, "essayer", essayer)
    bilan = run(lambda: lecons.apprendre(m.registry))
    assert bilan["etudies"] == 2 and bilan["lecons"] == 1 and bilan["manques"] == 1, bilan
    e = c.get("/api/self/lecons", headers=A).json()
    assert e["lecons"][0]["outil"] == "recette_chercher" and e["en_attente"] == 0
    d = c.get("/api/self/demandes", headers=A).json()["demandes"]
    assert any("taxi" in x["texte"].lower() for x in d)
    # appliquée : une demande semblable reçoit la leçon (et l'outil)
    trouve = lecons.pour("Liste-moi toutes mes recettes stp")
    assert trouve and trouve[0]["outil"] == "recette_chercher" and "recette_chercher" in lecons.note(trouve)
    assert lecons.pour("quelle heure est-il") == []
    lid = e["lecons"][0]["id"]
    c.patch(f"/api/self/lecons/{lid}", json={"actif": False}, headers=A)
    assert lecons.pour("liste mes recettes") == []
    c.patch(f"/api/self/lecons/{lid}", json={"supprimer": True}, headers=A)
    r = c.put("/api/self/lecons/reglages", json={"heure": 4, "code": True, "modele": "cloud:groq|llama"}, headers=A).json()
    assert r["heure"] == 4 and r["code"] is True and r["modele"] == "cloud:groq|llama"
    c.put("/api/self/lecons/reglages", json={"code": False, "modele": ""}, headers=A)


def test_mots():
    from app.lecons import mots
    assert mots("Liste-moi toutes mes recettes, stp !") == ["liste", "recette"]
