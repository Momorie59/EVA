"""Profil de vitesse : petit modèle pour les demandes courantes, principal pour le code ; réflexion coupée."""
import asyncio

from app import ollama_client, perf, router


def _env(monkeypatch, profil, installes=("qwen2.5:7b", "qwen3.5:4b", "llama3.2:3b")):
    async def cfg():
        return {**router.default_config(), "default": "qwen2.5:7b", "fast": "llama3.2:3b", "profil": profil, "petit": "qwen3.5:4b"}

    async def modeles(force=False):
        return [{"name": n, "embedding": False, "tools": True, "vision": False, "capabilities": ["completion", "tools"]} for n in installes]

    async def charge(m):
        return True
    monkeypatch.setattr(router, "load_config", cfg)
    monkeypatch.setattr(router, "installed_models", modeles)
    monkeypatch.setattr(perf, "est_charge", charge)


def test_profil_rapide(monkeypatch):
    _env(monkeypatch, "rapide")
    r = asyncio.run(router.select("quel temps fera-t-il demain à Lille ?"))
    assert r["model"] == "qwen3.5:4b" and "profil rapide" in r["reason"]
    assert asyncio.run(router.select("écris une fonction python qui trie une liste"))["model"] == "qwen2.5:7b"   # code : le principal
    assert asyncio.run(router.select("merci !"))["model"] == "qwen3.5:4b"


def test_profil_equilibre_inchange(monkeypatch):
    _env(monkeypatch, "equilibre")
    assert asyncio.run(router.select("quel temps fera-t-il demain à Lille ?"))["model"] == "qwen2.5:7b"


def test_petit_modele_absent(monkeypatch):
    _env(monkeypatch, "rapide", installes=("qwen2.5:7b",))
    r = asyncio.run(router.select("raconte-moi une blague"))
    assert r["model"] == "qwen2.5:7b" and "pas encore téléchargé" in r["reason"]


def test_reflexion_coupee():
    assert ollama_client._sans_reflexion({"model": "qwen3.5:4b"})["think"] is False
    assert "think" not in ollama_client._sans_reflexion({"model": "qwen2.5:7b"})
