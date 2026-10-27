"""Wiki (module activable) : pages famille et perso, historique, liens [[Titre]]."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from . import auth as auth_mod, wiki


class PageIn(BaseModel):
    espace: str = "famille"
    titre: str
    contenu: str = ""
    tags: list[str] = []


class PagePatch(BaseModel):
    titre: str | None = None
    contenu: str | None = None
    tags: list[str] | None = None
    base: str | None = None          # updated_at lu par l'éditeur (refus si quelqu'un a modifié entre-temps)


async def _moi(request: Request) -> tuple[str, str]:
    if not auth_mod.protected():
        return "", "admin"
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or "", me["role"]


def _err(e: wiki.WikiError) -> HTTPException:
    return HTTPException(e.status, str(e))


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/wiki")

    @r.get("")
    async def lister(request: Request, espace: str | None = Query(None), q: str = Query("", max_length=200)):
        qui, _ = await _moi(request)
        return {"pages": await wiki.lister(qui, espace, q)}

    @r.get("/titre")
    async def par_titre(request: Request, t: str = Query(..., min_length=1, max_length=200)):
        qui, _ = await _moi(request)
        p = await wiki.par_titre(qui, t)
        if p is None:
            raise HTTPException(404, "Page introuvable.")
        return p

    @r.post("")
    async def creer(request: Request, b: PageIn):
        qui, role = await _moi(request)
        try:
            return await wiki.creer(qui, b.espace, b.titre, b.contenu, b.tags, role)
        except wiki.WikiError as e:
            raise _err(e) from e

    @r.get("/{pid}")
    async def lire(request: Request, pid: int):
        qui, _ = await _moi(request)
        try:
            return await wiki.lire(qui, pid)
        except wiki.WikiError as e:
            raise _err(e) from e

    @r.put("/{pid}")
    async def modifier(request: Request, pid: int, b: PagePatch):
        qui, role = await _moi(request)
        try:
            return await wiki.modifier(qui, pid, b.titre, b.contenu, b.tags, b.base, role)
        except wiki.WikiError as e:
            raise _err(e) from e

    @r.delete("/{pid}")
    async def supprimer(request: Request, pid: int):
        qui, role = await _moi(request)
        try:
            await wiki.supprimer(qui, pid, role)
        except wiki.WikiError as e:
            raise _err(e) from e
        return {"ok": True}

    @r.get("/{pid}/versions")
    async def versions(request: Request, pid: int):
        qui, _ = await _moi(request)
        try:
            return {"versions": await wiki.versions(qui, pid)}
        except wiki.WikiError as e:
            raise _err(e) from e

    @r.get("/{pid}/versions/{vid}")
    async def version(request: Request, pid: int, vid: int):
        qui, _ = await _moi(request)
        try:
            return await wiki.version(qui, pid, vid)
        except wiki.WikiError as e:
            raise _err(e) from e

    @r.post("/{pid}/versions/{vid}/restaurer")
    async def restaurer(request: Request, pid: int, vid: int):
        qui, role = await _moi(request)
        try:
            return await wiki.restaurer(qui, pid, vid, role)
        except wiki.WikiError as e:
            raise _err(e) from e

    return r
