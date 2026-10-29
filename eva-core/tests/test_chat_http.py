"""Conversation sans WebSocket (proxy d'entreprise) : même conversation que /ws/chat, en HTTP long polling."""


def test_conversation_http(eva, monkeypatch):
    from app import chat_http
    monkeypatch.setattr(chat_http, "ATTENTE_S", 2)
    c, H, t = eva["c"], eva["H"], eva["t"]
    jeton = t["bob"]
    sid = c.post("/api/sessions", json={"title": "bureau"}, headers=H(jeton)).json()["id"]
    assert c.post(f"/api/chat-http/ouvrir?session={sid}&token=faux").status_code == 401          # jeton refusé
    autre = c.post("/api/sessions", json={"title": "à carla"}, headers=H(t["carla"])).json()["id"]
    assert c.post(f"/api/chat-http/ouvrir?session={autre}", headers=H(jeton)).status_code == 403  # conversation d'une autre personne
    cid = c.post(f"/api/chat-http/ouvrir?session={sid}", headers=H(jeton)).json()["id"]
    assert c.post(f"/api/chat-http/{cid}/envoyer", json={"text": "bonjour"}, headers=H(jeton)).json()["ok"]
    vus, n, texte = [], 0, ""
    for _ in range(40):
        r = c.get(f"/api/chat-http/{cid}/recevoir?apres={n}", headers=H(jeton)).json()
        for e in r["evenements"]:
            n = e["n"]
            vus.append(e["data"].get("type"))
            if e["data"].get("type") == "token":
                texte += e["data"].get("text", "")
        if "done" in vus or "error" in vus:
            break
    assert "state" in vus and ("done" in vus or "error" in vus)      # même flux d'événements que le WebSocket
    c.post(f"/api/chat-http/{cid}/fermer", headers=H(jeton))
    assert c.post(f"/api/chat-http/{cid}/envoyer", json={"text": "encore"}, headers=H(jeton)).status_code == 410
    for qui, s in (("bob", sid), ("carla", autre)):                         # ne rien laisser aux tests suivants
        c.post("/api/sessions/supprimer", json={"ids": [s]}, headers=H(t[qui]))
        c.post("/api/sessions/corbeille/vider", json={"tout": True}, headers=H(t[qui]))
