from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import auth as auth_mod, features as features_mod, mind, profiles as profiles_mod


class FactIn(BaseModel):
    text: str
    kind: str = "autre"


class Enabled(BaseModel):
    enabled: bool


class RuleEdit(BaseModel):
    status: str | None = None
    text: str | None = None


class Learn(BaseModel):
    topic: str


async def _me(request: Request) -> None:
    """Chaque personne ne voit et ne change que SA mémoire ; les invités n'en ont pas."""
    name, role = "", "admin"
    request.state.role = role
    if auth_mod.protected():
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
        if me is None:
            raise HTTPException(401, "Connexion requise.")
        name, role = me["user"], me["role"]
        request.state.role = role
        if role == "guest":
            raise HTTPException(403, "Pas de mémoire pour les invités.")
    profiles_mod.user_var.set(name)


def make_router(registry) -> APIRouter:
    router = APIRouter(prefix="/api/mind", dependencies=[Depends(_me)])

    def bad(exc):
        raise HTTPException(400, str(exc)) from exc

    @router.get("")
    async def get():
        d = await mind.load()
        return {"enabled": d["enabled"], "rules": d["rules"], "lessons": [{k: v for k, v in l.items()} for l in d["lessons"]],
                "limits": {"facts": mind.MAX_FACTS, "rules": mind.MAX_RULES, "lessons": mind.MAX_LESSONS}}

    @router.put("/enabled")
    async def enabled(b: Enabled):
        return {"enabled": await mind.set_enabled(b.enabled)}

    @router.post("/review")
    async def review():
        try:
            return {"added": await mind.review()}
        except ValueError as exc:
            bad(exc)
        except Exception as exc:  # noqa: BLE001 — modèle indisponible, etc.
            raise HTTPException(502, f"Relecture impossible : {exc}") from exc

    @router.put("/rules/{rid}")
    async def rule(rid: str, b: RuleEdit):
        if not await mind.set_rule(rid, b.status, b.text):
            raise HTTPException(404, "Règle introuvable.")
        return {"ok": True}

    @router.delete("/rules/{rid}")
    async def rule_rm(rid: str):
        if not await mind.set_rule(rid, delete=True):
            raise HTTPException(404, "Règle introuvable.")
        return {"ok": True}

    @router.post("/learn")
    async def learn(b: Learn, request: Request):
        role = getattr(request.state, "role", "admin")
        reg = registry if role == "admin" else features_mod.FeatureRegistry(registry, await features_mod.effective(role, profiles_mod.user_var.get()))
        try:
            return await mind.learn(b.topic, reg)
        except ValueError as exc:
            bad(exc)

    @router.delete("/lessons/{lid}")
    async def lesson_rm(lid: str):
        if not await mind.delete_lesson(lid):
            raise HTTPException(404, "Sujet introuvable.")
        return {"ok": True}

    return router
