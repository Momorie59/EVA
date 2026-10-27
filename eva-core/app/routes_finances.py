"""Finances personnelles : toujours SES données (aucune route ne lit celles d'un autre, administrateur compris)."""
from fastapi import APIRouter, HTTPException, Query, Request

from . import auth as auth_mod, features, finances


async def _qui(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if "finances" not in await features.effective(me["role"], me["user"]):
        raise HTTPException(403, "Les finances ne sont pas activées pour ton compte.")
    return me["user"] or ""


def _err(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/finances")

    @r.get("/tableau")
    async def tableau(request: Request, mois: str = ""):
        try:
            return {**await finances.tableau(await _qui(request), mois or None), "categories": finances.CATEGORIES}
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    @r.get("/operations")
    async def operations(request: Request, mois: str = "", categorie: str = "", q: str = ""):
        try:
            return {"operations": await finances.operations(await _qui(request), mois or None, categorie, q)}
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    @r.patch("/operations/{oid}")
    async def recategoriser(oid: int, request: Request, body: dict):
        try:
            return await finances.recategoriser(await _qui(request), oid, str(body.get("categorie", "")), bool(body.get("retenir", True)))
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    @r.get("/comptes")
    async def comptes(request: Request):
        return {"comptes": await finances.comptes(await _qui(request))}

    @r.post("/comptes")
    async def creer(request: Request, body: dict):
        try:
            return await finances.creer_compte(await _qui(request), body.get("nom", ""), body.get("solde_initial", 0))
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    @r.patch("/comptes/{cid}")
    async def modifier(cid: int, request: Request, body: dict):
        try:
            await finances.modifier_compte(await _qui(request), cid, body.get("nom"), body.get("solde_initial"))
        except finances.FinancesError as exc:
            raise _err(exc) from exc
        return {"ok": True}

    @r.delete("/comptes/{cid}")
    async def supprimer(cid: int, request: Request):
        await finances.supprimer_compte(await _qui(request), cid)
        return {"ok": True}

    @r.post("/comptes/{cid}/import")
    async def importer(cid: int, request: Request, nom: str = Query("releve.csv")):
        donnees = await request.body()
        if not donnees or len(donnees) > 10 * 1024 * 1024:
            raise HTTPException(400, "Relevé vide ou trop gros (10 Mo au plus).")
        try:
            return await finances.importer(await _qui(request), cid, nom, donnees)
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    @r.get("/budgets")
    async def budgets(request: Request):
        return {"budgets": await finances.budgets(await _qui(request)), "categories": finances.CATEGORIES}

    @r.put("/budgets")
    async def regler(request: Request, body: dict):
        try:
            return {"budgets": await finances.regler_budget(await _qui(request), str(body.get("categorie", "")), body.get("montant"))}
        except finances.FinancesError as exc:
            raise _err(exc) from exc

    return r
