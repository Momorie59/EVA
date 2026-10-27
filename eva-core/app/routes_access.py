from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from . import auth, features, quotas


class QuotasIn(BaseModel):
    profils: dict | None = None
    personnes: dict | None = None


class GroupIn(BaseModel):
    label: str
    features: list[str] = []


class UserAccess(BaseModel):
    groups: list[str] = []
    extra: list[str] = []
    blocked: list[str] = []


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/access")

    async def admin(authorization: str | None) -> None:
        me = await auth.identify(auth.bearer(authorization))
        if me is None or me["role"] != "admin":
            raise HTTPException(403, "Réservé à un administrateur.")

    @router.get("/quotas")
    async def lire_quotas(authorization: str | None = Header(default=None)):
        await admin(authorization)
        d = await quotas.charger()
        d["usage"] = {u["user"]: await quotas.usage(u["user"]) for u in auth.list_users() if u.get("role") != "admin"}
        return d

    @router.put("/quotas")
    async def ecrire_quotas(b: QuotasIn, authorization: str | None = Header(default=None)):
        await admin(authorization)
        try:
            return await quotas.enregistrer(b.profils, b.personnes)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("")
    async def overview(authorization: str | None = Header(default=None)):
        await admin(authorization)
        return await features.overview(auth.list_users())

    @router.post("/groups")
    async def create_group(b: GroupIn, authorization: str | None = Header(default=None)):
        await admin(authorization)
        try:
            return await features.group_save(b.label, b.features)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.put("/groups/{gid}")
    async def update_group(gid: str, b: GroupIn, authorization: str | None = Header(default=None)):
        await admin(authorization)
        try:
            return await features.group_save(b.label, b.features, gid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/groups/{gid}")
    async def delete_group(gid: str, authorization: str | None = Header(default=None)):
        await admin(authorization)
        await features.group_delete(gid)
        return {"ok": True}

    @router.put("/users/{name}")
    async def user_access(name: str, b: UserAccess, authorization: str | None = Header(default=None)):
        await admin(authorization)
        if name.lower() not in {u["user"].lower() for u in auth.list_users()}:
            raise HTTPException(404, "Utilisateur introuvable.")
        return await features.user_save(name, b.groups, b.extra, b.blocked)

    return router
