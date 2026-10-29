"""Mode miroir : identification par empreintes (logique pure), droits, et reconnaissance réelle si les modèles
sont disponibles (EVA_TEST_VISAGES = dossier contenant les deux fichiers .onnx de l'OpenCV Zoo)."""
import base64
import os
import shutil
from pathlib import Path

import numpy as np
import pytest


def _v(*x):
    v = np.array(x + (0.0,) * (128 - len(x)), dtype=np.float32)
    return v / np.linalg.norm(v)


def test_identifier_logique():
    from app import miroir
    miroir._empreintes.clear()
    miroir._empreintes.update({"alice": [_v(1, 0)], "bob": [_v(0, 1)]})
    r = miroir.identifier([_v(0.95, 0.1)])
    assert r["personnes"][0]["qui"] == "alice" and not r["discret"]
    r = miroir.identifier([_v(0.95, 0.1), _v(0.1, 0.95)])
    assert {p["qui"] for p in r["personnes"]} == {"alice", "bob"} and r["discret"]          # deux personnes : discret
    r = miroir.identifier([_v(0, 0, 1)])
    assert r["personnes"] == [] and r["inconnus"] == 1 and r["discret"]                       # inconnu : discret
    assert miroir.identifier([])["visages"] == 0
    miroir._empreintes.clear()


def test_droits_et_cartes(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    assert c.post("/api/miroir/visages", json={"qui": "alice", "images": []}, headers=H(t["bob"])).status_code == 403
    assert c.delete("/api/miroir/visages/alice", headers=H(t["bob"])).status_code == 403
    assert c.post("/api/miroir/modeles", headers=H(t["bob"])).status_code == 403
    e = c.get("/api/miroir/etat", headers=H(t["bob"])).json()
    assert "modeles_prets" in e and "personnes" in e
    assert "tuiles" in c.get("/api/miroir/cartes?qui=alice", headers=H(t["bob"])).json()        # bob : tuiles générales


MODELES = os.getenv("EVA_TEST_VISAGES", "")


@pytest.mark.skipif(not MODELES, reason="EVA_TEST_VISAGES non défini : modèles de visages absents")
def test_reconnaissance_reelle(eva, tmp_path):
    import cv2
    from skimage import data
    from app import miroir
    c, H, t = eva["c"], eva["H"], eva["t"]
    d = tmp_path / ".modeles" / "visages"
    d.mkdir(parents=True)
    for f in Path(MODELES).glob("*.onnx"):
        shutil.copy(f, d / f.name)
    miroir.lier(tmp_path)
    miroir._detecteur = None

    def b64(img):
        return base64.b64encode(cv2.imencode(".jpg", img)[1].tobytes()).decode()
    astro = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
    variantes = [astro, cv2.flip(astro, 1), cv2.convertScaleAbs(astro, alpha=1.2, beta=10),
                 cv2.resize(astro, None, fx=0.8, fy=0.8), cv2.GaussianBlur(astro, (3, 3), 0)]
    r = c.post("/api/miroir/visages", json={"qui": "carla", "images": [b64(x) for x in variantes]}, headers=H(t["alice"]))
    assert r.status_code == 200 and r.json()["photos"] >= 3, r.text
    vu = c.post("/api/miroir/regarder", json={"image": b64(cv2.convertScaleAbs(astro, alpha=0.9, beta=-10))}, headers=H(t["bob"])).json()
    assert vu["personnes"] and vu["personnes"][0]["qui"] == "carla"
    autre = cv2.cvtColor(data.camera(), cv2.COLOR_GRAY2BGR)                      # le cameraman : quelqu'un d'autre
    vu2 = c.post("/api/miroir/regarder", json={"image": b64(autre)}, headers=H(t["bob"])).json()
    assert all(p["qui"] != "carla" for p in vu2["personnes"])
    vide = np.full((300, 300, 3), 120, np.uint8)
    assert c.post("/api/miroir/regarder", json={"image": b64(vide)}, headers=H(t["bob"])).json()["visages"] == 0
    assert c.delete("/api/miroir/visages/carla", headers=H(t["carla"])).json()["effaces"] >= 3   # chacun efface le sien
    miroir._detecteur = None
