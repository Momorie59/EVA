from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import rooms


class Ice(BaseModel):
    servers: list[dict] = []


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/room")

    @router.get("")
    async def state():
        return {"users": rooms.hub.users(), "call": rooms.hub.participants(), "max_call": rooms.MAX_CALL}

    @router.get("/ice")
    async def ice():
        return {"servers": await rooms.ice_get()}

    @router.put("/ice")
    async def put_ice(b: Ice):
        try:
            return {"servers": await rooms.ice_set(b.servers)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/messages")
    async def clear():
        await rooms.hub.clear()
        return {"ok": True}

    return router
