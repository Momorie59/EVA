"""Raccourcis du téléphone : gestion des jetons (chacun les siens) et point d'entrée du raccourci."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import auth as auth_mod, raccourcis


async def _moi(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or ""


def make_router() -> APIRouter:
    r = APIRouter()

    @r.get("/api/raccourcis")
    async def lister(request: Request):
        return {"jetons": await raccourcis.lister(await _moi(request))}

    @r.post("/api/raccourcis")
    async def creer(request: Request, body: dict):
        try:
            return await raccourcis.creer(await _moi(request), (body or {}).get("nom", ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.delete("/api/raccourcis/{rid}")
    async def retirer(rid: str, request: Request):
        if not await raccourcis.retirer(await _moi(request), rid):
            raise HTTPException(404, "Jeton introuvable.")
        return {"ok": True}

    @r.post("/api/raccourci")
    async def raccourci(request: Request):
        """Corps : {"texte": "…"} ou le texte brut. Réponse : texte brut (ou JSON si ?format=json)."""
        p = await raccourcis.qui(auth_mod.bearer(request.headers.get("authorization")))
        if p is None:
            raise HTTPException(401, "Jeton de raccourci invalide ou retiré.")
        brut = (await request.body()).decode(errors="ignore")
        texte = brut
        if brut.lstrip().startswith("{"):
            try:
                import json
                texte = str(json.loads(brut).get("texte") or json.loads(brut).get("text") or "")
            except ValueError:
                pass
        rep = await raccourcis.demander(p, texte)
        if request.query_params.get("format") == "json":
            return JSONResponse({"reponse": rep})
        return PlainTextResponse(rep)

    return r
