"""Modules facultatifs (Paramètres › Modules) : lecture pour tous (le menu s'adapte), réglage par l'administrateur."""
from fastapi import APIRouter

from . import modules


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/modules")

    @r.get("")
    async def lire():
        etats = await modules.charger()
        return {"modules": [{"id": k, **v, "actif": etats.get(k, False)} for k, v in modules.MODULES.items()]}

    @r.put("")
    async def regler(body: dict):
        await modules.regler({k: v for k, v in (body or {}).items() if isinstance(v, bool)})
        return await lire()

    return r
