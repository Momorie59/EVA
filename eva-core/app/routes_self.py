from fastapi import APIRouter, HTTPException, Request

from . import self_mod as sm


def _wrap(exc: sm.SelfModError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/self")

    @router.get("/status")
    async def status():
        return sm.status()

    @router.get("/proposals")
    async def proposals():
        return {"proposals": await sm.list_proposals()}

    @router.get("/proposals/{pid}")
    async def one(pid: int):
        p = await sm.get_proposal(pid)
        if not p:
            raise HTTPException(status_code=404, detail="Proposition introuvable.")
        return p

    @router.post("/proposals/{pid}/apply")
    async def apply(pid: int):
        try:
            return await sm.apply(pid)
        except sm.SelfModError as exc:
            raise _wrap(exc) from exc

    @router.post("/proposals/{pid}/reject")
    async def reject(pid: int):
        try:
            await sm.reject(pid)
        except sm.SelfModError as exc:
            raise _wrap(exc) from exc
        return {"ok": True}

    @router.post("/proposals/{pid}/revert")
    async def revert(pid: int):
        try:
            return await sm.revert(pid)
        except sm.SelfModError as exc:
            raise _wrap(exc) from exc

    @router.get("/demandes")
    async def demandes():
        """Demandes d'évolution notées par EVA (ce qu'on lui a demandé et qu'elle ne sait pas encore faire)."""
        from . import evolution_demandes
        return {"demandes": await evolution_demandes.lister()}

    @router.patch("/demandes/{did}")
    async def demande_statut(did: str, body: dict):
        from . import evolution_demandes
        try:
            return {"demandes": await evolution_demandes.changer(did, str((body or {}).get("statut", "")))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/lecons")
    async def lecons_etat(request: Request):
        """Apprentissage par les erreurs : leçons, ratés notés (phrases de la famille : administrateur seulement)."""
        from . import auth as auth_mod, lecons
        if auth_mod.protected():
            me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
            if not me or me["role"] != "admin":
                raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
        return await lecons.etat()

    @router.put("/lecons/reglages")
    async def lecons_reglages(body: dict):
        from . import lecons
        b = body or {}
        return await lecons.regler(actif=b.get("actif"), modele=b.get("modele"), code=b.get("code"), heure=b.get("heure"), auto=b.get("auto"))

    @router.patch("/lecons/{lid}")
    async def lecons_changer(lid: int, body: dict):
        from . import lecons
        await lecons.changer(lid, actif=(body or {}).get("actif"), supprimer=bool((body or {}).get("supprimer")))
        return await lecons.etat()

    @router.post("/lecons/apprendre")
    async def lecons_apprendre():
        """Lance tout de suite une passe d'apprentissage (en fond)."""
        import asyncio
        from . import lecons
        from .main import registry
        if getattr(lecons, "_en_cours", False):
            raise HTTPException(status_code=409, detail="Une passe d'apprentissage est déjà en cours.")

        async def passe():
            lecons._en_cours = True
            try:
                await lecons.apprendre(registry)
            finally:
                lecons._en_cours = False
        asyncio.create_task(passe())
        return {"ok": True}

    @router.get("/banc")
    async def banc_resultats():
        """Banc d'essai des outils : résultats par modèle et passage en cours."""
        from . import banc_essai
        return await banc_essai.resultats()

    @router.post("/banc")
    async def banc_lancer(body: dict):
        """Lance le banc d'essai en fond avec le modèle choisi (rien n'est exécuté : on regarde seulement l'outil choisi)."""
        import asyncio
        from . import banc_essai, router as model_router
        from .main import registry
        modele = str((body or {}).get("modele") or "").strip()
        if not modele:
            modele = (await model_router.select("Allume la lumière du salon"))["model"]
        if banc_essai._etat.get("en_cours"):
            raise HTTPException(status_code=409, detail="Un banc d'essai tourne déjà.")
        tache = asyncio.create_task(banc_essai.lancer(modele, registry, str((body or {}).get("filtre") or "")))
        tache.add_done_callback(lambda t: t.exception())
        await asyncio.sleep(0)
        return {"ok": True, "modele": modele, "etat": dict(banc_essai._etat)}

    return router
