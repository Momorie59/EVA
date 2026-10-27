"""Choix du modèle d'AirLLM depuis l'interface (administrateurs) : relais vers le service eva-airllm (/config)."""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import settings


class ChoixBody(BaseModel):
    model: str


class ReplieBody(BaseModel):
    repli_auto: bool


async def _relais(methode: str, chemin: str, **kw) -> dict:
    if not settings.airllm_url:
        raise HTTPException(status_code=404, detail="AirLLM n'est pas installé (EVA_AIRLLM_URL vide).")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            r = await client.request(methode, settings.airllm_url.rstrip("/") + chemin, **kw)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Service AirLLM injoignable (conteneur eva-airllm arrêté ?) : {exc}") from exc
    if r.status_code == 404:
        raise HTTPException(status_code=502, detail="Le service AirLLM est trop ancien pour choisir le modèle : reconstruis eva-airllm (mise à jour 17).")
    try:
        data = r.json()
    except ValueError:
        data = {"detail": r.text[:200]}
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=data.get("detail", "Erreur AirLLM"))
    return data


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/airllm")

    @router.get("")
    async def etat():
        from .router import repli_airllm
        conf = await _relais("GET", "/config")
        sante = await _relais("GET", "/health")
        return {**conf, "sante": sante, "repli_auto": await repli_airllm()}

    @router.put("/repli")
    async def repli(body: ReplieBody):
        """Repli automatique quand le serveur IA ne répond pas (non par défaut : AirLLM seulement si on le choisit)."""
        from .router import regler_repli_airllm
        return {"repli_auto": await regler_repli_airllm(body.repli_auto)}

    @router.put("")
    async def choisir(body: ChoixBody):
        return await _relais("PUT", "/config", json={"model": body.model})

    @router.delete("/modeles/{auteur}/{nom}")
    async def supprimer(auteur: str, nom: str):
        return await _relais("DELETE", f"/modeles/{auteur}/{nom}")

    return router
