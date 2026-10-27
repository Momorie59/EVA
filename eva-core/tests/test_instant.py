"""Réponses instantanées (sans modèle) à travers la vraie conversation : heure, ajout et lecture de liste."""
from integration_pg import requiert_pg

from app import instant

pytestmark = requiert_pg


def _dire(eva, texte):
    c, t = eva["c"], eva["t"]["alice"]
    sid = c.post("/api/sessions", json={"title": "instant"}, headers=eva["H"](t)).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={t}&session={sid}") as w:
        w.send_json({"text": texte})
        out, outils = "", []
        for _ in range(40):
            ev = w.receive_json()
            if ev.get("type") == "token":
                out += ev["text"]
            if ev.get("type") == "tool_call":
                outils.append(ev["name"])
            if ev.get("type") in ("done", "error"):
                break
    return out, outils


def test_listes_et_heure(eva):
    r, o = _dire(eva, "ajoute du lait et des œufs à la liste de courses")
    assert r == "J'ai ajouté du lait et des œufs à la liste « Courses »." and o == ["list_add"]
    r, _ = _dire(eva, "ajoute du lait et du pain à la liste de courses")
    assert "J'ai ajouté du pain" in r and "Déjà sur la liste : du lait" in r
    r, _ = _dire(eva, "qu'est-ce qu'il y a sur la liste de courses ?")
    assert "- du lait" in r and "- des œufs" in r and "- du pain" in r
    r, o = _dire(eva, "quelle heure est-il ?")
    assert r.startswith("Il est ") and o == ["horloge"]


def test_phrases_complexes_laissees_au_modele():
    for t in ("ajoute une section sur les impôts à mon rapport", "quelle heure est-il à Tokyo et quel temps fait-il",
              "ajoute un post-it à la liste", "peux-tu me dire ce que je dois acheter pour une raclette ?"):
        assert instant.detect(t) is None, t
