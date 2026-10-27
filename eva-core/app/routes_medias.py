"""Envoi (connecté, module actif) et lecture (adresse = clé) des photos et vidéos du wiki et des recettes."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import auth as auth_mod, features, medias, modules

MIME = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/mp4", ".pdf": "application/pdf",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def make_routers(workspace: Path) -> tuple[APIRouter, APIRouter]:
    medias.initialiser(workspace)
    prive = APIRouter(prefix="/api/medias")
    public = APIRouter(prefix="/api/public/medias")

    @prive.post("")
    async def envoyer(request: Request, module: str = Query(...), nom: str = Query(..., min_length=1, max_length=200)):
        """Corps brut = le fichier (écrit au fil de l'eau). Réservé à une personne qui a le module et la fonctionnalité."""
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
        if me is None:
            raise HTTPException(401, "Connexion requise.")
        if module not in medias.DOSSIERS or not modules.actif(module):
            raise HTTPException(404, "Ce module n'est pas activé (Paramètres › Modules).")
        if me["role"] == "guest" or module not in await features.effective(me["role"], me["user"]):
            raise HTTPException(403, "Tu ne peux pas ajouter de fichier ici.")
        try:
            fichier, cible, limite = medias.nouveau(module, nom)
        except medias.MediaError as e:
            raise HTTPException(e.status, str(e)) from e
        taille = 0
        try:
            with open(cible, "wb") as out:
                async for morceau in request.stream():
                    taille += len(morceau)
                    if taille > limite:
                        raise HTTPException(413, f"Fichier trop gros ({limite // (1024 * 1024)} Mo maximum).")
                    out.write(morceau)
        except HTTPException:
            cible.unlink(missing_ok=True)
            raise
        if taille == 0:
            cible.unlink(missing_ok=True)
            raise HTTPException(400, "Fichier vide.")
        return {"fichier": fichier, "genre": medias.genre(fichier), "url": f"/api/public/medias/{fichier}", "taille": taille}

    @public.get("/{fichier}")
    async def lire(fichier: str):
        try:
            module, p = medias.chemin(fichier)
        except medias.MediaError as e:
            raise HTTPException(e.status, str(e)) from e
        if module in modules.MODULES and not modules.actif(module):
            raise HTTPException(404, "Fichier introuvable.")
        return FileResponse(p, media_type=MIME.get(p.suffix.lower(), "application/octet-stream"),
                            headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})

    return prive, public
