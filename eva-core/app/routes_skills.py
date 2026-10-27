from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import skills as sk


class SkillRaw(BaseModel):
    raw: str


class SkillInstall(BaseModel):
    source: str


class SkillLot(BaseModel):
    names: list[str]
    action: str          # activer | desactiver | supprimer


class SkillBatch(BaseModel):
    source: str
    paths: list[str]


def make_router(workspace_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/skills")

    @router.get("")
    async def list_all():
        return {"skills": sk.list_skills(workspace_root)}

    @router.post("/install")
    async def install(body: SkillInstall):
        try:
            return await sk.install_from_github(body.source, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — réseau coupé, GitHub injoignable…
            raise HTTPException(status_code=502, detail=f"GitHub injoignable : {exc}") from exc

    @router.post("/catalog")
    async def catalog(body: SkillInstall):
        try:
            return await sk.catalog(body.source, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"GitHub injoignable : {exc}") from exc

    @router.post("/install-many")
    async def install_many(body: SkillBatch):
        if not body.paths:
            raise HTTPException(status_code=400, detail="Coche au moins un skill.")
        try:
            return await sk.install_many(body.source, body.paths, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/lot")
    async def lot(body: SkillLot):
        if body.action == "supprimer":
            return {"n": sk.delete_many(body.names, workspace_root)}
        if body.action in ("activer", "desactiver"):
            return {"n": sk.set_actifs(body.names, body.action == "activer", workspace_root)}
        raise HTTPException(status_code=400, detail="Action inconnue.")

    @router.get("/{name}")
    async def get(name: str):
        try:
            skill = sk.get_skill(name, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not skill:
            raise HTTPException(status_code=404, detail="Skill introuvable.")
        return skill

    @router.put("/{name}")
    async def put(name: str, body: SkillRaw):
        try:
            return sk.save_skill_raw(name, body.raw, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{name}")
    async def delete(name: str):
        try:
            ok = sk.delete_skill(name, workspace_root)
        except sk.SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="Skill introuvable.")
        return {"ok": True}

    return router
