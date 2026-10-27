"""Connexion à GitHub et dépôts d'EVA (administrateur uniquement)."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import auth, autorisations, github as gh


class Jeton(BaseModel):
    token: str


class Clone(BaseModel):
    repo: str


class Commit(BaseModel):
    message: str


class Push(BaseModel):
    confirme: bool = False
    toujours: bool = False


async def _admin(request: Request) -> None:
    me = await auth.identify(auth.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if me["role"] != "admin":
        raise HTTPException(403, "Réservé à un administrateur.")
    request.state.qui = me["user"] or ""


def make_router(workspace_root: Path) -> APIRouter:
    r = APIRouter(prefix="/api/github", dependencies=[Depends(_admin)])

    async def run(coro):
        try:
            return await coro
        except gh.GitHubError as e:
            raise HTTPException(e.status, str(e)) from e

    @r.get("")
    async def etat(request: Request):
        return {**await gh.status(), "push_auto": await autorisations.allowed(request.state.qui, "github_push")}

    @r.put("/token")
    async def token(b: Jeton):
        return await run(gh.connect(b.token))

    @r.delete("/token")
    async def deconnecter():
        return await gh.disconnect()

    @r.get("/repos")
    async def repos():
        return {"repos": await run(gh.repos())}

    @r.get("/depots")
    async def depots():
        return {"depots": await gh.depots(workspace_root)}

    @r.post("/depots")
    async def cloner(b: Clone):
        return await run(gh.cloner(b.repo, workspace_root))

    @r.get("/depots/{nom}/etat")
    async def e(nom: str):
        return await run(gh.etat(nom, workspace_root))

    @r.get("/depots/{nom}/historique")
    async def h(nom: str):
        return {"commits": await run(gh.historique(nom, 15, workspace_root))}

    @r.get("/depots/{nom}/differences")
    async def d(nom: str):
        return await run(gh.differences(nom, workspace_root))

    @r.post("/depots/{nom}/commit")
    async def c(nom: str, b: Commit):
        return await run(gh.commit(nom, b.message, workspace_root))

    @r.post("/depots/{nom}/recuperer")
    async def pull(nom: str):
        return await run(gh.recuperer(nom, workspace_root))

    @r.post("/depots/{nom}/envoyer")
    async def push(nom: str, b: Push, request: Request):
        qui = request.state.qui
        deja = await autorisations.allowed(qui, "github_push")
        if b.confirme and b.toujours and not deja:
            await autorisations.allow(qui, "github_push")      # « toujours envoyer sans demander » : retirable dans Sécurité & données
        return await run(gh.pousser(nom, b.confirme or deja, workspace_root))

    @r.delete("/depots/{nom}")
    async def rm(nom: str):
        await run(gh.supprimer_copie(nom, workspace_root))
        return {"ok": True}

    return r
