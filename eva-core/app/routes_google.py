from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import google as g


class Client(BaseModel):
    client_id: str
    client_secret: str


class Redirected(BaseModel):
    url: str


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/google")

    def _err(exc: g.GoogleError) -> HTTPException:
        return HTTPException(status_code=400, detail=str(exc))

    @router.get("/status")
    async def status():
        return await g.status()

    @router.put("/client")
    async def client(body: Client):
        try:
            await g.set_client(body.client_id, body.client_secret)
        except g.GoogleError as exc:
            raise _err(exc) from exc
        return await g.status()

    @router.get("/auth-url")
    async def auth_url():
        try:
            return {"url": await g.auth_url()}
        except g.GoogleError as exc:
            raise _err(exc) from exc

    @router.post("/complete")
    async def complete(body: Redirected):
        try:
            return await g.complete(body.url)
        except g.GoogleError as exc:
            raise _err(exc) from exc

    @router.delete("")
    async def disconnect():
        await g.disconnect()
        return {"ok": True}

    return router
