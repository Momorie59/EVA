"""Réglages d'inférence envoyés à Ollama : taille du contexte (num_ctx) et température.
Sans num_ctx, Ollama coupe silencieusement le début de la conversation quand elle dépasse son défaut (2048 à 4096 jetons) :
la consigne d'EVA, les schémas d'outils et les fichiers joints disparaissent, et elle « comprend mal »."""
import json

from .db import get_pool

DEFAULTS = {"num_ctx": 8192, "temperature": 0.4}
LIMITS = {"num_ctx": (2048, 131072), "temperature": (0.0, 1.5)}
_CACHE = dict(DEFAULTS)


def options() -> dict:
    return {"num_ctx": int(_CACHE["num_ctx"]), "temperature": float(_CACHE["temperature"])}


async def load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='llm_options'")
    _CACHE.update(DEFAULTS)
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        for k in DEFAULTS:
            if isinstance(data.get(k), (int, float)):
                lo, hi = LIMITS[k]
                _CACHE[k] = min(max(data[k], lo), hi)
    return options()


async def save(num_ctx: int, temperature: float) -> dict:
    for k, v in (("num_ctx", num_ctx), ("temperature", temperature)):
        lo, hi = LIMITS[k]
        if not (lo <= v <= hi):
            raise ValueError(f"{k} doit être entre {lo} et {hi}.")
    cfg = {"num_ctx": int(num_ctx), "temperature": round(float(temperature), 2)}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('llm_options', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(cfg))
    _CACHE.update(cfg)
    return options()
