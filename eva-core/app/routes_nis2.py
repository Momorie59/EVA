from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, nis2


class IncidentIn(BaseModel):
    title: str
    severity: str = "moyen"
    description: str = ""
    detected: str = ""


class IncidentPatch(BaseModel):
    status: str | None = None
    actions: str | None = None
    mark: list[str] = []
    unmark: list[str] = []


def _https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/nis2")

    async def admin(authorization: str | None) -> dict:
        me = await auth.identify(auth.bearer(authorization))
        if me is None or me["role"] != "admin":
            raise HTTPException(403, "Réservé à un administrateur.")
        return me

    @router.get("")
    async def get_audit(request: Request, authorization: str | None = Header(default=None)):
        await admin(authorization)
        return await nis2.audit(_https(request))

    @router.get("/report")
    async def report(request: Request, authorization: str | None = Header(default=None)):
        await admin(authorization)
        md = await nis2.report_markdown(_https(request))
        return Response(md, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="eva-nis2-rapport.md"'})

    @router.get("/incidents")
    async def list_incidents(authorization: str | None = Header(default=None)):
        await admin(authorization)
        return {"incidents": await nis2.incidents(), "severities": list(nis2.SEVERITIES)}

    @router.post("/incidents")
    async def add_incident(b: IncidentIn, request: Request, authorization: str | None = Header(default=None)):
        me = await admin(authorization)
        try:
            inc = await nis2.incident_add(b.title, b.severity, b.description, b.detected, me["user"] or "")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        await auth.audit("admin", me["user"] or "", request.client.host if request.client else "", "Incident enregistré", f"{inc['title']} ({inc['severity']})", 200)
        return inc

    @router.patch("/incidents/{iid}")
    async def patch_incident(iid: str, b: IncidentPatch, authorization: str | None = Header(default=None)):
        await admin(authorization)
        try:
            return await nis2.incident_update(iid, b.model_dump(exclude_none=True))
        except KeyError as exc:
            raise HTTPException(404, "Incident introuvable.") from exc

    @router.delete("/incidents/{iid}")
    async def delete_incident(iid: str, authorization: str | None = Header(default=None)):
        await admin(authorization)
        await nis2.incident_delete(iid)
        return {"ok": True}

    return router
