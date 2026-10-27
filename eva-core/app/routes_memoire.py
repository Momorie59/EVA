"""Page Mémoire : chacun voit, corrige, désactive ou efface ce qu'EVA retient de lui, et peut couper sa mémoire."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import auth, memoire


class SouvenirIn(BaseModel):
    texte: str
    kind: str | None = None


class SouvenirPatch(BaseModel):
    texte: str | None = None
    kind: str | None = None
    actif: bool | None = None


class ReglageIn(BaseModel):
    actif: bool


async def _moi_role(request: Request) -> tuple[str, str]:
    me = await auth.identify(auth.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or "", me["role"]


async def _moi(request: Request) -> str:
    return (await _moi_role(request))[0]


def _err(e: memoire.MemoireError):
    return HTTPException(e.status, str(e))


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/memoire")

    @r.get("")
    async def lire(request: Request):
        qui = await _moi(request)
        return {"actif": await memoire.active(qui), "sortes": memoire.SORTES, "souvenirs": await memoire.lister(qui), "reprise": memoire.REPRISE.get(qui.strip().lower())}

    @r.post("")
    async def ajouter(b: SouvenirIn, request: Request):
        try:
            return await memoire.ajouter(await _moi(request), b.texte, b.kind)
        except memoire.MemoireError as e:
            raise _err(e) from e

    @r.patch("/{mid}")
    async def modifier(mid: int, b: SouvenirPatch, request: Request):
        try:
            return await memoire.modifier(await _moi(request), mid, b.texte, b.kind, b.actif)
        except memoire.MemoireError as e:
            raise _err(e) from e

    @r.delete("/{mid}")
    async def supprimer(mid: int, request: Request):
        try:
            await memoire.supprimer(await _moi(request), mid)
        except memoire.MemoireError as e:
            raise _err(e) from e
        return {"ok": True}

    @r.post("/reprendre")
    async def reprendre(request: Request):
        qui, role = await _moi_role(request)
        if not await memoire.active(qui):
            raise HTTPException(409, "Ta mémoire est coupée : rallume-la d'abord.")
        return {"demarre": memoire.lancer_reprise(qui, admin=(role == "admin"))}

    @r.put("/reglage")
    async def reglage(b: ReglageIn, request: Request):
        return {"actif": await memoire.set_active(await _moi(request), b.actif)}

    return r
