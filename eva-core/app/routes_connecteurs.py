"""Paramètres › Services connectés : OBS, Discord, Instagram, Twilio (administrateur seulement)."""
from fastapi import APIRouter, HTTPException

from . import connecteurs as cx


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/connecteurs")

    @r.get("")
    async def etat():
        return await cx.etat()

    @r.put("/{service}")
    async def enregistrer(service: str, body: dict):
        try:
            return await cx.enregistrer(service, body or {})
        except (cx.ConnecteurError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/{service}/tester")
    async def tester(service: str):
        try:
            return await cx.tester(service)
        except cx.ConnecteurError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.delete("/{service}")
    async def oublier(service: str):
        if service not in cx.SERVICES:
            raise HTTPException(status_code=404, detail="Service inconnu.")
        await cx.oublier(service)
        return {"ok": True}

    return r
