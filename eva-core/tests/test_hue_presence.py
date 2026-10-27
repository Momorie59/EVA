"""Philips Hue en direct (faux pont) et présence à la maison (faux eva-scanner)."""
import time

from integration_pg import requiert_pg

pytestmark = requiert_pg


class FauxPont:
    def __init__(self):
        self.bouton = False
        self.etats = {"1": {"on": False, "bri": 100, "reachable": True, "xy": [0.3, 0.3], "ct": 300}, "2": {"on": True, "bri": 254, "reachable": True}}
        self.recu = []

    async def req(self, method, url, body=None, timeout=6.0):
        self.recu.append((method, url.split("/api", 1)[1], body))
        chemin = url.split("/api", 1)[1]
        if method == "POST" and chemin == "":
            return [{"success": {"username": "cle-secrete"}}] if self.bouton else [{"error": {"type": 101, "description": "link button not pressed"}}]
        if "cle-secrete" not in chemin:
            return [{"error": {"type": 1, "description": "unauthorized user"}}]
        if chemin.endswith("/config"):
            return {"name": "Pont du salon"}
        if chemin.endswith("/lights"):
            return {lid: {"name": n, "type": "Extended color light", "state": self.etats[lid]} for lid, n in (("1", "Lampe salon"), ("2", "Plafonnier"))}
        if "/lights/" in chemin and method == "PUT":
            lid = chemin.split("/lights/")[1].split("/")[0]
            self.etats[lid].update(body)
            return [{"success": body}]
        if "/lights/" in chemin:
            return {"state": self.etats[chemin.split("/lights/")[1]]}
        if chemin.endswith("/scenes"):
            return {"abc": {"name": "Lecture", "type": "GroupScene", "group": "1"}}
        if chemin.endswith("/groups"):
            return {"1": {"name": "Salon"}}
        if "/groups/" in chemin:
            return [{"success": body}]
        return {}


def test_hue_appairage_import_pilotage(eva, monkeypatch):
    from app import hue
    pont = FauxPont()
    monkeypatch.setattr(hue, "_req", pont.req)
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    r = c.post("/api/home/admin/hue/appairer", json={"ip": "192.168.1.20"}, headers=H(t["alice"]))
    assert r.status_code == 400 and "bouton" in r.json()["detail"]
    pont.bouton = True
    assert c.post("/api/home/admin/hue/appairer", json={"ip": "192.168.1.20"}, headers=H(t["alice"])).json()["nom"] == "Pont du salon"
    assert c.post("/api/home/admin/hue/appairer", json={"ip": "192.168.1.20"}, headers=H(t["bob"])).status_code == 403
    ls = c.get("/api/home/admin/hue/192.168.1.20/lampes", headers=H(t["alice"])).json()["lampes"]
    assert [l["nom"] for l in ls] == ["Lampe salon", "Plafonnier"]
    imp = c.post("/api/home/admin/hue/192.168.1.20/importer", json={"ids": ["1", "2"], "piece": "salon"}, headers=H(t["alice"])).json()
    assert len(imp["ajoutees"]) == 2
    assert c.post("/api/home/admin/hue/192.168.1.20/importer", json={"ids": ["1"]}, headers=H(t["alice"])).json()["ajoutees"] == []   # pas de doublon
    from app import devices
    res = c.portal.call(lambda: devices.control("lampe salon", "on"))
    assert pont.etats["1"]["on"] is True, res
    c.portal.call(lambda: devices.control("lampe salon", "color", "bleu"))
    assert pont.etats["1"]["xy"][1] < 0.1                                   # bleu : y très bas
    c.portal.call(lambda: devices.control("lampe salon", "brightness", 50))
    assert pont.etats["1"]["bri"] == 127
    sc = c.portal.call(lambda: m.registry.get("device_hue_scene").execute(scene="lecture", piece="salon"))
    assert sc["ok"] and sc["piece"] == "Salon" and ("PUT", "/cle-secrete/groups/1/action", {"scene": "abc"}) in pont.recu
    assert "cle-secrete" not in c.get("/api/home/admin/hue", headers=H(t["alice"])).text          # la clé n'est jamais renvoyée


def test_presence(eva, monkeypatch):
    from app import presence
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    assert c.put("/api/home/admin/presence", json={"personnes": {"Julie": {"macs": ["zz"]}}}, headers=H(t["alice"])).status_code == 400
    c.put("/api/home/admin/presence", json={"personnes": {"Paul": {"macs": ["aa-bb-cc-dd-ee-01"]}, "Julie": {"macs": ["AA:BB:CC:DD:EE:02"]}}},
          headers=H(t["alice"]))
    presence._vus.clear()
    presence._vus["AA:BB:CC:DD:EE:01"] = {"ip": "192.168.1.40", "ts": time.time()}
    presence._vus["AA:BB:CC:DD:EE:02"] = {"ip": "192.168.1.41", "ts": time.time() - 3600}
    e = c.get("/api/home/presence", headers=H(t["bob"])).json()
    assert {p["nom"]: p["present"] for p in e["personnes"]} == {"Paul": True, "Julie": False}
    assert presence.phrase(e) == "À la maison : Paul. Absent : Julie."
    assert c.put("/api/home/admin/presence", json={"personnes": {}}, headers=H(t["bob"])).status_code == 403
    from app import instant
    rep = c.portal.call(instant.repondre, instant.detect("qui est à la maison ?"), "Europe/Paris")
    assert rep[0] == "À la maison : Paul. Absent : Julie."


def test_scenes_de_depart_et_d_arrivee(eva, monkeypatch):
    from app import devices, presence
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    d = c.post("/api/home/admin/devices", json={"name": "Lampe entrée", "room": "entrée", "type": "light", "driver": "wled",
                                                "config": {"ip": "192.168.1.77"}}, headers=A)
    assert d.status_code == 200, d.text
    sc = c.post("/api/home/admin/scenes", json={"name": "Départ", "actions": [{"device": "Lampe entrée", "action": "off"}]}, headers=A).json()
    lances = []

    async def faux_run(scene):
        lances.append(scene["name"])
        return {"ok": True}
    monkeypatch.setattr(devices, "run_scene", faux_run)
    c.put("/api/home/admin/presence", json={"personnes": {"Paul": {"macs": ["AA:BB:CC:DD:EE:01"]}},
                                            "automatismes": {"depart": sc["id"], "arrivee": None}}, headers=A)
    reg = c.get("/api/home/admin/presence", headers=A).json()
    assert reg["automatismes"]["depart"] == sc["id"] and any(s["nom"] == "Départ" for s in reg["scenes"])
    c.put("/api/home/admin/presence", json={"personnes": {"Paul": {"macs": ["AA:BB:CC:DD:EE:01"]}}}, headers=A)
    assert c.get("/api/home/admin/presence", headers=A).json()["automatismes"]["depart"] == sc["id"]      # gardés si non renvoyés
    presence._etat.pop("presents", None)
    presence._etat["erreur"] = ""
    presence._vus.clear()
    presence._vus["AA:BB:CC:DD:EE:01"] = {"ip": "x", "ts": time.time()}
    assert c.portal.call(presence.automatismes) is None                          # premier passage : observation seulement
    presence._vus["AA:BB:CC:DD:EE:01"]["ts"] = time.time() - 3600
    assert c.portal.call(presence.automatismes) == "🏠 Tout le monde est parti : scène « Départ » lancée."
    assert lances == ["Départ"]
    presence._vus["AA:BB:CC:DD:EE:01"]["ts"] = time.time()
    assert c.portal.call(presence.automatismes) is None                          # arrivée : aucune scène choisie
    assert lances == ["Départ"]
