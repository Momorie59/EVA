"""Tâches en fond : liste (les siennes ; toutes pour l'administrateur) et annulation."""
from fastapi import APIRouter, HTTPException, Request

from . import auth as auth_mod, taches_fond


async def _moi(request: Request) -> tuple[str, bool]:
    if not auth_mod.protected():
        return "", True
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or "", me["role"] == "admin"


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/taches-fond")

    @r.get("")
    async def lister(request: Request):
        qui, admin = await _moi(request)
        return {"taches": await taches_fond.lister(qui, admin)}

    @r.delete("/{tid}")
    async def annuler(tid: str, request: Request):
        qui, admin = await _moi(request)
        if not await taches_fond.annuler(tid, qui, admin):
            raise HTTPException(404, "Tâche introuvable.")
        return {"ok": True}

    return r
