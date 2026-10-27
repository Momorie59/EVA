from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import mcp


class McpServer(BaseModel):
    name: str
    url: str
    headers: dict | None = None
    trusted: bool = False
    enabled: bool = True


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/mcp")

    @router.get("")
    async def listing():
        return {"servers": await mcp.status()}

    @router.put("")
    async def save(body: McpServer):
        try:
            await mcp.save(body.name, body.url, body.headers, body.trusted, body.enabled)
        except mcp.McpError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"servers": await mcp.status()}

    @router.post("/{name}/refresh")
    async def refresh(name: str):
        await mcp.refresh(name)
        return {"servers": await mcp.status()}

    @router.delete("/{name}")
    async def remove(name: str):
        if not await mcp.remove(name):
            raise HTTPException(status_code=404, detail="Serveur inconnu.")
        return {"ok": True}

    return router
