"""API de l'inventaire et des prêts (page Inventaire)."""
from fastapi import APIRouter, HTTPException, Request

from . import auth as auth_mod
from . import inventaire


async def _qui(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or ""


def _err(e: inventaire.InventaireError) -> HTTPException:
    return HTTPException(e.status, str(e))


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/inventaire")

    @r.get("")
    async def lister(request: Request, q: str = "", lieu: str = ""):
        qui = await _qui(request)
        return {"objets": await inventaire.lister(qui, q, lieu), "lieux": await inventaire.lieux(qui), "prets": await inventaire.prets(qui)}

    @r.post("")
    async def ranger(request: Request, body: dict):
        b = body or {}
        try:
            return await inventaire.ranger(await _qui(request), b.get("nom", ""), b.get("emplacement", ""), b.get("quantite"),
                                           b.get("notes"), b.get("prive"), b.get("id"))
        except inventaire.InventaireError as e:
            raise _err(e) from e

    @r.delete("/{oid}")
    async def retirer(request: Request, oid: int):
        try:
            await inventaire.retirer(await _qui(request), oid)
        except inventaire.InventaireError as e:
            raise _err(e) from e
        return {"ok": True}

    @r.post("/prets")
    async def preter(request: Request, body: dict):
        b = body or {}
        try:
            return await inventaire.preter(await _qui(request), b.get("objet", ""), b.get("personne", ""), b.get("sens", "prete"), b.get("retour"))
        except inventaire.InventaireError as e:
            raise _err(e) from e

    @r.post("/prets/{pid}/rendu")
    async def rendu(request: Request, pid: int):
        if not await inventaire.rendre(await _qui(request), pid=pid):
            raise HTTPException(404, "Prêt introuvable ou déjà rendu.")
        return {"ok": True}

    @r.get("/prets")
    async def prets(request: Request, tous: bool = False):
        return {"prets": await inventaire.prets(await _qui(request), tous)}

    return r
