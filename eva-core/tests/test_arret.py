"""Bouton « Arrêter » : une réponse qui tourne en boucle s'arrête tout de suite, et la conversation continue."""
import asyncio

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_arreter_une_reponse_en_boucle(eva, monkeypatch):
    from app.harness import loop
    tours = {"n": 0}

    async def flux(history, tools=None, model=None):
        tours["n"] += 1
        if tours["n"] == 1:
            while True:                                      # le modèle récite sans fin
                await asyncio.sleep(0.05)
                yield ("content", "--- uploads/décompte.pdf --- ")
        yield ("content", "Bonjour !")
    monkeypatch.setattr(loop, "stream_decide", flux)
    c, t = eva["c"], eva["t"]["alice"]
    sid = c.post("/api/sessions", json={"title": "boucle"}, headers=eva["H"](t)).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={t}&session={sid}") as w:
        w.send_json({"text": "Résume mon décompte de paiement"})
        n = 0
        while n < 5:
            if w.receive_json().get("type") == "token":
                n += 1
        w.send_json({"type": "stop"})
        vus = []
        for _ in range(500):
            ev = w.receive_json()
            vus.append(ev.get("type"))
            if ev.get("type") == "done":
                break
        assert "stopped" in vus and vus[-1] == "done"
        w.send_json({"text": "Bonjour"})                    # la conversation repart normalement
        texte = ""
        for _ in range(200):
            ev = w.receive_json()
            if ev.get("type") == "token":
                texte += ev["text"]
            if ev.get("type") == "done":
                break
        assert texte == "Bonjour !"
