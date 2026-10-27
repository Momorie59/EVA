from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from . import backup

MAX_UPLOAD = 300 * 1024 * 1024


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/backup")

    @router.get("")
    async def listing():
        return {"backups": backup.listing()}

    @router.post("")
    async def create():
        return await backup.create()

    @router.get("/file/{name}")
    async def download(name: str):
        p = backup.path_of(name)
        if p is None:
            raise HTTPException(status_code=404, detail="Sauvegarde introuvable.")
        return FileResponse(p, media_type="application/zip", filename=name)

    @router.post("/restore")
    async def restore(request: Request):
        # Corps brut (application/zip) : évite la dépendance à python-multipart.
        data = await request.body()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="Archive trop volumineuse.")
        try:
            return await backup.restore(data)
        except backup.BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
