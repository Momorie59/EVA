"""Mode miroir (voir miroir.py) : modèles, visages appris, reconnaissance, tuiles."""
import asyncio

from fastapi import APIRouter, HTTPException, Request

from . import auth as auth_mod
from . import miroir


async def _moi(request: Request) -> tuple[str, str]:
    if not auth_mod.protected():
        return "", "admin"
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or "", me["role"]


def _role_de(qui: str) -> str | None:
    u = next((x for x in auth_mod.list_users() if x["user"].lower() == (qui or "").lower()), None)
    return u["role"] if u and not u.get("disabled") else None


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/miroir")

    @r.get("/etat")
    async def etat(request: Request):
        moi, _ = await _moi(request)
        return {**await miroir.etat(), "moi": moi, "comptes": [u["user"] for u in auth_mod.list_users() if not u.get("disabled")]}

    @r.post("/modeles")
    async def modeles(request: Request):
        _, role = await _moi(request)
        if role != "admin":
            raise HTTPException(403, "Réservé à l'administrateur.")
        asyncio.get_running_loop().create_task(miroir.telecharger())
        return {"ok": True}

    @r.post("/visages")
    async def apprendre(request: Request, body: dict):
        moi, role = await _moi(request)
        qui = (body or {}).get("qui") or moi
        if role != "admin" and qui.lower() != moi.lower():
            raise HTTPException(403, "Tu ne peux apprendre que ton propre visage.")
        if auth_mod.protected() and _role_de(qui) is None:
            raise HTTPException(404, "Compte inconnu.")
        try:
            return await miroir.apprendre(qui, (body or {}).get("images") or [])
        except miroir.MiroirError as e:
            raise HTTPException(e.status, str(e)) from e

    @r.delete("/visages/{qui}")
    async def oublier(request: Request, qui: str):
        moi, role = await _moi(request)
        if role != "admin" and qui.lower() != moi.lower():
            raise HTTPException(403, "Tu ne peux effacer que ton propre visage.")
        return {"effaces": await miroir.oublier(qui)}

    @r.post("/regarder")
    async def regarder(request: Request, body: dict):
        await _moi(request)
        try:
            return await miroir.regarder((body or {}).get("image") or "")
        except miroir.MiroirError as e:
            raise HTTPException(e.status, str(e)) from e

    @r.get("/cartes")
    async def cartes(request: Request, qui: str = ""):
        moi, role = await _moi(request)
        if qui and role != "admin" and qui.lower() != moi.lower():
            qui = ""                                      # pas le droit de voir les infos d'un autre : tuiles générales
        r_qui = _role_de(qui) if qui else None
        if qui and auth_mod.protected() and r_qui is None:
            qui = ""
        return await miroir.cartes(qui or None, r_qui or role)

    return r
