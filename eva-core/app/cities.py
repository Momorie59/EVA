"""Villes d'EVA : ville par défaut (météo, briefing du matin) et liste de villes proposées en choix rapide."""
import json
import re

from .config import settings
from .db import get_pool

KV = "cities"
MAX = 12
_NAME = re.compile(r"^[^\W\d_][\w' .\-]{0,58}$", re.UNICODE)


async def get() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    lst = [c for c in d.get("list", []) if isinstance(c, str) and c.strip()]
    default = d.get("default") or settings.default_city
    if default not in lst:
        lst.insert(0, default)
    return {"default": default, "list": lst[:MAX]}


async def default() -> str:
    return (await get())["default"]


def clean(name: str) -> str:
    name = " ".join((name or "").split())
    if not _NAME.match(name):
        raise ValueError(f"Nom de ville invalide : « {name[:30]} ».")
    return name


async def save(default_city: str, cities: list[str]) -> dict:
    d = clean(default_city)
    out: list[str] = []
    for c in cities:
        c = clean(c)
        if c.lower() not in [x.lower() for x in out]:
            out.append(c)
    if d.lower() not in [x.lower() for x in out]:
        out.insert(0, d)
    if len(out) > MAX:
        raise ValueError(f"{MAX} villes au maximum.")
    d = next(x for x in out if x.lower() == d.lower())
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps({"default": d, "list": out}))
    return {"default": d, "list": out}
