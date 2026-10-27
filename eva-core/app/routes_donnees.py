"""Mes données : ce qu'EVA garde sur moi, l'export complet (ZIP) et l'effacement.
Chacun gère ses propres données ; l'administrateur peut le faire pour n'importe qui (et supprimer le compte)."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from . import auth, donnees

CONFIRMATION = "EFFACER"


class EffacerIn(BaseModel):
    confirmation: str
    compte: bool = False


def make_router(workspace: Path) -> APIRouter:
    r = APIRouter(prefix="/api/donnees")

    async def cible(request: Request, personne: str) -> tuple[dict, str]:
        me = await auth.identify(auth.bearer(request.headers.get("authorization")))
        if me is None:
            raise HTTPException(401, "Connexion requise.")
        if personne and personne.lower() != (me["user"] or "").lower():
            if me["role"] != "admin":
                raise HTTPException(403, "Tu ne peux gérer que tes propres données.")
            if not any(u["user"].lower() == personne.lower() for u in auth.list_users()):
                raise HTTPException(404, "Personne inconnue.")
            return me, personne.lower()
        return me, (me["user"] or "").lower()

    @r.get("")
    async def inventaire(request: Request, personne: str = Query("", max_length=64)):
        _, qui = await cible(request, personne)
        return await donnees.inventaire(workspace, qui)

    @r.post("/export")
    async def exporter(request: Request, personne: str = Query("", max_length=64)):
        _, qui = await cible(request, personne)
        try:
            return {"path": await donnees.exporter(workspace, qui)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @r.post("/effacer")
    async def effacer(b: EffacerIn, request: Request, personne: str = Query("", max_length=64)):
        me, qui = await cible(request, personne)
        if b.confirmation.strip().upper() != CONFIRMATION:
            raise HTTPException(400, f"Écris « {CONFIRMATION} » pour confirmer : l'effacement est définitif.")
        if not qui:
            raise HTTPException(400, "EVA n'est pas protégée par un mot de passe : il n'y a pas de compte à qui rattacher ces données.")
        if b.compte and me["role"] != "admin":
            raise HTTPException(403, "Seul l'administrateur supprime un compte.")
        try:
            return {"efface": await donnees.effacer(workspace, qui, compte=b.compte, acteur=me["user"])}
        except auth.AuthError as e:
            raise HTTPException(getattr(e, "status", 409), str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    return r
