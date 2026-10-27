from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import identity as idn

MAX_BODY = 12 * 1024 * 1024


class NameBody(BaseModel):
    name: str


class SettingsBody(BaseModel):
    voice_id: bool | None = None
    face_id: bool | None = None
    voice_threshold: float | None = None
    face_threshold: float | None = None
    restrict_unknown: bool | None = None
    fresh_seconds: int | None = None
    face_liveness: bool | None = None
    style_id: bool | None = None


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/identity")

    async def body_of(request: Request) -> bytes:
        data = await request.body()
        if not data or len(data) > MAX_BODY:
            raise HTTPException(status_code=400, detail="Corps vide ou trop gros.")
        return data

    def wrap(exc: idn.IdentityError):
        return HTTPException(status_code=400, detail=str(exc))

    @router.get("/status")
    async def status():
        return await idn.status()

    @router.post("/models/download")
    async def download():
        import asyncio
        if not idn._download["running"]:
            asyncio.create_task(idn.download_models())
        return {"started": True}

    @router.put("/settings")
    async def settings(body: SettingsBody):
        return await idn.update_settings(body.model_dump())

    @router.post("/profiles")
    async def create(body: NameBody):
        try:
            await idn.create_profile(body.name)
        except idn.IdentityError as exc:
            raise wrap(exc) from exc
        return {"ok": True}

    @router.delete("/profiles/{name}")
    async def delete(name: str, kind: str | None = None):
        try:
            await idn.delete_profile(name, kind)
        except idn.IdentityError as exc:
            raise wrap(exc) from exc
        return {"ok": True}

    @router.post("/enroll/{kind}")
    async def enroll(kind: str, name: str, request: Request):
        if kind not in ("voice", "face", "style"):
            raise HTTPException(status_code=404)
        try:
            if kind == "style":
                return await idn.enroll_style(name, (await body_of(request)).decode("utf-8", "replace"))
            return await idn.enroll(name, kind, await body_of(request))
        except idn.IdentityError as exc:
            raise wrap(exc) from exc

    @router.post("/identify/voice")
    async def identify_voice(request: Request):
        try:
            return await idn.identify_voice(await body_of(request))
        except idn.IdentityError as exc:
            raise wrap(exc) from exc

    @router.post("/identify/face")
    async def identify_face(request: Request):
        try:
            return await idn.identify_face(await body_of(request))
        except idn.IdentityError as exc:
            raise wrap(exc) from exc

    @router.post("/liveness/start")
    async def liveness_start():
        return await idn.liveness_start()

    @router.post("/liveness/frame")
    async def liveness_frame(challenge: str, request: Request):
        try:
            return await idn.liveness_frame(challenge, await body_of(request))
        except idn.IdentityError as exc:
            raise wrap(exc) from exc

    return router
