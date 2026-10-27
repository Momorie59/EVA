import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import acces, auth as auth_mod, knowledge, uploads


async def _moi(request: Request) -> dict:
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return me


def make_router(workspace: Path) -> APIRouter:
    router = APIRouter(prefix="/api/uploads")

    @router.post("")
    async def upload(request: Request, name: str = Query(..., min_length=1, max_length=200)):
        """Corps brut (le fichier lui-même) : évite la dépendance à python-multipart. Écrit au fil de l'eau (pas tout en mémoire)."""
        limit = uploads.MAX_MB * 1024 * 1024
        declared = int(request.headers.get("content-length") or 0)
        if declared > limit:
            raise HTTPException(status_code=413, detail=f"Fichier trop gros ({uploads.MAX_MB} Mo maximum).")
        me = await _moi(request)
        folder = workspace / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        target = uploads.unique_path(folder, uploads.safe_name(name))
        size = 0
        try:
            with open(target, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(status_code=413, detail=f"Fichier trop gros ({uploads.MAX_MB} Mo maximum).")
                    out.write(chunk)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        if size == 0:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Fichier vide.")
        acces.enregistrer(workspace, target.relative_to(workspace).as_posix(), me["user"])   # le fichier est à celle ou celui qui l'envoie
        try:
            info = await asyncio.to_thread(uploads.describe, target, workspace)
        except Exception as e:                       # fichier abîmé (PDF tronqué…) : on le garde, sans aperçu
            rel = target.relative_to(workspace).as_posix()
            info = {"name": target.name, "path": rel, "size": size, "kind": "autre", "text_path": None, "preview": "",
                    "entries": [], "note": f"Fichier reçu, mais illisible pour EVA ({type(e).__name__}) : il est peut-être abîmé."}
        try:
            knowledge.learn_upload(target, workspace, info.get("kind", ""))
        except Exception:
            pass
        return info

    files_router = APIRouter(prefix="/api/files")

    @files_router.get("/download")
    async def download(request: Request, path: str = Query(..., min_length=1, max_length=400)):
        """Télécharge un fichier du workspace (ZIP livré par EVA, fichier déposé ou image créée).
        Une personne non administratrice ne télécharge que ses fichiers et ceux de ses projets (voir acces.py)."""
        p = (workspace / path).resolve()
        if workspace.resolve() not in p.parents or not p.is_file():
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
        me = await _moi(request)
        reel = p.relative_to(workspace.resolve()).as_posix()        # le vrai fichier, liens symboliques suivis
        if not await acces.autorise(workspace, path, me["user"], me["role"]) or not await acces.autorise(workspace, reel, me["user"], me["role"]):
            await auth_mod.audit("denied", me["user"], "", f"GET /api/files/download {path}", "fichier d'une autre personne", 403)
            raise HTTPException(status_code=403, detail="Ce fichier ne t'appartient pas.")
        return FileResponse(p, filename=p.name)

    router.files_router = files_router
    return router
