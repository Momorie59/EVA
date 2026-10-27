from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import base64

from . import auth as auth_mod, image_models, imageedit, images


class ImageCfg(BaseModel):
    url: str = ""
    kind: str = "a1111"
    model: str = ""
    steps: int = 0
    size: int = 0
    negative: str | None = None
    enhance: bool = True
    token: str | None = None


class GenBody(BaseModel):
    prompt: str


class EditBody(BaseModel):
    instruction: str
    image: str = ""            # nom d'une image de la galerie ; vide = la dernière
    data: str = ""             # ou une photo envoyée (base64 / data URI)


class ModelBody(BaseModel):
    id: str


class GalleryCfg(BaseModel):
    keep_days: int = 30
    max_items: int = 200


class PinBody(BaseModel):
    pinned: bool = True


from . import profiles  # noqa: E402


async def _scope(request: Request) -> None:
    """Qui demande ? Un utilisateur standard ne voit et ne modifie que ses propres images."""
    owner = None
    if auth_mod.protected():
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
        if me is not None and me["role"] != "admin":
            owner = me["user"]
        images.neg_extra_var.set(profiles.image_block(me["role"]) if me is not None else "")
    images.owner_var.set(owner)


def make_router(workspace: Path) -> APIRouter:
    router = APIRouter(prefix="/api/images", dependencies=[Depends(_scope)])

    @router.get("/config")
    async def get_cfg():
        return images.public(await images.get_config())

    @router.put("/config")
    async def put_cfg(body: ImageCfg):
        try:
            return await images.set_config(body.url, body.kind, body.model, body.steps, body.size, body.negative, body.enhance, body.token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/status")
    async def get_status():
        return await images.status()

    @router.post("/detect")
    async def detect():
        """Cherche le serveur eva-imagegen sur le serveur IA / le réseau Docker et l'enregistre."""
        found = await images.detect()
        if not found:
            raise HTTPException(status_code=404, detail="Aucun serveur eva-imagegen trouvé (port 7860). Lance-le sur ton serveur IA : cd eva-imagegen && docker compose up -d --build.")
        cfg = await images.get_config()
        await images.set_config(found["url"], "a1111", cfg["model"], cfg["steps"], cfg["size"], None, cfg["enhance"], None)
        return found

    @router.post("/test")
    async def test():
        """Génère une petite image d'essai pour vérifier que le serveur d'images répond."""
        cfg = await images.get_config()
        if not cfg["url"]:
            raise HTTPException(status_code=400, detail="Aucun serveur d'images configuré.")
        try:
            png = await images.generate("a small red apple on a wooden table, photo", {**cfg, "size": 256})
        except images.ImageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": True, "bytes": len(png)}

    @router.post("/generate")
    async def generate(body: GenBody):
        """Crée une image à partir d'une description (en français ou en anglais) et la range dans la galerie."""
        cfg = await images.get_config()
        if not cfg["url"]:
            raise HTTPException(status_code=400, detail=images.NOT_CONFIGURED)
        subject = body.prompt.strip()[:1000]
        if not subject:
            raise HTTPException(status_code=400, detail="Décris l'image à créer.")
        final = await images.enhance(subject) if cfg["enhance"] else subject
        try:
            png = await images.generate(final, cfg)
        except images.ImageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        p = images.save(png, workspace, subject, final)
        return {"name": p.name, "prompt": subject, "final": final, "image": images.thumb(workspace, p.name, 0)}

    @router.post("/edit")
    async def edit(body: EditBody):
        """Modifie une image (galerie ou photo envoyée) d'après une demande en français ; le résultat est une nouvelle image de la galerie."""
        text = body.instruction.strip()[:500]
        if not text:
            raise HTTPException(status_code=400, detail="Dis ce qu'il faut changer sur l'image.")
        if body.data:
            try:
                src = base64.b64decode(body.data.split(",", 1)[-1])
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Image illisible.") from exc
        elif body.image:
            if not images._NAME.match(body.image):
                raise HTTPException(status_code=400, detail="Nom d'image invalide.")
            f = workspace / "generated" / body.image
            try:
                images.check_access(workspace, body.image, images.owner_var.get())
            except images.ImageError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if not f.is_file():
                raise HTTPException(status_code=404, detail="Image introuvable (peut-être purgée).")
            src = f.read_bytes()
        else:
            got = images.latest(workspace, max_age=86400)
            if not got:
                raise HTTPException(status_code=404, detail="Aucune image à modifier.")
            src = got[1]
        pl = imageedit.plan(text, has_attachment=True)
        if not pl:
            raise HTTPException(status_code=400, detail="Je n'ai pas compris la modification (ex. « mets en noir et blanc », « enlève le poteau », « transforme en aquarelle »).")
        try:
            out, summary = await imageedit.run(src, pl, text)
        except images.ImageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        p = images.save(out, workspace, text, summary, kind="edit")
        return {"name": p.name, "summary": summary, "image": images.thumb(workspace, p.name, 0)}

    def _srv(exc):
        return HTTPException(status_code=502, detail=str(exc))

    @router.get("/models")
    async def models():
        return await image_models.overview()

    @router.post("/models/pull")
    async def models_pull(body: ModelBody):
        try:
            return await image_models.pull(body.id.strip())
        except image_models.ServerError as exc:
            raise _srv(exc) from exc

    @router.post("/models/use")
    async def models_use(body: ModelBody):
        return await image_models.use(body.id)

    @router.post("/models/delete")
    async def models_delete(body: ModelBody):
        try:
            return await image_models.delete(body.id.strip())
        except image_models.ServerError as exc:
            raise _srv(exc) from exc

    @router.post("/server/update")
    async def server_update():
        try:
            return await image_models.update_server()
        except image_models.ServerError as exc:
            raise _srv(exc) from exc

    @router.get("/gallery-config")
    async def get_gallery_cfg():
        return await images.get_gallery_cfg()

    @router.put("/gallery-config")
    async def put_gallery_cfg(body: GalleryCfg):
        return await images.set_gallery_cfg(body.keep_days, body.max_items)

    @router.post("/purge")
    async def purge_now():
        cfg = await images.get_gallery_cfg()
        return images.purge(workspace, cfg["keep_days"], cfg["max_items"])

    @router.post("/item/{name}/pin")
    async def pin_item(name: str, body: PinBody):
        try:
            images.check_access(workspace, name, images.owner_var.get())
            images.set_pinned(workspace, name, body.pinned)
        except images.ImageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "pinned": body.pinned}

    @router.get("/gallery")
    async def get_gallery():
        items = images.gallery(workspace, 500, images.owner_var.get())
        for it in items:
            try:
                it["thumb"] = images.thumb(workspace, it["name"], 256)
            except images.ImageError:
                it["thumb"] = ""
        return {"items": items}

    @router.get("/item/{name}")
    async def item(name: str):
        try:
            images.check_access(workspace, name, images.owner_var.get())
            return {"image": images.thumb(workspace, name, 0)}
        except images.ImageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/item/{name}")
    async def delete_item(name: str):
        try:
            images.check_access(workspace, name, images.owner_var.get())
            images.remove(workspace, name)
        except images.ImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    return router
