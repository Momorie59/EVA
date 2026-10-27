"""Vitesse : pas de rechargement de modèle évitable, mesures des rechargements et conseil."""
import asyncio
import time

from app import perf, router


def _router(monkeypatch, charges):
    async def cfg():
        return {"mode": "auto", "default": "qwen2.5:7b", "fast": "llama3.2:3b", "code": "", "reasoning": "", "vision": ""}

    async def installes(force=False):
        return [{"name": n, "embedding": False, "tools": True, "vision": False, "capabilities": ["completion", "tools"]} for n in ("qwen2.5:7b", "llama3.2:3b")]

    async def charge(m):
        return m in charges
    monkeypatch.setattr(router, "load_config", cfg)
    monkeypatch.setattr(router, "installed_models", installes)
    monkeypatch.setattr(perf, "est_charge", charge)


def test_pas_de_rechargement_pour_une_petite_phrase(monkeypatch):
    _router(monkeypatch, {"qwen2.5:7b"})
    r = asyncio.run(router.select("merci !"))
    assert r["model"] == "qwen2.5:7b" and "rechargement" in r["reason"]


def test_modele_rapide_utilise_s_il_est_deja_charge(monkeypatch):
    _router(monkeypatch, {"llama3.2:3b", "qwen2.5:7b"})
    assert asyncio.run(router.select("merci !"))["model"] == "llama3.2:3b"


def test_mesures_et_conseil(monkeypatch):
    perf._tours.clear()
    for i in range(4):
        perf.noter("qwen2.5:7b" if i % 2 else "llama3.2:3b", {"load_duration": 6e9, "prompt_eval_count": 1000,
                   "prompt_eval_duration": 2e9, "eval_count": 100, "eval_duration": 4e9, "total_duration": 12e9})
    perf.noter("qwen2.5:7b", {"load_duration": 5e7, "prompt_eval_count": 500, "prompt_eval_duration": 1e9, "eval_count": 50, "eval_duration": 2e9})

    async def charges(max_age=3.0):
        return [{"name": "qwen2.5:7b", "size_gb": 5.1, "vram_gb": 5.1, "until": None}]
    monkeypatch.setattr(perf, "modeles_charges", charges)
    r = asyncio.run(perf.resume())
    assert r["tours"] == 5 and r["rechargements"] == 4 and r["rechargement_moyen_ms"] == 6000
    assert r["lecture_tokens_s"] == 500.0 and r["ecriture_tokens_s"] == 25.0
    assert "modèle rapide plus petit" in r["conseil"]
    perf._tours.clear()
    assert asyncio.run(perf.resume())["tours"] == 0
    assert time.time()
