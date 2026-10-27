"""IA du marché (OpenAI, Claude, Gemini…) : fournisseurs, clés (jamais renvoyées), test, repli. Réservé à l'administrateur pour les modifications."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import cloud_ai, ia_gratuites
from . import router as mrouter


class ProviderBody(BaseModel):
    preset: str = "custom"
    label: str = ""
    base_url: str = ""
    api_key: str = ""
    models: list[str] | str = []
    enabled: bool = True
    fallback: bool = False
    vision: bool = False
    sans_cle: bool = False
    gratuit: bool = False
    entrainement: str | None = None
    prix_entree: float | str | None = None       # € par million de jetons envoyés
    prix_sortie: float | str | None = None       # € par million de jetons reçus
    budget_mois: float | str | None = None       # plafond mensuel en € (0 = aucun)


class RotationBody(BaseModel):
    ordre: list[str] | None = None
    exclus: list[str] | None = None
    exclure_entrainement: bool | None = None
    repli: bool | None = None


class PrefBody(BaseModel):
    prefer_over_airllm: bool


def make_cloud_router() -> APIRouter:
    router = APIRouter(prefix="/api/cloud")

    @router.get("")
    async def get_all():
        return {**cloud_ai.public(await cloud_ai.load()), "depenses": await cloud_ai.depenses()}

    @router.put("/providers/{pid}")
    async def put_provider(pid: str, body: ProviderBody):
        try:
            out = await cloud_ai.upsert(pid, body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await mrouter.installed_models(force=True)
        return out

    @router.delete("/providers/{pid}")
    async def del_provider(pid: str):
        out = await cloud_ai.remove(pid)
        await mrouter.installed_models(force=True)
        return out

    @router.put("/prefs")
    async def prefs(body: PrefBody):
        return await cloud_ai.upsert_prefs(body.prefer_over_airllm)

    @router.get("/rotation")
    async def rotation():
        """IA gratuites (automatique) : ordre d'essai, services en pause et pourquoi."""
        cfg = await cloud_ai.load()
        return {**cfg["rotation"], "services": cloud_ai.etat_rotation(cfg)}

    @router.put("/rotation")
    async def regler_rotation(body: RotationBody):
        out = await cloud_ai.regler_rotation(body.ordre, body.exclure_entrainement, body.repli, body.exclus)
        await mrouter.installed_models(force=True)
        return out

    @router.get("/gratuites")
    async def gratuites():
        """IA gratuites (liste awesome-free-llm-apis) : services, modèles, conditions, à ajouter en un clic."""
        return await ia_gratuites.catalogue()

    @router.post("/gratuites/maj")
    async def gratuites_maj():
        try:
            return await ia_gratuites.mettre_a_jour()
        except ia_gratuites.GratuitesError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/providers/{pid}/test")
    async def test(pid: str):
        try:
            return await cloud_ai.test(pid)
        except cloud_ai.CloudError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
