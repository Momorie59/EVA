from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import homeassistant as ha


class HaConfig(BaseModel):
    url: str
    token: str


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/homeassistant")

    @router.get("/status")
    async def status():
        return await ha.status()

    @router.put("")
    async def save(body: HaConfig):
        try:
            return await ha.save(body.url, body.token)
        except ha.HAError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("")
    async def remove():
        await ha.remove()
        return {"ok": True}

    return router
