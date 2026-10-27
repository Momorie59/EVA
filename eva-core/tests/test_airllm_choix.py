"""Choix du modèle d'AirLLM depuis l'interface : relais d'EVA vers le vrai service eva-airllm (sans torch ni téléchargement)."""
import importlib.util
import json
from pathlib import Path

import httpx

from integration_pg import requiert_pg

pytestmark = requiert_pg


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.setenv("AIRLLM_SHARDS_DIR", str(tmp_path / "shards"))
    monkeypatch.setenv("AIRLLM_CONFIG", str(tmp_path / "eva-config.json"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    chemin = Path(__file__).parent.parent.parent / "eva-airllm" / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("eva_airllm_main", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_choisir_le_modele_airllm(eva, monkeypatch, tmp_path):
    from app import routes_airllm
    from app.config import settings
    svc = _service(tmp_path, monkeypatch)
    vrai = httpx.AsyncClient
    monkeypatch.setattr(routes_airllm.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.ASGITransport(app=svc.app), base_url="http://eva-airllm:8200"))
    monkeypatch.setattr(settings, "airllm_url", "http://eva-airllm:8200")
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    assert c.put("/api/airllm", json={"model": "a/b"}, headers=H(t["bob"])).status_code == 403
    d = c.get("/api/airllm", headers=A).json()
    assert d["model"] == "Qwen/Qwen2.5-7B-Instruct" and d["depuis_env"] and d["gpu"] is False and d["sante"]["model"] == d["model"]
    assert any(x["id"] == "Qwen/Qwen2.5-1.5B-Instruct" for x in d["catalogue"]) and d["presents"] == []

    r = c.put("/api/airllm", json={"model": "Qwen/Qwen2.5-1.5B-Instruct"}, headers=A)
    assert r.status_code == 200 and r.json()["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert json.loads((tmp_path / "eva-config.json").read_text())["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert svc.dossier_couches().endswith("shards/Qwen--Qwen2.5-1.5B-Instruct")         # un dossier de couches par modèle
    assert c.get("/api/airllm", headers=A).json()["sante"]["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert "auteur/modèle" in c.put("/api/airllm", json={"model": "../../etc"}, headers=A).json()["detail"]

    for m in ("Qwen--Qwen2.5-7B-Instruct", "Qwen--Qwen2.5-1.5B-Instruct"):         # deux modèles sur le disque
        p = tmp_path / "hf" / "hub" / f"models--{m}"
        p.mkdir(parents=True)
        (p / "poids.safetensors").write_bytes(b"x" * 1000)
    (tmp_path / "shards" / "Qwen--Qwen2.5-7B-Instruct").mkdir(parents=True)
    presents = {x["id"] for x in c.get("/api/airllm", headers=A).json()["presents"]}
    assert presents == {"Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct"}
    assert c.delete("/api/airllm/modeles/Qwen/Qwen2.5-1.5B-Instruct", headers=A).status_code == 409   # celui utilisé
    r = c.delete("/api/airllm/modeles/Qwen/Qwen2.5-7B-Instruct", headers=A).json()
    assert [x["id"] for x in r["presents"]] == ["Qwen/Qwen2.5-1.5B-Instruct"]
    assert not (tmp_path / "shards" / "Qwen--Qwen2.5-7B-Instruct").exists()
    monkeypatch.setattr(settings, "airllm_url", "")
    assert c.get("/api/airllm", headers=A).status_code == 404


def test_options_selon_le_materiel(monkeypatch, tmp_path):
    svc = _service(tmp_path, monkeypatch)
    import types
    import sys
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(float32="f32"))
    cpu = svc.options_chargement(False)
    assert cpu["device"] == "cpu" and cpu["dtype"] == "f32" and "compression" not in cpu and cpu["prefetching"] is False
    gpu = svc.options_chargement(True)
    assert gpu["compression"] == "4bit" and "device" not in gpu
    assert cpu["layer_shards_saving_path"].endswith("Qwen--Qwen2.5-7B-Instruct")


def test_airllm_seulement_si_choisi(eva, monkeypatch):
    """Serveur IA éteint : AirLLM n'est pas pris d'office ; seulement si la case « repli automatique » est cochée."""
    from app import router
    c, A = eva["c"], eva["H"](eva["t"]["alice"])

    async def aucun(force=False):
        return None

    async def en_ligne():
        return True
    monkeypatch.setattr(router, "installed_models", aucun)
    monkeypatch.setattr(router, "airllm_up", en_ligne)
    choisir = lambda: c.portal.call(lambda: router.select("Explique-moi la photosynthèse"))  # noqa: E731
    assert choisir()["model"] != "airllm"
    assert c.put("/api/airllm/repli", json={"repli_auto": True}, headers=A).json() == {"repli_auto": True}
    assert choisir()["model"] == "airllm"
    assert c.put("/api/airllm/repli", json={"repli_auto": False}, headers=A).json() == {"repli_auto": False}
    assert choisir()["model"] != "airllm"
    assert c.put("/api/airllm/repli", json={"repli_auto": True}, headers=eva["H"](eva["t"]["bob"])).status_code == 403
