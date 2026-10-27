"""Raccourcis du téléphone : jeton personnel, réponse en texte, jamais d'action qui demande un accord."""
from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_raccourcis(eva, monkeypatch):
    from app.harness import loop
    c, H, t = eva["c"], eva["H"], eva["t"]
    B = H(t["bob"])
    j = c.post("/api/raccourcis", json={"nom": "iPhone de Bob"}, headers=B).json()
    assert j["jeton"].startswith("evarac_") and c.get("/api/raccourcis", headers=H(t["alice"])).json()["jetons"] == []
    R = {"Authorization": f"Bearer {j['jeton']}"}
    assert c.post("/api/raccourci", content="bonjour", headers={"Authorization": "Bearer evarac_faux"}).status_code == 401
    r = c.post("/api/raccourci", json={"texte": "ajoute du pain à la liste de courses"}, headers=R)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain") and "pain" in r.text, r.text

    etapes = iter([[("tool_calls", [{"function": {"name": "gmail_send", "arguments": {"to": "x@y.fr", "subject": "s", "body": "b"}}}])],
                   [("content", "Je n'ai pas envoyé le mail.")]])

    async def flux(history, tools=None, model=None):
        for ev in next(etapes):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    eva_c = c.post("/api/raccourci?format=json", content="envoie un mail à x@y.fr pour dire bonjour", headers=R).json()["reponse"]
    assert eva_c.startswith("Je n'ai pas envoyé le mail.") and "ouvre EVA pour le confirmer" in eva_c, eva_c
    c.delete(f"/api/raccourcis/{j['id']}", headers=B)
    assert c.post("/api/raccourci", content="x", headers=R).status_code == 401
