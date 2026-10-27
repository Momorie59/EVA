from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import aiserver


class Cfg(BaseModel):
    url: str = ""


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/aiserver")

    @router.get("/stats")
    async def stats():
        return await aiserver.stats()

    @router.get("/power")
    async def power(period: str = "24h"):
        return await aiserver.power(period)

    @router.get("/config")
    async def get_cfg():
        return {"url": await aiserver.get_url(), "default": aiserver.default_url()}

    @router.put("/config")
    async def put_cfg(b: Cfg):
        try:
            return {"url": await aiserver.set_url(b.url), "default": aiserver.default_url()}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
