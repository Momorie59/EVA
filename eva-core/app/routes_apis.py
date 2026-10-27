from fastapi import APIRouter

from . import api_catalog


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/apis")

    @router.get("/status")
    async def status():
        return await api_catalog.status()

    @router.post("/update")
    async def update():
        return await api_catalog.update(force=True)

    return router
