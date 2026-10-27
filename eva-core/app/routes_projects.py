import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import auth as auth_mod, projects as P, project_acl as ACL
from . import sandbox_proj as S
from . import share as SH
from . import history as H
import mimetypes
import secrets
import time


class CreateBody(BaseModel):
    name: str
    description: str = ""


class WriteBody(BaseModel):
    path: str
    content: str
    base_mtime_ns: str | int | None = None


class PathBody(BaseModel):
    path: str


class MoveBody(BaseModel):
    src: str
    dst: str


class RunBody(BaseModel):
    command: str
    timeout: int = 60
    internet: bool = False


class ShareBody(BaseModel):
    enabled: bool
    password: str | None = None
    port: int | None = None


class InstallBody(BaseModel):
    packages: list[str]


_PREVIEW: dict[str, tuple[str, float]] = {}


class SharesBody(BaseModel):
    shared: list[str] = []


async def _me(request: Request) -> tuple[str, str]:
    """(nom, rôle) de la personne connectée ; ("", "admin") quand l'accès n'est pas protégé."""
    if not auth_mod.protected():
        return "", "admin"
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"], me["role"]


async def _gate(request: Request) -> None:
    """Un projet partagé avec personne reste invisible : « introuvable », jamais « interdit »."""
    slug = request.path_params.get("slug")
    if not slug or slug in ("share", "trash", "people"):
        return
    user, role = await _me(request)
    if not ACL.can_open((await ACL.load()).get(slug), user, role):
        raise HTTPException(404, f"Projet introuvable : {slug}")


def make_router(ws: Path) -> APIRouter:
    router = APIRouter(prefix="/api/projects", dependencies=[Depends(_gate)])

    async def snap(slug: str, message: str, fresh: bool = False):
        """Enregistre une version après une modification faite depuis l'interface (sans jamais faire échouer la requête)."""
        try:
            if fresh:
                await asyncio.to_thread(H.purge, ws, slug)
            await asyncio.to_thread(H.snapshot, ws, slug, message, H.YOU)
        except Exception:  # noqa: BLE001
            pass

    def hguard(fn, *a):
        try:
            return fn(*a)
        except (H.HistoryError, P.ProjectError) as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    def guard(fn, *a, **k):
        try:
            return fn(*a, **k)
        except P.ProjectError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("")
    async def list_all(request: Request):
        user, role = await _me(request)
        acl = await ACL.load()
        out = []
        for p in await asyncio.to_thread(P.list_projects, ws):
            meta = acl.get(p["slug"])
            if ACL.can_open(meta, user, role):
                out.append({**p, "owner": (meta or {}).get("owner"), "shared": (meta or {}).get("shared", []), "mine": ACL.is_owner(meta, user, role)})
        return {"projects": out}

    @router.get("/people")
    async def people(request: Request):
        user, _role = await _me(request)
        return {"users": [u["user"] for u in auth_mod.list_users() if u["user"].lower() != user.lower() and not u["disabled"]]}

    @router.put("/{slug}/shares")
    async def set_shares(slug: str, body: SharesBody, request: Request):
        user, role = await _me(request)
        if not ACL.is_owner((await ACL.load()).get(slug), user, role):
            raise HTTPException(403, "Seule la personne qui a créé ce projet peut changer son partage.")
        guard(P.project_dir, ws, slug)
        return {"shared": await ACL.set_shared(slug, body.shared)}

    @router.get("/share")
    async def share_status():
        return await SH.status()

    @router.put("/share")
    async def share_apply(body: ShareBody):
        try:
            return await SH.apply(ws, body.enabled, body.password, body.port)
        except SH.ShareError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("")
    async def create(body: CreateBody, request: Request):
        r = guard(P.create, ws, body.name, body.description)
        await ACL.set_owner(r["slug"], (await _me(request))[0])
        await snap(r["slug"], "Création du projet", fresh=True)
        return r

    @router.delete("/{slug}")
    async def delete(slug: str, request: Request):
        """Met le projet à la corbeille (récupérable 30 jours) ; sa base de test est supprimée."""
        user, role = await _me(request)
        if not ACL.is_owner((await ACL.load()).get(slug), user, role):
            raise HTTPException(403, "Seule la personne qui a créé ce projet peut le supprimer.")
        guard(P.project_dir, ws, slug)
        try:
            await S.drop_db(slug)
        except Exception:  # noqa: BLE001 — base de test absente ou inaccessible : on met quand même le dossier à la corbeille
            pass
        return {"ok": True, "trash_id": guard(P.trash, ws, slug)}

    async def _trash_owner(request: Request, tid: str) -> None:
        m = P.TRASH_ID.match(tid)
        user, role = await _me(request)
        if m and not ACL.is_owner((await ACL.load()).get(m.group(1)), user, role):
            raise HTTPException(404, "Élément introuvable dans la corbeille.")

    @router.get("/trash")
    async def trash_list(request: Request):
        user, role = await _me(request)
        acl = await ACL.load()
        return {"items": [i for i in await asyncio.to_thread(P.list_trash, ws) if ACL.is_owner(acl.get(i["slug"]), user, role)]}

    @router.post("/trash/{tid}/restore")
    async def trash_restore(tid: str, request: Request):
        await _trash_owner(request, tid)
        return {"slug": guard(P.restore_trash, ws, tid)}

    @router.delete("/trash/{tid}")
    async def trash_purge(tid: str, request: Request):
        await _trash_owner(request, tid)
        slug = guard(P.purge_trash, ws, tid)
        if not (P.root(ws) / slug).exists():
            await asyncio.to_thread(H.purge, ws, slug)
            await ACL.forget(slug)
        return {"ok": True}

    @router.get("/{slug}/tree")
    async def tree(slug: str, rev: str = ""):
        t = await asyncio.to_thread(guard, P.tree, ws, slug)
        if rev and rev == t["rev"]:
            return {"rev": rev, "changed": False}
        return {**t, "changed": True}

    @router.get("/{slug}/file")
    async def read(slug: str, path: str = Query(..., min_length=1)):
        return guard(P.read_file, ws, slug, path)

    @router.put("/{slug}/file")
    async def write(slug: str, body: WriteBody):
        r = guard(P.write_file, ws, slug, body.path, body.content, body.base_mtime_ns)
        await snap(slug, f"Modifié : {body.path}")
        return r

    @router.delete("/{slug}/file")
    async def rm(slug: str, path: str = Query(..., min_length=1)):
        guard(P.delete_path, ws, slug, path)
        await snap(slug, f"Supprimé : {path}")
        return {"ok": True}

    @router.post("/{slug}/mkdir")
    async def mkdir(slug: str, body: PathBody):
        guard(P.mkdir, ws, slug, body.path)
        return {"ok": True}

    @router.post("/{slug}/move")
    async def move(slug: str, body: MoveBody):
        guard(P.move, ws, slug, body.src, body.dst)
        await snap(slug, f"Déplacé : {body.src} → {body.dst}")
        return {"ok": True}

    @router.post("/{slug}/upload")
    async def upload(slug: str, request: Request, name: str = Query(..., min_length=1, max_length=200),
                     dir: str = "", extract: bool = False):
        """Dépose un fichier (corps brut) dans le projet ; un ZIP peut être décompressé sur place."""
        guard(P.project_dir, ws, slug)
        limit = P.MAX_UPLOAD_MB * 1024 * 1024
        if int(request.headers.get("content-length") or 0) > limit:
            raise HTTPException(status_code=413, detail=f"Fichier trop gros ({P.MAX_UPLOAD_MB} Mo maximum).")
        fname = P.clean_filename(name)
        target = guard(P.resolve, ws, slug, f"{dir.strip('/')}/{fname}" if dir.strip("/") else fname)
        if any(part in P.HIDDEN for part in Path(dir).parts):
            raise HTTPException(status_code=400, detail="Dossier réservé.")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkstemp(prefix="up_", dir=str(target.parent))[1])
        size = 0
        try:
            with open(tmp, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(status_code=413, detail=f"Fichier trop gros ({P.MAX_UPLOAD_MB} Mo maximum).")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="Fichier vide.")
            if extract and fname.lower().endswith(".zip"):
                try:
                    names = await asyncio.to_thread(P.extract_zip_into, ws, slug, tmp, dir.strip("/"))
                except Exception as exc:  # noqa: BLE001 — zip invalide, trop gros…
                    raise HTTPException(status_code=400, detail=f"Archive refusée : {exc}") from exc
                await snap(slug, f"Archive décompressée : {fname}")
                return {"extracted": len(names), "name": fname}
            tmp.replace(target)
            await snap(slug, f"Déposé : {fname}")
            return {"name": fname, "size": size, "path": target.relative_to(P.project_dir(ws, slug).resolve()).as_posix()}
        finally:
            tmp.unlink(missing_ok=True)

    @router.get("/{slug}/download")
    async def download(slug: str, path: str = ""):
        if path:
            p = guard(P.resolve, ws, slug, path)
            if not p.is_file():
                raise HTTPException(status_code=404, detail="Fichier introuvable.")
            return FileResponse(p, filename=p.name)
        z = await asyncio.to_thread(guard, P.make_zip, ws, slug)
        return FileResponse(z, filename=f"{slug}.zip", media_type="application/zip", background=BackgroundTask(lambda: z.unlink(missing_ok=True)))

    # --- historique
    @router.get("/{slug}/history")
    async def history_list(slug: str):
        guard(P.project_dir, ws, slug)
        return {"items": await asyncio.to_thread(hguard, H.log, ws, slug)}

    @router.get("/{slug}/history/{sha}")
    async def history_show(slug: str, sha: str):
        guard(P.project_dir, ws, slug)
        return await asyncio.to_thread(hguard, H.show, ws, slug, sha)

    @router.post("/{slug}/history/snapshot")
    async def history_snapshot(slug: str, body: dict):
        guard(P.project_dir, ws, slug)
        msg = str(body.get("message", "")).strip()[:150] or "Version enregistrée"
        sha = await asyncio.to_thread(hguard, H.snapshot, ws, slug, msg, H.YOU)
        return {"sha": sha, "unchanged": sha is None}

    @router.post("/{slug}/history/restore")
    async def history_restore(slug: str, body: dict):
        guard(P.project_dir, ws, slug)
        return await asyncio.to_thread(hguard, H.restore, ws, slug, str(body.get("sha", "")))

    @router.post("/{slug}/history/undo-eva")
    async def history_undo(slug: str):
        guard(P.project_dir, ws, slug)
        return await asyncio.to_thread(hguard, H.undo_eva, ws, slug)

    # --- aperçu : adresse temporaire (1 h) sans en-tête d'authentification, pour l'iframe
    @router.post("/{slug}/preview")
    async def preview_open(slug: str):
        guard(P.project_dir, ws, slug)
        now = time.time()
        for k in [k for k, v in _PREVIEW.items() if v[1] < now]:
            _PREVIEW.pop(k, None)
        tok = secrets.token_urlsafe(24)
        _PREVIEW[tok] = (slug, now + 3600)
        pages = [i["path"] for i in (await asyncio.to_thread(P.tree, ws, slug))["items"] if not i["dir"] and i["path"].lower().endswith((".html", ".htm"))]
        return {"base": f"/api/preview/{tok}/", "pages": pages[:50]}

    # --- bac à sable
    @router.get("/{slug}/sandbox")
    async def sandbox_status(slug: str):
        return await S.status(ws, slug) if guard(P.project_dir, ws, slug) else {}

    @router.post("/{slug}/sandbox/run")
    async def sandbox_run(slug: str, body: RunBody):
        guard(P.project_dir, ws, slug)
        return await S.run(ws, slug, body.command, body.timeout, body.internet)

    @router.post("/{slug}/sandbox/install")
    async def sandbox_install(slug: str, body: InstallBody):
        guard(P.project_dir, ws, slug)
        return await S.install(ws, slug, body.packages)

    @router.post("/{slug}/sandbox/db")
    async def sandbox_db_create(slug: str):
        guard(P.project_dir, ws, slug)
        i = await S.ensure_db(slug)
        return {"database": i["database"], "created": i["created"]}

    @router.post("/{slug}/sandbox/db/reset")
    async def sandbox_db_reset(slug: str):
        guard(P.project_dir, ws, slug)
        i = await S.reset_db(slug)
        return {"database": i["database"], "reset": True}

    @router.post("/{slug}/sandbox/db/query")
    async def sandbox_db_query(slug: str, body: dict):
        guard(P.project_dir, ws, slug)
        return await S.query(slug, str(body.get("sql", "")))

    pv = APIRouter(prefix="/api/preview")

    @pv.get("/{token}/{path:path}")
    async def preview(token: str, path: str = ""):
        """Sert les fichiers d'un projet (HTML/CSS/JS/images). Le document est « sandboxé » : il ne peut ni lire EVA ni agir en son nom."""
        ent = _PREVIEW.get(token)
        if not ent or ent[1] < time.time():
            raise HTTPException(status_code=404, detail="Aperçu expiré : rouvre-le depuis la page Projets.")
        slug = ent[0]
        rel = path or "index.html"
        try:
            p = P.resolve(ws, slug, rel)
            if p.is_dir():
                p = p / "index.html"
            if not p.is_file() or any(part in P.HIDDEN for part in p.relative_to(P.project_dir(ws, slug).resolve()).parts):
                raise HTTPException(status_code=404, detail="Fichier introuvable dans le projet.")
        except P.ProjectError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix.lower() in (".js", ".mjs"):
            ctype = "text/javascript"
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": "*",
                   "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups allow-modals"}
        return FileResponse(p, media_type=ctype, headers=headers)

    router.preview_router = pv
    return router
