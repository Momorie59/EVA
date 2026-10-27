import functools

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import auth as auth_mod, features as features_mod, notebooks as nbk


class NbIn(BaseModel):
    title: str | None = None
    icon: str | None = None
    color: str | None = None


class Shares(BaseModel):
    shares: list[dict] = []


class SecIn(BaseModel):
    title: str = ""


class PageIn(BaseModel):
    title: str | None = None
    text: str | None = None
    base: float | None = None
    move_to: str | None = None


async def _who(request: Request) -> dict:
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    groups = []
    if me["role"] != "admin":
        groups = (await features_mod._load())["users"].get(me["user"].lower(), {}).get("groups", [])
    return {"user": me["user"], "role": me["role"], "groups": groups}


def _guard(fn):
    @functools.wraps(fn)
    async def run(*a, **k):
        try:
            return await fn(*a, **k)
        except nbk.NotebookError as exc:
            raise HTTPException(exc.status, {"message": str(exc), **exc.extra} if exc.extra else str(exc)) from exc
    return run


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/notebooks")

    @router.get("")
    async def mine(request: Request):
        return {"notebooks": await nbk.list_for(await _who(request))}

    @router.get("/people")
    async def people(request: Request):
        """Avec qui partager : les comptes (sauf soi) et les groupes."""
        who = await _who(request)
        d = await features_mod._load()
        return {"users": [u["user"] for u in auth_mod.list_users() if u["user"].lower() != who["user"].lower() and not u["disabled"]],
                "groups": [{"id": g, "label": v.get("label", g)} for g, v in d["groups"].items()]}

    @router.post("")
    @_guard
    async def create(request: Request, b: NbIn):
        return await nbk.create(await _who(request), b.title or "", b.icon or "📓", b.color or "jaune")

    @router.get("/{nid}")
    @_guard
    async def one(request: Request, nid: str):
        return await nbk.get_for(nid, await _who(request))

    @router.put("/{nid}")
    @_guard
    async def upd(request: Request, nid: str, b: NbIn):
        return await nbk.update(nid, await _who(request), b.title, b.icon, b.color)

    @router.delete("/{nid}")
    @_guard
    async def rm(request: Request, nid: str):
        await nbk.delete(nid, await _who(request))
        return {"ok": True}

    @router.put("/{nid}/shares")
    @_guard
    async def shares(request: Request, nid: str, b: Shares):
        d = await features_mod._load()
        users = {u["user"].lower() for u in auth_mod.list_users()}
        return {"shares": await nbk.set_shares(nid, await _who(request), b.shares, {g: v.get("label", g) for g, v in d["groups"].items()}, users)}

    @router.post("/{nid}/sections")
    @_guard
    async def add_sec(request: Request, nid: str, b: SecIn):
        return await nbk.add_section(nid, await _who(request), b.title)

    @router.put("/{nid}/sections/{sid}")
    @_guard
    async def ren_sec(request: Request, nid: str, sid: str, b: SecIn):
        await nbk.rename_section(nid, sid, await _who(request), b.title)
        return {"ok": True}

    @router.delete("/{nid}/sections/{sid}")
    @_guard
    async def del_sec(request: Request, nid: str, sid: str):
        await nbk.delete_section(nid, sid, await _who(request))
        return {"ok": True}

    @router.post("/{nid}/sections/{sid}/pages")
    @_guard
    async def add_pg(request: Request, nid: str, sid: str, b: PageIn):
        return await nbk.add_page(nid, sid, await _who(request), b.title or "", b.text or "")

    @router.put("/{nid}/pages/{pid}")
    @_guard
    async def save_pg(request: Request, nid: str, pid: str, b: PageIn):
        return await nbk.save_page(nid, pid, await _who(request), b.title, b.text, b.base, b.move_to)

    @router.delete("/{nid}/pages/{pid}")
    @_guard
    async def del_pg(request: Request, nid: str, pid: str):
        await nbk.delete_page(nid, pid, await _who(request))
        return {"ok": True}

    return router
