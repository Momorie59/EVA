"""Qui voit quels projets : chaque projet a un propriétaire et peut être partagé (avec des personnes, ou tout le monde « * »).
Un projet sans fiche (créé avant cette règle, ou par EVA seule) reste visible de tous. L'administrateur voit tout.
Stockage : une ligne `kv` « project_acl » = {slug: {"owner": nom, "shared": [noms] | ["*"]}}."""
import json

from .db import get_pool

KEY = "project_acl"


async def load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KEY)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else {}


async def save(data: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KEY, json.dumps(data))


def can_open(meta: dict | None, user: str, role: str) -> bool:
    if not user or role == "admin" or not meta:
        return True
    shared = [str(s).lower() for s in meta.get("shared", [])]
    return str(meta.get("owner", "")).lower() == user.lower() or user.lower() in shared or "*" in shared


def is_owner(meta: dict | None, user: str, role: str) -> bool:
    return not user or role == "admin" or not meta or str(meta.get("owner", "")).lower() == user.lower()


async def set_owner(slug: str, owner: str) -> None:
    if not owner:
        return
    data = await load()
    data[slug] = {"owner": owner, "shared": []}
    await save(data)


async def set_shared(slug: str, names: list[str]) -> list[str]:
    clean = sorted({str(n).strip() for n in names if str(n).strip()})[:50]
    clean = ["*"] if "*" in clean else clean
    data = await load()
    meta = data.get(slug) or {"owner": ""}
    meta["shared"] = clean
    data[slug] = meta
    await save(data)
    return clean


async def forget(slug: str) -> None:
    data = await load()
    if data.pop(slug, None) is not None:
        await save(data)
