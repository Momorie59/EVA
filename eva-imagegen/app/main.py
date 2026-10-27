"""Serveur d'images d'EVA. Deux « langues » pour le même moteur :
- API Stable Diffusion WebUI (/sdapi/v1/…) — celle qu'EVA utilise ;
- API OpenAI (/v1/images/generations), pour tout autre client.
+ /health (état, carte graphique, modèle) et /unload (libérer la mémoire de la carte tout de suite)."""
import asyncio
import base64
import hmac
import os
import re
import threading

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from pathlib import Path

from . import VERSION, models as hubmodels, engine as videomod
from .engine import ImageGenError, MODEL, engine, list_models, profile

TOKEN = os.getenv("IMAGEGEN_TOKEN", "")
app = FastAPI(title="EVA imagegen")


def auth(authorization: str = Header(default="")) -> None:
    if TOKEN and not hmac.compare_digest(authorization.removeprefix("Bearer ").strip(), TOKEN):
        raise HTTPException(401, "Jeton invalide.")


_idle_task: asyncio.Task | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _idle_task

    async def idle():
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(engine.idle_check)
    _idle_task = asyncio.create_task(idle())
    if os.getenv("IMAGEGEN_PRELOAD", "0") in ("1", "true", "yes"):
        threading.Thread(target=lambda: _safe_warm(), daemon=True).start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _idle_task:
        _idle_task.cancel()


def _safe_warm() -> None:
    try:
        engine.generate("a red apple", steps=1, width=64, height=64)
    except Exception:  # noqa: BLE001
        pass


@app.get("/health")
async def health():
    return {**engine.status(), "models": [m["title"] for m in list_models()], "default_model": MODEL, "version": VERSION, "video": videomod.video_status()}


@app.post("/unload", dependencies=[Depends(auth)])
async def unload():
    return {"unloaded": await asyncio.to_thread(engine.unload)}


class Txt2Img(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 0
    height: int = 0
    steps: int = 0
    cfg_scale: float | None = None
    seed: int = -1
    batch_size: int = 1
    n_iter: int = 1
    override_settings: dict | None = None
    model_config = {"extra": "ignore"}


async def _run(**kw):
    try:
        return await asyncio.to_thread(engine.generate, **kw)
    except ImageGenError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/sdapi/v1/txt2img", dependencies=[Depends(auth)])
async def txt2img(b: Txt2Img):
    model = (b.override_settings or {}).get("sd_model_checkpoint", "")
    imgs, info = await _run(prompt=b.prompt, negative=b.negative_prompt, width=b.width, height=b.height, steps=b.steps, cfg=b.cfg_scale,
                            seed=b.seed, n=b.batch_size * max(1, b.n_iter), model=model)
    import json
    return {"images": [base64.b64encode(i).decode() for i in imgs], "parameters": b.model_dump(), "info": json.dumps(info)}


@app.get("/sdapi/v1/sd-models", dependencies=[Depends(auth)])
async def sd_models():
    return list_models()


@app.get("/sdapi/v1/options", dependencies=[Depends(auth)])
async def get_options():
    return {"sd_model_checkpoint": engine.current}


@app.post("/sdapi/v1/options", dependencies=[Depends(auth)])
async def set_options(body: dict):
    if body.get("sd_model_checkpoint"):
        try:
            engine.set_model(str(body["sd_model_checkpoint"]))
        except ImageGenError as exc:
            raise HTTPException(400, str(exc)) from exc
    return {}


@app.get("/sdapi/v1/progress")
async def progress():
    return {"progress": 0.5 if engine.busy else 0.0, "state": {"job_count": int(engine.busy)}}


class OpenAIImg(BaseModel):
    prompt: str
    n: int = 1
    size: str = ""
    model: str = ""
    response_format: str = "b64_json"
    model_config = {"extra": "ignore"}


@app.post("/v1/images/generations", dependencies=[Depends(auth)])
async def openai_images(b: OpenAIImg):
    w = h = 0
    if b.size:
        m = re.fullmatch(r"(\d{2,4})x(\d{2,4})", b.size.strip().lower())
        if not m:
            raise HTTPException(400, "Taille invalide (ex. 512x512).")
        w, h = int(m.group(1)), int(m.group(2))
    model = b.model if b.model and b.model not in ("dall-e-2", "dall-e-3", "gpt-image-1") else ""
    imgs, _ = await _run(prompt=b.prompt, width=w, height=h, n=b.n, model=model)
    return {"created": int(__import__("time").time()), "data": [{"b64_json": base64.b64encode(i).decode()} for i in imgs]}


class Img2Img(BaseModel):
    init_images: list[str] = []
    mask: str | None = None
    prompt: str = ""
    negative_prompt: str = ""
    denoising_strength: float | None = None
    steps: int = 0
    cfg_scale: float | None = None
    seed: int = -1
    override_settings: dict | None = None
    model_config = {"extra": "ignore"}


def _b64(data: str) -> bytes:
    try:
        return base64.b64decode(data.split(",", 1)[-1], validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Image illisible (base64).") from exc


async def _edit(**kw):
    try:
        return await asyncio.to_thread(engine.edit, **kw)
    except ImageGenError as exc:
        raise HTTPException(500, str(exc)) from exc


def _edit_reply(imgs, info, params):
    import json
    return {"images": [base64.b64encode(i).decode() for i in imgs], "parameters": params, "info": json.dumps(info)}


@app.post("/sdapi/v1/img2img", dependencies=[Depends(auth)])
async def img2img(b: Img2Img):
    """API Stable Diffusion WebUI : image → image ; avec `mask` (blanc = à refaire) : retouche d'une zone."""
    if not b.init_images:
        raise HTTPException(400, "init_images manquant.")
    imgs, info = await _edit(image=_b64(b.init_images[0]), prompt=b.prompt, negative=b.negative_prompt, strength=b.denoising_strength, steps=b.steps, cfg=b.cfg_scale,
                             seed=b.seed, model=(b.override_settings or {}).get("sd_model_checkpoint", ""), mask=_b64(b.mask) if b.mask else None)
    return _edit_reply(imgs, info, b.model_dump(exclude={"init_images", "mask"}))


class EvaEdit(BaseModel):
    image: str
    prompt: str
    negative_prompt: str = ""
    target: str = ""            # « le poteau » : seule cette zone est refaite (trouvée automatiquement)
    strength: float | None = None
    steps: int = 0
    cfg_scale: float | None = None
    seed: int = -1
    grow: int = 10
    model: str = ""
    model_config = {"extra": "ignore"}


@app.post("/eva/edit", dependencies=[Depends(auth)])
async def eva_edit(b: EvaEdit):
    """Modification par le texte : toute l'image (target vide) ou seulement la zone désignée par un mot (target)."""
    imgs, info = await _edit(image=_b64(b.image), prompt=b.prompt, negative=b.negative_prompt, strength=b.strength, steps=b.steps, cfg=b.cfg_scale, seed=b.seed,
                             model=b.model, target=b.target, grow=max(0, min(b.grow, 40)))
    return _edit_reply(imgs, info, {"prompt": b.prompt, "target": b.target})


class VideoReq(BaseModel):
    prompt: str = ""
    frames: int = 25
    steps: int = 20
    width: int = 512
    height: int = 320
    seed: int = -1
    model_config = {"extra": "ignore"}


@app.post("/eva/video", dependencies=[Depends(auth)])
async def eva_video(b: VideoReq):
    """Clip vidéo par IA (expérimental, désactivé par défaut). Réponse : WebP animé en base64."""
    if not videomod.VIDEO_ENABLED:
        raise HTTPException(403, videomod.DISABLED_MSG)
    try:
        data, info = await asyncio.to_thread(videomod.generate_video, b.prompt, b.frames, b.steps, b.width, b.height, b.seed)
    except ImageGenError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"webp_b64": base64.b64encode(data).decode(), **info}


# ---------------------------------------------------------------- modèles : liste, téléchargement, suppression (pilotés depuis EVA)
@app.get("/eva/installed", dependencies=[Depends(auth)])
async def eva_installed():
    return {"models": await asyncio.to_thread(hubmodels.installed), "disk_free_gb": hubmodels.disk_free_gb(), "active": engine.current, "default": MODEL, "version": VERSION,
            "gpu": engine.status().get("gpu", {}), "device": engine.status().get("device", "cpu")}


class ModelId(BaseModel):
    id: str


@app.post("/eva/pull", dependencies=[Depends(auth)])
async def eva_pull(b: ModelId):
    try:
        return hubmodels.start_pull(b.id.strip(), os.getenv("HF_TOKEN", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/eva/pulls", dependencies=[Depends(auth)])
async def eva_pulls():
    return {"pulls": list(hubmodels.PULLS.values())}


@app.post("/eva/delete", dependencies=[Depends(auth)])
async def eva_delete(b: ModelId):
    mid = b.id.strip()
    if engine.current == mid or engine.spec.endswith(mid):
        await asyncio.to_thread(engine.unload)                      # libère les fichiers avant de les supprimer
    if not await asyncio.to_thread(hubmodels.delete, mid):
        raise HTTPException(404, "Modèle introuvable.")
    return {"ok": True}


# ---------------------------------------------------------------- mise à jour du code du serveur, depuis EVA (jeton obligatoire)
APP_DIR = Path(__file__).resolve().parent
UPDATABLE = {"__init__.py", "engine.py", "main.py", "models.py"}


class UpdateBody(BaseModel):
    files: dict[str, str]


def _restart() -> None:
    """Redémarre le conteneur (la politique « unless-stopped » de Docker le relance avec le nouveau code)."""
    threading.Timer(1.5, os._exit, [3]).start()


@app.post("/eva/update", dependencies=[Depends(auth)])
async def eva_update(b: UpdateBody):
    if not TOKEN:
        raise HTTPException(403, "Mise à jour à distance désactivée : ce serveur n'a pas de jeton (IMAGEGEN_TOKEN). Relance install-imagegen.sh : il en crée un.")
    if not b.files or set(b.files) - UPDATABLE:
        raise HTTPException(400, "Fichiers non autorisés.")
    new: dict[str, bytes] = {}
    for name, data in b.files.items():
        try:
            raw = base64.b64decode(data, validate=True)
            if len(raw) > 400_000:
                raise ValueError("trop gros")
            compile(raw.decode("utf-8"), name, "exec")                # on refuse un fichier qui ne compile pas : le serveur doit pouvoir redémarrer
        except (ValueError, SyntaxError, UnicodeDecodeError) as exc:
            raise HTTPException(400, f"Fichier {name} invalide : {exc}") from exc
        new[name] = raw
    import time
    backup = hubmodels.MODELS_DIR / ".update-backup" / time.strftime("%Y%m%d-%H%M%S")
    try:
        backup.mkdir(parents=True, exist_ok=True)
        for name in new:
            if (APP_DIR / name).is_file():
                (backup / name).write_bytes((APP_DIR / name).read_bytes())
    except OSError:
        pass                                                          # la sauvegarde est un confort : elle n'empêche pas la mise à jour
    for name, raw in new.items():
        tmp = APP_DIR / (name + ".new")
        tmp.write_bytes(raw)
        os.replace(tmp, APP_DIR / name)
    m = re.search(rb"VERSION\s*=\s*(\d+)", new.get("__init__.py", b""))
    _restart()
    return {"ok": True, "version": int(m.group(1)) if m else None, "restarting": True}
