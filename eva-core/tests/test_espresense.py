"""Présence pièce par pièce (ESP32 + ESPresense) : messages MQTT, pièce la plus proche, intégration à la présence."""
import json
import time

from app import espresense


def test_messages_et_pieces():
    espresense._mesures.clear()
    t = time.time()
    assert not espresense.recevoir("autre/devices/x/salon", b"{}")
    assert not espresense.recevoir("espresense/devices/x/salon", b"pas du json")
    assert espresense.recevoir("espresense/devices/irk:abc/salon", json.dumps({"id": "irk:abc", "name": "iPhone", "distance": 3.2}), maintenant=t)
    assert espresense.recevoir("espresense/devices/irk:abc/bureau", json.dumps({"distance": 0.9}), maintenant=t)
    espresense.recevoir("espresense/devices/montre/cuisine", json.dumps({"distance": 1.5}), maintenant=t - 120)   # trop vieux
    p = espresense.pieces({"irk:abc": "Paul", "montre": "Léa"}, maintenant=t)
    assert p == {"Paul": {"piece": "Bureau", "distance": 0.9}}
    vus = espresense.appareils_vus(maintenant=t)
    assert {"irk:abc", "montre"} <= {v["id"] for v in vus} and next(v for v in vus if v["id"] == "irk:abc")["nom"] == "iPhone"
    espresense._mesures.clear()


def test_presence_avec_pieces(eva):
    from app import presence
    c, H, t = eva["c"], eva["H"], eva["t"]
    r = c.put("/api/home/admin/espresense", json={"actif": True, "hote": "127.0.0.1", "port": 1, "appareils": {"irk:abc": "Julie"}},
              headers=H(t["alice"]))
    assert r.status_code == 200 and r.json()["reglages"]["appareils"] == {"irk:abc": "Julie"}
    assert c.put("/api/home/admin/espresense", json={"actif": False}, headers=H(t["bob"])).status_code == 403
    espresense.recevoir("espresense/devices/irk:abc/chambre_parents", json.dumps({"distance": 1.1}))
    e = c.portal.call(presence.etat)
    julie = next(p for p in e["personnes"] if p["nom"] == "Julie")
    assert julie["present"] and julie["piece"] == "Chambre parents"
    assert "Julie (chambre parents)" in presence.phrase(e)
    assert c.portal.call(lambda: espresense.piece_de("julie")) == "Chambre parents"
    c.put("/api/home/admin/espresense", json={"actif": False, "appareils": {}}, headers=H(t["alice"]))
    espresense._mesures.clear()
