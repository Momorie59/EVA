"""OBS (faux serveur obs-websocket 5 avec mot de passe), Discord, Instagram, Twilio (réponses simulées)."""
import asyncio
import base64
import hashlib
import json

from integration_pg import requiert_pg

pytestmark = requiert_pg


def _faux_obs(password: str, etat: dict):
    import websockets

    async def gerer(ws):
        await ws.send(json.dumps({"op": 0, "d": {"rpcVersion": 1, "authentication": {"salt": "sel", "challenge": "defi"}}}))
        ident = json.loads(await ws.recv())["d"]
        secret = base64.b64encode(hashlib.sha256((password + "sel").encode()).digest()).decode()
        attendu = base64.b64encode(hashlib.sha256((secret + "defi").encode()).digest()).decode()
        if ident.get("authentication") != attendu:
            await ws.close(4009, "Authentication failed")
            return
        await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        async for m in ws:
            d = json.loads(m)["d"]
            t, data, ok = d["requestType"], {}, True
            etat["recu"].append(t)
            if t == "GetStreamStatus":
                data = {"outputActive": etat["live"], "outputTimecode": "00:01:00"}
            elif t == "GetRecordStatus":
                data = {"outputActive": False}
            elif t == "GetSceneList":
                data = {"currentProgramSceneName": etat["scene"], "scenes": [{"sceneName": "Pause"}, {"sceneName": "Jeu"}]}
            elif t == "StartStream":
                etat["live"] = True
            elif t == "SetCurrentProgramScene":
                etat["scene"] = d["requestData"]["sceneName"]
            else:
                ok = False
            await ws.send(json.dumps({"op": 7, "d": {"requestType": t, "requestId": d["requestId"],
                                                     "requestStatus": {"result": ok, "code": 100 if ok else 204}, "responseData": data}}))
    return websockets.serve(gerer, "127.0.0.1", 0)


def test_obs(eva):
    from app import connecteurs as cx
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    etat = {"live": False, "scene": "Jeu", "recu": []}

    async def lancer():
        srv = await _faux_obs("motdepasse", etat)
        return srv, srv.sockets[0].getsockname()[1]
    srv, port = c.portal.call(lancer)
    try:
        assert c.put("/api/connecteurs/obs", json={"hote": "127.0.0.1", "port": port, "password": "faux"}, headers=H(t["bob"])).status_code == 403
        c.put("/api/connecteurs/obs", json={"hote": "127.0.0.1", "port": port, "password": "faux"}, headers=H(t["alice"]))
        r = c.post("/api/connecteurs/obs/tester", headers=H(t["alice"]))
        assert r.status_code == 400 and "mot de passe" in r.json()["detail"]
        c.put("/api/connecteurs/obs", json={"hote": "127.0.0.1", "port": port, "password": "motdepasse"}, headers=H(t["alice"]))
        e = c.post("/api/connecteurs/obs/tester", headers=H(t["alice"])).json()
        assert e["en_direct"] is False and e["scene"] == "Jeu" and e["scenes"] == ["Jeu", "Pause"]
        assert "motdepasse" not in c.get("/api/connecteurs", headers=H(t["alice"])).text
        outil = m.registry.get("obs_action")
        assert outil.permission.value == "confirm"
        assert c.portal.call(lambda: outil.execute(action="scene", scene="pause"))["scene"] == "Pause"
        assert c.portal.call(lambda: outil.execute(action="demarrer_live"))["ok"] and etat["live"]
        assert "error" in c.portal.call(lambda: outil.execute(action="scene", scene="cuisine"))
        assert "OBS" in c.portal.call(lambda: outil.execute(action="demarrer_replay"))["error"]      # refus d'OBS remonté proprement
    finally:
        srv.close()


class Rep:
    def __init__(self, code, data):
        self.status_code, self._d, self.headers = code, data, {"content-type": "application/json"}

    def json(self):
        return self._d


def test_discord_instagram_twilio(eva, monkeypatch):
    from app import connecteurs as cx
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    appels = []

    async def faux_http(method, url, **kw):
        appels.append((method, url, kw))
        if "discord" in url:
            return Rep(204, None)
        if "graph.instagram.com" in url and url.endswith("/me"):
            return Rep(200, {"username": "lafamille", "followers_count": 321, "media_count": 12})
        if "graph.instagram.com" in url:
            return Rep(200, {"data": [{"caption": "Tiramisu maison", "like_count": 40, "comments_count": 3, "timestamp": "2026-10-20T10:00:00+0000"}]})
        if "twilio" in url:
            return Rep(201, {"sid": "CA1"})
        return Rep(404, {})
    monkeypatch.setattr(cx, "_http", faux_http)
    A = H(t["alice"])
    assert c.put("/api/connecteurs/discord", json={"salons": {"général": "https://exemple.com/x"}}, headers=A).status_code == 400
    c.put("/api/connecteurs/discord", json={"salons": {"Général": "https://discord.com/api/webhooks/123/abc-DEF"}}, headers=A)
    vu = c.get("/api/connecteurs", headers=A).json()["discord"]
    assert vu["salons"] == {"Général": "…bc-DEF"} and "webhooks/123" not in json.dumps(vu)
    c.put("/api/connecteurs/discord", json={"salons": {"Général": "…bc-DEF"}}, headers=A)        # valeur masquée : inchangée
    r = c.portal.call(lambda: m.registry.get("discord_envoyer").execute(message="Live ce soir à 21 h @everyone"))
    assert r == {"ok": True, "salon": "Général"}
    assert appels[-1][1] == "https://discord.com/api/webhooks/123/abc-DEF" and appels[-1][2]["json"]["allowed_mentions"] == {"parse": []}

    c.put("/api/connecteurs/instagram", json={"token": "IGtoken"}, headers=A)
    s = c.portal.call(lambda: m.registry.get("instagram_stats").execute(nombre=3))
    assert s["abonnes"] == 321 and s["dernieres"][0]["j_aime"] == 40 and s["dernieres"][0]["date"] == "2026-10-20"

    sid = "AC" + "0" * 32
    assert c.put("/api/connecteurs/twilio", json={"sid": sid, "token": "x", "de": "+33100000000", "contacts": {"Maman": "06 12 34"}}, headers=A).status_code == 400
    c.put("/api/connecteurs/twilio", json={"sid": sid, "token": "secret", "de": "+33100000000", "contacts": {"Maman": "06 12 34 56 78"}}, headers=A)
    assert c.get("/api/connecteurs", headers=A).json()["twilio"]["contacts"] == {"Maman": "+33612345678"}
    outil = m.registry.get("appel_telephone")
    assert outil.permission.value == "confirm"
    assert "pas dans les contacts" in c.portal.call(lambda: outil.execute(contact="+33699999999", message="coucou"))["error"]
    r = c.portal.call(lambda: outil.execute(contact="maman", message="Le dîner est prêt <vite> & chaud"))
    assert r == {"ok": True, "contact": "Maman", "type": "appel"}
    meth, url, kw = appels[-1]
    assert url.endswith(f"/Accounts/{sid}/Calls.json") and kw["data"]["To"] == "+33612345678" and "&lt;vite&gt; &amp; chaud" in kw["data"]["Twiml"]
    assert c.portal.call(lambda: outil.execute(contact="Maman", message="Rentre vite", sms=True))["type"] == "SMS"
    assert appels[-1][2]["data"]["Body"].startswith("[EVA, assistante automatique") and appels[-1][2]["data"]["Body"].endswith("] Rentre vite")
    assert "assistante automatique" in kw["data"]["Twiml"]


def test_droits_et_selection():
    from app import features
    from app.harness.selection import select_tool_names
    assert features.feature_of("obs_action") == "diffusion" and features.feature_of("appel_telephone") == "notify"
    assert "diffusion" not in features.PROFILE_BASE["child"]
    noms = ["obs_etat", "obs_action", "discord_envoyer", "instagram_stats", "appel_telephone", "weather_get"]
    assert "obs_action" in select_tool_names(["lance le live sur OBS"], noms)
    assert "appel_telephone" not in select_tool_names(["quel temps fait-il ?"], noms)
    assert "appel_telephone" in select_tool_names(["appelle maman pour lui dire que le dîner est prêt"], noms)


def test_appel_conversation(eva, monkeypatch):
    import base64
    import hashlib
    import hmac
    from urllib.parse import urlencode

    from app import appels, connecteurs as cx, ollama_client
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    sid_tw = "AC" + "1" * 32
    assert c.put("/api/connecteurs/twilio", json={"sid": sid_tw, "token": "secret-tw", "de": "+33100000000", "contacts": {"Maman": "0612345678"},
                                                  "adresse_publique": "http://pas-https.fr"}, headers=A).status_code == 400
    c.put("/api/connecteurs/twilio", json={"sid": sid_tw, "token": "secret-tw", "de": "+33100000000", "contacts": {"Maman": "0612345678"},
                                           "adresse_publique": "https://eva.exemple.fr"}, headers=A)
    lances = []

    async def faux_http(method, url, **kw):
        lances.append(kw["data"])

        class R:
            status_code = 201
        return R()
    monkeypatch.setattr(cx, "_http", faux_http)
    repliques = iter(["Très bien, je note que vous venez dimanche. Merci et au revoir ! [FIN]", "Maman vient dimanche vers midi."])

    async def faux_chat(messages, tools=None, model=None):
        return {"role": "assistant", "content": next(repliques)}
    monkeypatch.setattr(ollama_client, "chat_once", faux_chat)
    sid = c.post("/api/sessions", json={"title": "appel"}, headers=A).json()["id"]
    r = c.portal.call(appels.lancer, "maman", "Demander si elle vient manger dimanche", "alice", sid)
    assert r["type"] == "conversation"
    jeton = lances[0]["Url"].split("/api/public/appel/")[1].split("/")[0]
    assert lances[0]["Url"] == f"https://eva.exemple.fr/api/public/appel/{jeton}/debut" and lances[0]["To"] == "+33612345678"

    def twilio(etape, **params):
        url = f"https://eva.exemple.fr/api/public/appel/{jeton}/{etape}"
        sig = base64.b64encode(hmac.new(b"secret-tw", (url + "".join(k + params[k] for k in sorted(params))).encode(), hashlib.sha1).digest()).decode()
        return c.post(f"/api/public/appel/{jeton}/{etape}", content=urlencode(params),
                      headers={"X-Twilio-Signature": sig, "Content-Type": "application/x-www-form-urlencoded"})
    assert c.post(f"/api/public/appel/{jeton}/debut", content="", headers={"X-Twilio-Signature": "faux"}).status_code == 403
    d = twilio("debut", CallSid="CA1")
    assert d.status_code == 200 and "assistante automatique de la maison, de la part de alice" in d.text and "Je ne suis pas une personne" in d.text
    assert "<Gather" in d.text and f"/api/public/appel/{jeton}/tour" in d.text
    tr = twilio("tour", CallSid="CA1", SpeechResult="Oui je viens dimanche midi")
    assert "je note que vous venez dimanche" in tr.text and "<Hangup/>" in tr.text and "[FIN]" not in tr.text
    twilio("fin", CallSid="CA1", CallStatus="completed")
    dernier = c.get(f"/api/sessions/{sid}/messages", headers=A).json()["messages"][-1]["content"]
    assert "Appel à Maman terminé" in dernier and "Maman vient dimanche vers midi." in dernier and "Oui je viens dimanche midi" in dernier
    assert twilio("tour", CallSid="CA1", SpeechResult="x").status_code == 403          # appel fini : jeton invalide
