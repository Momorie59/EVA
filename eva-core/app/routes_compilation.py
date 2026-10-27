"""Compilation automatique des conversations : état, réglages, « Compiler maintenant » (Paramètres › Intelligence)."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import compilation


class Reglage(BaseModel):
    heure: int | None = None
    actif: bool | None = None


def make_router(workspace: Path) -> APIRouter:
    r = APIRouter(prefix="/api/compilation")

    @r.get("")
    async def lire():
        return await compilation.etat()

    @r.put("")
    async def regler(b: Reglage):
        try:
            return await compilation.regler(b.heure, b.actif)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @r.post("/lancer")
    async def lancer():
        return {"lancee": compilation.lancer(workspace), **(await compilation.etat())}

    return r
