"""Spotify : réglage et liaison (administrateur) ; retour de la page de connexion Spotify (public, protégé par le « state »)."""
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import auth as auth_mod, spotify


async def _admin(request: Request) -> None:
    if not auth_mod.protected():
        return
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if me["role"] != "admin":
        raise HTTPException(403, "Réservé à un administrateur.")


def adresse_retour(request: Request) -> str:
    hote = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{hote}/api/spotify/retour"


def make_router() -> APIRouter:
    r = APIRouter()

    @r.get("/api/spotify")
    async def etat(request: Request):
        await _admin(request)
        return {**await spotify.etat(), "retour": adresse_retour(request)}

    @r.put("/api/spotify")
    async def regler(request: Request, body: dict):
        await _admin(request)
        try:
            return await spotify.regler(body.get("client_id"), body.get("playlist_auto"))
        except spotify.SpotifyError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.post("/api/spotify/connecter")
    async def connecter(request: Request, body: dict | None = None):
        await _admin(request)
        e = await spotify.etat()
        if not e["client_id"]:
            raise HTTPException(400, "Enregistre d'abord le Client ID de ton appli Spotify.")
        retour = str((body or {}).get("retour") or adresse_retour(request))
        return {"lien": spotify.lien_connexion(e["client_id"], retour)}

    @r.delete("/api/spotify")
    async def oublier(request: Request):
        await _admin(request)
        await spotify.oublier()
        return {"ok": True}

    @r.get("/api/spotify/retour", response_class=HTMLResponse)
    async def retour(code: str = "", state: str = "", error: str = ""):
        if error or not code:
            texte, ok = f"Liaison annulée ({escape(error or 'pas de code')}).", False
        else:
            try:
                e = await spotify.finir_connexion(code, state)
                texte, ok = f"Spotify est relié au compte « {escape(e['compte'])} »." + ("" if e["premium"] else
                            " (Compte gratuit : recherche et playlists oui, pilotage de la lecture non.)"), True
            except spotify.SpotifyError as exc:
                texte, ok = escape(str(exc)), False
        return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVA · Spotify</title><body style="font-family:system-ui;background:#141a33;color:#fff;display:grid;place-items:center;min-height:90vh;text-align:center">
<div><h1>{'✅' if ok else '⚠️'} Spotify</h1><p>{texte}</p><p>Tu peux fermer cette page et revenir dans EVA.</p></div>
<script>try{{window.opener&&window.opener.postMessage("eva-spotify","*")}}catch(e){{}}</script>""")

    return r
