"""Satellites vocaux : jeton, voix autorisée, réponse immédiate, accord à voix haute, musique."""
import shutil
import subprocess

import pytest

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_satellite_conversation_et_accord(eva, monkeypatch):
    from app.harness import loop
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    assert c.post("/api/home/admin/satellites", json={"nom": "Cuisine", "piece": "cuisine", "compte": "bob"}, headers=H(t["bob"])).status_code == 403
    assert c.get("/api/home/admin/satellites", headers=H(t["bob"])).status_code == 403
    s = c.post("/api/home/admin/satellites", json={"nom": "Cuisine", "piece": "cuisine", "compte": "alice"}, headers=A).json()
    S = {"Authorization": f"Bearer {s['jeton']}"}
    assert c.get("/api/auth/verify", headers=S).status_code == 200                     # le service voix l'accepte
    assert c.get("/api/auth/verify", headers={"Authorization": "Bearer evasat_faux"}).status_code == 401
    assert c.post("/api/satellite/bonjour", headers={"Authorization": "Bearer evasat_faux"}).status_code == 401
    assert c.post("/api/satellite/bonjour", headers=S).json() == {"nom": "Cuisine", "piece": "cuisine", "mot": "EVA", "pause": False}
    assert c.get("/api/home/admin/satellites", headers=A).json()["satellites"][0]["en_ligne"] is True

    r = c.post("/api/satellite/demander", json={"texte": "Quelle heure est-il ?"}, headers=S).json()
    assert r["reponse"].startswith("Il est ")

    vus = []
    appels = iter([
        [("tool_calls", [{"function": {"name": "obs_action", "arguments": {"action": "demarrer_live"}}}])],
        [("content", "OBS n'est pas encore relié.")],
    ])

    async def flux(history, tools=None, model=None):
        vus.append(history[0]["content"])
        for ev in next(appels):
            yield ev
    monkeypatch.setattr(loop, "stream_decide", flux)
    r = c.post("/api/satellite/demander", json={"texte": "Lance le live sur OBS"}, headers=S).json()
    assert r.get("attente") and "piloter OBS" in r["question"] and "demarrer_live" in r["question"], r
    assert "cuisine" in vus[0] and "une ou deux phrases" in vus[0]
    r = c.post("/api/satellite/repondre", json={"texte": "Oui vas-y"}, headers=S).json()
    assert r["reponse"] == "OBS n'est pas encore relié."
    assert c.post("/api/satellite/repondre", json={"texte": "oui"}, headers=S).json()["reponse"] == "Il n'y avait rien à confirmer."

    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)
    assert c.post("/api/satellite/bonjour", headers=S).status_code == 401


def test_scripts_telechargeables(eva):
    c = eva["c"]
    r = c.get("/api/public/satellite/satellite.py")
    assert r.status_code == 200 and "commande_apres_eveil" in r.text
    assert c.get("/api/public/satellite/installer-linux.sh").status_code == 200
    assert c.get("/api/public/satellite/../main.py").status_code == 404


def test_oui_non():
    from app.satellites import est_oui
    assert est_oui("Oui.") and est_oui("vas-y") and est_oui("d'accord")
    assert not est_oui("non") and not est_oui("non merci") and not est_oui("")


@pytest.mark.skipif(not shutil.which("fpcalc") or not shutil.which("ffmpeg"), reason="fpcalc ou ffmpeg absent")
def test_musique(eva, monkeypatch, tmp_path):
    from app import connecteurs as cx
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    extrait = tmp_path / "x.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-f", "lavfi", "-i",
                    "anoisesrc=d=12:a=0.2", "-filter_complex", "amix=inputs=2", "-ar", "16000", "-ac", "1", str(extrait)], check=True)
    donnees = extrait.read_bytes()
    assert "pas configurée" in c.post("/api/musique/reconnaitre?nom=x.wav", content=donnees, headers=A).json()["detail"]
    envoye = {}

    class Rep:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok", "results": [{"score": 0.93, "recordings": [{"id": "abc", "title": "Bohemian Rhapsody",
                    "artists": [{"name": "Queen"}], "releasegroups": [{"type": "Album", "title": "A Night at the Opera"}]}]}]}

    async def faux_http(method, url, **kw):
        envoye.update(kw["data"])
        return Rep()
    monkeypatch.setattr(cx, "_http", faux_http)
    c.put("/api/connecteurs/acoustid", json={"cle": "cleTest123"}, headers=A)
    r = c.post("/api/musique/reconnaitre?nom=x.wav", content=donnees, headers=A).json()
    assert r["titre"] == "Bohemian Rhapsody" and r["phrase"] == "C'est « Bohemian Rhapsody », de Queen, sur l'album « A Night at the Opera »."
    assert envoye["client"] == "cleTest123" and int(envoye["duration"]) >= 11 and len(envoye["fingerprint"]) > 20
    assert c.post("/api/musique/reconnaitre", content=b"x" * 10, headers=A).status_code == 400


def test_ordres_annonce_et_pc(eva):
    import importlib
    import sys
    import threading
    import types
    from pathlib import Path
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    sys.modules.setdefault("sounddevice", types.SimpleNamespace(InputStream=None, play=None, wait=None, rec=None, query_devices=None))
    sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "data" / "satellite"))
    sat_client = importlib.import_module("satellite")
    A = H(t["alice"])
    s = c.post("/api/home/admin/satellites", json={"nom": "Bureau", "piece": "bureau", "compte": "alice"}, headers=A).json()
    S = {"Authorization": f"Bearer {s['jeton']}"}
    run = lambda nom, **kw: c.portal.call(lambda: m.registry.get(nom).execute(**kw))      # noqa: E731
    assert "n'écoute pas" in run("annonce", texte="À table !", piece="bureau")["error"]   # satellite pas encore à l'écoute

    dits, fin = [], threading.Event()
    pc = sat_client.Ordinateur({"jeu": "echo jeu"}, None, None)
    c.post("/api/satellite/bonjour", json={"capacites": ["dire", "pc"], "systeme": "Linux", "applis": sorted(pc.applis)}, headers=S)

    def satellite():
        while not fin.is_set():
            for o in c.post("/api/satellite/ordres", headers=S).json()["ordres"]:
                if o["type"] == "dire":
                    dits.append(o["texte"])
                    res = {"ok": True}
                else:
                    res = pc.faire(o["action"], o.get("valeur", ""))
                c.post("/api/satellite/resultat", json={"id": o["id"], "resultat": res}, headers=S)
    th = threading.Thread(target=satellite, daemon=True)
    th.start()
    import time as _t
    _t.sleep(0.5)
    r = run("annonce", texte="À table !", piece="partout")
    assert r == {"ok": True, "annonce_sur": ["Bureau"]} and dits == ["À table !"]
    e = run("pc_commande", action="etat")
    assert e["ordinateur"] == "Bureau" and "memoire_pct" in e, e
    assert "pas dans la liste" in run("pc_commande", action="ouvrir", valeur="minecraft")["error"]
    assert run("pc_commande", action="ouvrir", valeur="jeu")["texte"] == "jeu est lancé."
    assert m.registry.get("pc_commande").permission_for({"action": "eteindre"}).value == "confirm"
    assert "musique" in run("pc_commande", action="reconnaitre_musique")["error"]
    liste = c.get("/api/home/admin/satellites", headers=A).json()["satellites"]
    assert liste[0]["capacites"] == ["dire", "pc"] and liste[0]["a_l_ecoute"] and "jeu" in liste[0]["applis"]
    fin.set()


def test_annonce_alexa(eva, monkeypatch):
    from app import homeassistant
    m = eva["m"]
    appels = []

    async def faux_api(method, path, **kw):
        if path == "/api/states":
            return [{"entity_id": "media_player.echo_cuisine", "attributes": {"friendly_name": "Echo Cuisine", "last_called": False}},
                    {"entity_id": "media_player.tv_salon", "attributes": {"friendly_name": "TV salon"}},
                    {"entity_id": "media_player.echo_dot_chambre", "attributes": {"friendly_name": "Chambre Léa", "last_called": True}}]
        appels.append((path, kw.get("json")))
        return {}
    monkeypatch.setattr(homeassistant, "_api", faux_api)
    r = eva["c"].portal.call(lambda: m.registry.get("annonce").execute(texte="À table !", piece="cuisine"))
    assert r["ok"] and "Echo Echo Cuisine" in r["annonce_sur"], r
    assert appels[-1] == ("/api/services/notify/alexa_media", {"message": "À table !", "target": ["media_player.echo_cuisine"], "data": {"type": "announce"}})
    eva["c"].portal.call(lambda: m.registry.get("annonce").execute(texte="Bonne nuit", piece="partout"))
    assert appels[-1][1]["target"] == ["media_player.echo_cuisine", "media_player.echo_dot_chambre"]       # pas la télé
