from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import auth as auth_mod, fil, project_acl, sessions as sessions_db


class SessionCreate(BaseModel):
    title: str = ""


class SessionRename(BaseModel):
    title: str | None = None
    project: str | None = None          # "" = détacher du projet


class Suppression(BaseModel):
    ids: list[str] = []
    tout: bool = False                  # toutes MES conversations
    personne: str | None = None         # administrateur : toutes les conversations de cette personne


class Rattachement(BaseModel):
    ids: list[str]
    project: str = ""


class FilIn(BaseModel):
    resume: str


async def _moi(request: Request) -> dict:
    if not auth_mod.protected():
        return {"user": "", "role": "admin"}
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return me


async def _owner(request: Request) -> str | None:
    """None = administrateur (voit tout) ; sinon le nom de l'utilisateur, qui ne voit que ses propres conversations."""
    if not auth_mod.protected():
        return None
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    return None if me is None or me["role"] == "admin" else me["user"]


async def _check(request: Request, session_id: str) -> None:
    if not await sessions_db.can_access(session_id, await _owner(request)):
        raise HTTPException(status_code=404, detail="Conversation introuvable.")


def make_router(workspace: Path | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/sessions")
    ws = Path(workspace) if workspace else None

    async def projet_permis(request: Request, slug: str) -> None:
        if not slug:
            return
        if ws is None or not (ws / "projets" / slug).is_dir():
            raise HTTPException(status_code=404, detail="Projet introuvable.")
        me = await _moi(request)
        if not project_acl.can_open((await project_acl.load()).get(slug), me["user"], me["role"]):
            raise HTTPException(status_code=403, detail="Ce projet ne t'est pas partagé.")

    async def supprimer_liste(request: Request, ids: list[str]) -> int:
        owner = await _owner(request)
        n = 0
        for sid in ids:
            if sid == "default" or not await sessions_db.can_access(sid, owner):
                continue
            if await sessions_db.delete_session(sid):
                n += 1
        return n

    # Routes à chemin fixe d'abord (sinon « /supprimer » serait pris pour un identifiant de conversation).
    @router.get("/corbeille")
    async def corbeille(request: Request):
        """Conversations supprimées depuis moins de 30 jours (récupérables)."""
        return {"conversations": await sessions_db.corbeille(await _owner(request)), "jours": sessions_db.CORBEILLE_JOURS}

    @router.post("/corbeille/restaurer")
    async def corbeille_restaurer(request: Request, body: Suppression):
        owner = await _owner(request)
        n = 0
        for sid in list(dict.fromkeys(body.ids))[:2000]:
            if await sessions_db.can_access(sid, owner) and await sessions_db.restaurer(sid):
                n += 1
        return {"restaurees": n}

    @router.post("/corbeille/vider")
    async def corbeille_vider(request: Request, body: Suppression):
        """Efface pour de bon : les conversations données, ou toute ma corbeille (tout=true)."""
        owner = await _owner(request)
        dans = {c["id"] for c in await sessions_db.corbeille(owner)}
        ids = list(dans) if body.tout else [i for i in dict.fromkeys(body.ids) if i in dans]
        n = 0
        for sid in ids[:2000]:
            if await sessions_db.effacer_session(sid):
                n += 1
        return {"effacees": n}

    @router.post("/supprimer")
    async def supprimer(request: Request, body: Suppression):
        """Supprime plusieurs conversations : une liste, toutes les miennes, ou (administrateur) toutes celles d'une personne."""
        me = await _moi(request)
        ids = list(dict.fromkeys(body.ids))[:2000]
        if body.personne is not None:
            if me["role"] != "admin":
                raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
            ids += await sessions_db.ids_of_owner(body.personne.lower())
        if body.tout:
            ids += await sessions_db.ids_of_owner("" if me["role"] == "admin" else me["user"])
        n = await supprimer_liste(request, list(dict.fromkeys(ids)))
        await auth_mod.audit("action", me["user"], "", "Suppression de conversations", f"{n} supprimée(s)", 200)
        return {"supprimees": n}

    @router.post("/rattacher")
    async def rattacher(request: Request, body: Rattachement):
        slug = (body.project or "").strip()
        await projet_permis(request, slug)
        owner = await _owner(request)
        n = 0
        for sid in list(dict.fromkeys(body.ids))[:500]:
            if await sessions_db.can_access(sid, owner):
                await fil.rattacher(sid, slug, ws)
                n += 1
        return {"rattachees": n, "project": slug}

    @router.post("/projets/{slug}/fil")
    async def compiler_projet(request: Request, slug: str):
        await projet_permis(request, slug)
        return {"fil": await fil.compiler_projet(ws, slug)}

    @router.get("")
    async def list_all(request: Request):
        return {"sessions": await sessions_db.list_sessions(owner=await _owner(request))}

    @router.post("")
    async def create(request: Request, body: SessionCreate | None = None):
        return await sessions_db.create_session(body.title if body else "", owner=await _owner(request) or "")

    @router.get("/search")
    async def search(request: Request, q: str = ""):
        return {"results": await sessions_db.search_sessions(q, owner=await _owner(request))}

    @router.get("/{session_id}/messages")
    async def messages(request: Request, session_id: str):
        await _check(request, session_id)
        from . import plans
        return {"messages": await sessions_db.get_messages(session_id), "plan": await plans.lire(session_id)}

    @router.patch("/{session_id}")
    async def rename(request: Request, session_id: str, body: SessionRename):
        await _check(request, session_id)
        if body.title is not None:
            if not body.title.strip():
                raise HTTPException(status_code=400, detail="Titre vide.")
            if not await sessions_db.rename_session(session_id, body.title):
                raise HTTPException(status_code=404, detail="Conversation introuvable.")
        if body.project is not None:
            slug = body.project.strip()
            await projet_permis(request, slug)
            await sessions_db.ensure_session(session_id, owner=await _owner(request) or "")
            await fil.rattacher(session_id, slug, ws)
        return {"ok": True}

    @router.get("/{session_id}/fil")
    async def lire_fil(request: Request, session_id: str):
        await _check(request, session_id)
        return await fil.etat(session_id)

    @router.put("/{session_id}/fil")
    async def corriger_fil(request: Request, session_id: str, body: FilIn):
        await _check(request, session_id)
        return await fil.corriger(session_id, body.resume)

    @router.post("/{session_id}/fil")
    async def compiler_fil(request: Request, session_id: str):
        """Compile tout de suite le fil conducteur (tous les échanges, même récents)."""
        await _check(request, session_id)
        try:
            return await fil.mettre_a_jour(session_id, ws, force=True)
        except Exception as exc:  # noqa: BLE001 — Ollama injoignable…
            raise HTTPException(status_code=503, detail=f"Fil non compilé : {exc}") from exc

    @router.delete("/{session_id}")
    async def delete(request: Request, session_id: str):
        await _check(request, session_id)
        if not await sessions_db.delete_session(session_id):
            raise HTTPException(status_code=404, detail="Conversation introuvable.")
        return {"ok": True}

    return router
