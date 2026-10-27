"""EVA serveur MCP : point d'entrée pour les clients (jeton MCP) et gestion des jetons (administrateur)."""
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import auth as auth_mod, mcp_serveur as srv


async def _admin(request: Request) -> None:
    if not auth_mod.protected():
        return
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if me["role"] != "admin":
        raise HTTPException(403, "Réservé à un administrateur.")


def make_router() -> APIRouter:
    r = APIRouter()

    @r.post("/api/serveur-mcp")
    async def entree(request: Request):
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
        try:
            corps = json.loads(await request.body() or b"null")
        except ValueError:
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON illisible."}}, status_code=400)
        statut, rep = await srv.traiter(auth_mod.bearer(request.headers.get("authorization")), corps, ip)
        if statut == 401:
            return JSONResponse(rep, status_code=401, headers={"WWW-Authenticate": 'Bearer realm="eva-mcp"'})
        if rep is None:
            return Response(status_code=statut)
        return JSONResponse(rep, status_code=statut)

    @r.get("/api/serveur-mcp")
    async def pas_de_flux():
        return Response(status_code=405, headers={"Allow": "POST"})       # pas de flux SSE côté serveur

    @r.delete("/api/serveur-mcp")
    async def fin_session():
        return Response(status_code=405, headers={"Allow": "POST"})

    @r.get("/api/mcp/serveur")
    async def etat(request: Request):
        await _admin(request)
        return {"jetons": await srv.lister(), "outils": srv.outils_exposables(), "comptes": [u["user"] for u in auth_mod.list_users()]}

    @r.post("/api/mcp/serveur/jetons")
    async def creer(request: Request, body: dict):
        await _admin(request)
        try:
            return await srv.creer(body.get("nom", ""), body.get("compte", ""), body.get("outils") or [])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.put("/api/mcp/serveur/jetons/{jid}")
    async def modifier(jid: str, request: Request, body: dict):
        await _admin(request)
        try:
            return await srv.modifier(jid, body.get("outils") or [])
        except KeyError as exc:
            raise HTTPException(404, "Jeton inconnu.") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.delete("/api/mcp/serveur/jetons/{jid}")
    async def revoquer(jid: str, request: Request):
        await _admin(request)
        await srv.revoquer(jid)
        return {"ok": True}

    return r
