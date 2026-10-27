"""Suivi de contenus : ses contenus et ceux partagés ; annonce Discord d'une publication."""
from fastapi import APIRouter, HTTPException, Request

from . import auth as auth_mod, connecteurs as cx, contenus, features


async def _qui(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if "contenus" not in await features.effective(me["role"], me["user"]):
        raise HTTPException(403, "Le suivi de contenus n'est pas activé pour ton compte.")
    return me["user"] or ""


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/contenus")

    @r.get("")
    async def lister(request: Request, etat: str = "", debut: str = "", fin: str = ""):
        qui = await _qui(request)
        try:
            lst = await contenus.lister(qui, etat, debut, fin)
        except contenus.ContenuError as exc:
            raise HTTPException(400, str(exc)) from exc
        salons = list(((await cx.config("discord")).get("salons") or {}))
        return {"contenus": lst, "etats": contenus.ETATS, "noms": contenus.NOMS_ETATS, "plateformes": contenus.PLATEFORMES,
                "discord": salons, "instagram": bool(await cx.config("instagram")), "moi": qui}

    @r.post("")
    async def creer(request: Request, body: dict):
        try:
            return await contenus.creer(await _qui(request), body or {})
        except contenus.ContenuError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.patch("/{cid}")
    async def modifier(cid: int, request: Request, body: dict):
        try:
            return await contenus.modifier(await _qui(request), cid, body or {})
        except contenus.ContenuError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.delete("/{cid}")
    async def supprimer(cid: int, request: Request):
        try:
            await contenus.supprimer(await _qui(request), cid)
        except contenus.ContenuError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {"ok": True}

    @r.post("/{cid}/annoncer")
    async def annoncer(cid: int, request: Request, body: dict | None = None):
        qui = await _qui(request)
        try:
            c = await contenus.lire(qui, cid)
            return await cx.discord_envoyer(str((body or {}).get("salon", "")), str((body or {}).get("message") or contenus.message_annonce(c)))
        except (contenus.ContenuError, cx.ConnecteurError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.get("/instagram")
    async def instagram(request: Request):
        await _qui(request)
        try:
            return await cx.instagram_stats(6)
        except cx.ConnecteurError as exc:
            raise HTTPException(400, str(exc)) from exc

    return r
