"""Interface : post-it (CRUD) et thème personnalisé (couleurs, disposition) conservé côté serveur."""
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fastapi import Depends, Request

from . import auth as auth_mod, notes, profiles as profiles_mod
from .db import get_pool

THEME_MAX_BYTES = 20_000


class NoteIn(BaseModel):
    text: str
    color: str | None = None
    x: float | None = None
    y: float | None = None


class NoteEdit(BaseModel):
    shared: list[str] | None = None
    text: str | None = None
    color: str | None = None
    x: float | None = None
    y: float | None = None
    done: bool | None = None


async def _note_user(request: Request) -> None:
    """Chaque personne ne voit que ses post-it et ceux qu'on a partagés avec elle."""
    name = ""
    if auth_mod.protected():
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
        name = me["user"] if me else ""
    profiles_mod.user_var.set(name)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api")
    notes_dep = [Depends(_note_user)]

    @router.get("/notes/people", dependencies=notes_dep)
    async def note_people():
        me = profiles_mod.user_var.get().lower()
        return {"users": [u["user"] for u in auth_mod.list_users() if u["user"].lower() != me and not u["disabled"]]}

    @router.get("/notes", dependencies=notes_dep)
    async def list_notes():
        return {"notes": await notes.list_notes()}

    @router.post("/notes", dependencies=notes_dep)
    async def create_note(body: NoteIn):
        try:
            return await notes.create(body.text, body.color, body.x, body.y, by="user")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/notes/{note_id}", dependencies=notes_dep)
    async def edit_note(note_id: int, body: NoteEdit):
        try:
            n = await notes.update(note_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if n is None:
            raise HTTPException(status_code=404, detail="Post-it introuvable.")
        return n

    @router.delete("/notes/{note_id}", dependencies=notes_dep)
    async def remove_note(note_id: int):
        if not await notes.delete(note_id):
            raise HTTPException(status_code=404, detail="Post-it introuvable.")
        return {"ok": True}

    @router.delete("/notes", dependencies=notes_dep)
    async def clear_notes(done_only: bool = Query(False)):
        return {"deleted": await notes.clear(done_only)}

    @router.get("/ui/theme")
    async def get_theme():
        async with get_pool().acquire() as conn:
            v = await conn.fetchval("SELECT value FROM kv WHERE key='ui_theme'")
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                v = None
        return {"theme": v if isinstance(v, dict) else None}

    @router.put("/ui/theme")
    async def put_theme(body: dict):
        theme = body.get("theme")
        if theme is None:                                   # réinitialiser
            async with get_pool().acquire() as conn:
                await conn.execute("DELETE FROM kv WHERE key='ui_theme'")
            return {"theme": None}
        if not isinstance(theme, dict) or len(json.dumps(theme)) > THEME_MAX_BYTES:
            raise HTTPException(status_code=400, detail="Thème invalide ou trop volumineux.")
        async with get_pool().acquire() as conn:
            await conn.execute("INSERT INTO kv (key, value) VALUES ('ui_theme', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                               json.dumps(theme))
        return {"theme": theme}

    return router
