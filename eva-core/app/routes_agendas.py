"""Agendas iCal : chacun gère ses abonnements (lecture seule pour EVA)."""
from fastapi import APIRouter, HTTPException, Request

from . import agendas, auth as auth_mod


async def _qui(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or ""


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/agendas")

    @r.get("")
    async def lister(request: Request):
        return {"agendas": await agendas.lister(await _qui(request))}

    @r.post("")
    async def ajouter(request: Request, body: dict):
        try:
            return {"agendas": await agendas.ajouter(await _qui(request), body.get("nom", ""), body.get("url", ""))}
        except agendas.AgendaError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.post("/retirer")
    async def retirer(request: Request, body: dict):
        return {"agendas": await agendas.retirer(await _qui(request), str(body.get("url", "")))}

    @r.get("/a-venir")
    async def a_venir(request: Request, jours: int = 7):
        try:
            return await agendas.a_venir(await _qui(request), jours)
        except agendas.AgendaError as exc:
            raise HTTPException(400, str(exc)) from exc

    return r
