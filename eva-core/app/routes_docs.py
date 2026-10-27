import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import auth as auth_mod, docs


async def _scope(request: Request) -> None:
    """Un utilisateur standard ne cherche que dans ses propres conversations et les dossiers partagés."""
    owner = None
    if auth_mod.protected():
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
        if me is not None and me["role"] != "admin":
            owner = me["user"]
    docs.owner_var.set(owner)


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/docs", dependencies=[Depends(_scope)])
    state = {"last": None, "error": None}

    @router.get("/status")
    async def status():
        s = await docs.status()
        s["last_result"] = state["last"]
        s["last_error"] = state["error"]
        return s

    @router.post("/reindex")
    async def reindex():
        if docs._lock.locked():
            raise HTTPException(status_code=409, detail="Une indexation est déjà en cours.")

        async def job():
            try:
                state["last"], state["error"] = await docs.reindex(), None
            except docs.DocsError as exc:
                state["error"] = str(exc)
            except Exception as exc:  # noqa: BLE001
                state["error"] = f"Erreur inattendue : {exc}"

        asyncio.create_task(job())
        return {"started": True}

    @router.get("/search")
    async def search(q: str = Query(..., min_length=1), k: int = 5, kind: str | None = None):
        if kind not in (None, "file", "message"):
            raise HTTPException(status_code=400, detail="kind doit être file ou message.")
        try:
            return {"results": await docs.search(q, k, kind)}
        except docs.DocsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
