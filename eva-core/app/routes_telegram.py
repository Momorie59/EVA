from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import telegram as tg


class TgConfig(BaseModel):
    token: str = ""
    allowed: str = ""
    alerts: bool = True


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/telegram")

    @router.get("/status")
    async def status():
        return await tg.status()

    @router.put("")
    async def save(body: TgConfig):
        try:
            return await tg.save(body.token, body.allowed, body.alerts)
        except tg.TelegramError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("")
    async def remove():
        await tg.remove()
        return {"ok": True}

    return router
