"""Mes autorisations « toujours » : voir et retirer."""
from fastapi import APIRouter, HTTPException, Request

from . import auth, autorisations


async def _moi(request: Request) -> str:
    me = await auth.identify(auth.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or ""


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/autorisations")

    @r.get("")
    async def lire(request: Request):
        return {"outils": await autorisations.lister(await _moi(request))}

    @r.delete("")
    async def tout_retirer(request: Request):
        await autorisations.revoke(await _moi(request))
        return {"outils": []}

    @r.delete("/{outil}")
    async def retirer(outil: str, request: Request):
        qui = await _moi(request)
        await autorisations.revoke(qui, outil)
        return {"outils": await autorisations.lister(qui)}

    return r
