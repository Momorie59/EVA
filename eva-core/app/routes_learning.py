from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import learning
from . import skills as skills_mod


class FeedbackBody(BaseModel):
    rating: int
    comment: str = ""


def make_router(workspace_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/messages/{message_id}/feedback")
    async def feedback(message_id: int, body: FeedbackBody):
        if body.rating not in (-1, 0, 1):
            raise HTTPException(status_code=400, detail="rating doit valoir -1, 0 ou 1.")
        if not await learning.set_feedback(message_id, body.rating, body.comment):
            raise HTTPException(status_code=404, detail="Réponse introuvable.")
        return {"ok": True}

    @router.get("/learning")
    async def report(days: int = Query(30, ge=1, le=365)):
        return await learning.report(days)

    @router.post("/skills/{name}/optimize")
    async def optimize(name: str):
        try:
            return await learning.optimize_skill(name, workspace_root)
        except skills_mod.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
