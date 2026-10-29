"""Réglages des infos pratiques (Paramètres › Services connectés) et aperçu."""
from fastapi import APIRouter, HTTPException

from . import pratique


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/pratique")

    @r.get("/reglages")
    async def lire():
        return {**await pratique.reglages(), "bacs_possibles": pratique.BACS, "carburants": pratique.CARBURANTS}

    @r.put("/reglages")
    async def regler(body: dict):
        try:
            return await pratique.regler(body or {})
        except pratique.PratiqueError as e:
            raise HTTPException(400, str(e)) from e

    @r.get("/apercu/{quoi}")
    async def apercu(quoi: str):
        f = {"poubelles": pratique.poubelles, "vacances": pratique.vacances, "carburants": pratique.carburants,
             "ephemeride": pratique.ephemeride, "actu": pratique.actu}.get(quoi)
        if not f:
            raise HTTPException(404, "Inconnu.")
        try:
            return await f()
        except pratique.PratiqueError as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Service injoignable ({type(e).__name__})."}

    return r
