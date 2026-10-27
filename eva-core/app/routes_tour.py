import json
import time

from fastapi import APIRouter, Header

from . import auth as auth_mod
from .db import get_pool

KV = "tours"


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/tour")

    @router.get("")
    async def seen(authorization: str | None = Header(default=None)):
        """La visite guidée de première connexion a-t-elle déjà été vue par cette personne ?"""
        me = await auth_mod.identify(auth_mod.bearer(authorization))
        return {"seen": bool(me and me["user"] in await _load())}

    @router.post("/seen")
    async def done(authorization: str | None = Header(default=None)):
        me = await auth_mod.identify(auth_mod.bearer(authorization))
        if me and me["user"]:
            d = await _load()
            d[me["user"]] = time.strftime("%Y-%m-%dT%H:%M:%S")
            async with get_pool().acquire() as conn:
                await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
        return {"seen": True}

    @router.delete("")
    async def reset(authorization: str | None = Header(default=None)):
        """« Revoir la visite » : on l'oublie pour cette personne (elle se relance d'elle-même au prochain chargement)."""
        me = await auth_mod.identify(auth_mod.bearer(authorization))
        if me and me["user"]:
            d = await _load()
            d.pop(me["user"], None)
            async with get_pool().acquire() as conn:
                await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
        return {"seen": False}

    return router
