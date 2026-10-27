import asyncio
import json
import re
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .config import settings

from . import hf_catalog, llm_opts
from . import router as mrouter
from .db import get_pool


class RouterConfig(BaseModel):
    mode: str = "auto"
    default: str = ""
    fast: str = ""
    code: str = ""
    reasoning: str = ""
    vision: str = ""


class SessionModel(BaseModel):
    model: str = ""


class PullBody(BaseModel):
    name: str


class WarmBody(BaseModel):
    model: str = ""


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,100}$")
PULLS: dict[str, dict] = {}       # état des téléchargements en cours / récents
_WARM = {"at": 0.0, "model": ""}
_REC: dict = {"at": 0.0, "data": None}


def _host() -> str:
    return settings.ollama_host.rstrip("/")


async def _pull_task(name: str) -> None:
    st = PULLS[name]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            async with client.stream("POST", f"{_host()}/api/pull", json={"name": name, "stream": True}) as r:
                if r.status_code != 200:
                    st.update(error=f"Ollama a répondu {r.status_code}", done=True)
                    return
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("error"):
                        st.update(error=str(ev["error"])[:300], done=True)
                        return
                    st.update(status=ev.get("status", ""), completed=ev.get("completed", st.get("completed", 0)),
                              total=ev.get("total", st.get("total", 0)))
        st.update(done=True, status="terminé")
        await mrouter.installed_models(force=True)
    except httpx.HTTPError as exc:
        st.update(error=f"Serveur IA injoignable : {exc}", done=True)


class HardwareBody(BaseModel):
    vram_gb: float
    ram_gb: float


class OptionsBody(BaseModel):
    num_ctx: int
    temperature: float


class Preview(BaseModel):
    text: str
    has_image: bool = False


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/models")
    async def models():
        installed = await mrouter.installed_models(force=True)
        cfg = await mrouter.load_config()
        liste = list(installed or [])
        if installed is None:                     # serveur IA éteint : les IA gratuites / du marché restent proposées
            from . import cloud_ai
            try:
                liste += await cloud_ai.model_entries()
            except Exception:  # noqa: BLE001
                pass
        try:                                      # « en mémoire » : répond sans temps de chargement
            from . import perf
            charges = {m["name"] for m in (await perf.modeles_charges() or [])}
        except Exception:  # noqa: BLE001
            charges = set()
        for m in liste:
            m["charge"] = m["name"] in charges
        return {
            "reachable": installed is not None,
            "installed": liste,
            "config": cfg,
            "suggestion": mrouter.suggest(installed) if installed else None,
        }

    @router.get("/models/options")
    async def get_options():
        return llm_opts.options()

    @router.put("/models/options")
    async def put_options(body: OptionsBody):
        try:
            return await llm_opts.save(body.num_ctx, body.temperature)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/models/vitesse")
    async def vitesse():
        """Modèles en mémoire vidéo, rechargements et vitesse sur la dernière heure (Paramètres › Intelligence)."""
        from . import perf
        return await perf.resume()

    @router.get("/models/hardware")
    async def hardware():
        return await hf_catalog.get_hardware()

    @router.put("/models/hardware")
    async def put_hardware(body: HardwareBody):
        try:
            _REC["data"] = None
            return await hf_catalog.set_hardware(body.vram_gb, body.ram_gb)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/models/hf/search")
    async def hf_search(q: str = "", sort: str = "downloads"):
        try:
            return {"hardware": await hf_catalog.get_hardware(), "results": await hf_catalog.search(q, sort)}
        except hf_catalog.HFError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/models/recommend")
    async def recommend(refresh: bool = False):
        """Meilleurs modèles Hugging Face par rôle, adaptés à la puissance du serveur IA (gardé 30 min)."""
        import time as _t
        hit = _REC.get("data")
        if hit and not refresh and _t.monotonic() - _REC["at"] < 1800:
            return hit
        try:
            data = await hf_catalog.recommend()
        except hf_catalog.HFError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        _REC.update(at=_t.monotonic(), data=data)
        return data

    @router.get("/models/hf/files")
    async def hf_files(repo: str):
        try:
            return await hf_catalog.files(repo)
        except hf_catalog.HFError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/models/pull")
    async def pull(body: PullBody):
        name = body.name.strip()
        if not NAME_RE.match(name):
            raise HTTPException(status_code=400, detail="Nom de modèle invalide (ex. llama3.2:3b).")
        cur = PULLS.get(name)
        if cur and not cur.get("done"):
            return cur
        PULLS[name] = {"name": name, "status": "démarrage", "completed": 0, "total": 0, "done": False, "error": ""}
        asyncio.create_task(_pull_task(name))
        return PULLS[name]

    @router.get("/models/pulls")
    async def pulls():
        return {"pulls": list(PULLS.values())}

    @router.delete("/models/{name:path}")
    async def remove(name: str):
        if not NAME_RE.match(name):
            raise HTTPException(status_code=400, detail="Nom de modèle invalide.")
        cfg = await mrouter.load_config()
        if name in {settings.ollama_model, *[v for v in cfg.values() if isinstance(v, str)]}:
            raise HTTPException(status_code=409, detail="Ce modèle est utilisé dans les réglages : change d'abord l'attribution.")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.request("DELETE", f"{_host()}/api/delete", json={"name": name})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Serveur IA injoignable : {exc}") from exc
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama a répondu {r.status_code}")
        await mrouter.installed_models(force=True)
        return {"ok": True}

    @router.post("/models/warm")
    async def warm(body: WarmBody):
        """Charge le modèle rapide en mémoire dès que l'utilisateur commence à parler (gain de plusieurs secondes si déchargé)."""
        model = body.model.strip()
        if not model:
            model = (await mrouter.select("bonjour", False, prefer_fast=True))["model"]
        if not NAME_RE.match(model):
            raise HTTPException(status_code=400, detail="Nom de modèle invalide.")
        if _WARM["model"] == model and time.monotonic() - _WARM["at"] < 120:
            return {"ok": True, "model": model, "skipped": True}
        _WARM.update(at=time.monotonic(), model=model)

        async def _go():
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    await client.post(f"{_host()}/api/generate", json={"model": model, "prompt": "", "keep_alive": settings.keep_alive})
            except httpx.HTTPError:
                pass
        asyncio.create_task(_go())
        return {"ok": True, "model": model, "skipped": False}

    @router.put("/models/router")
    async def put_config(body: RouterConfig):
        try:
            return await mrouter.save_config(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/models/preview")
    async def preview(body: Preview):
        return await mrouter.select(body.text, body.has_image)

    @router.put("/sessions/{session_id}/model")
    async def session_model(session_id: str, body: SessionModel, request: Request):
        model = body.model.strip()
        if model:
            installed = await mrouter.installed_models()
            if installed is not None and model not in {m["name"] for m in installed}:
                raise HTTPException(status_code=400, detail=f"Modèle absent du serveur IA : {model}")
        from . import auth as auth_mod, sessions as sessions_db
        me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization"))) if auth_mod.protected() else None
        proprietaire = None if (me is None or me["role"] == "admin") else me["user"]
        if not await sessions_db.can_access(session_id, proprietaire):
            raise HTTPException(status_code=404, detail="Conversation introuvable.")
        async with get_pool().acquire() as conn:
            res = await conn.execute("UPDATE sessions SET model=$2 WHERE id=$1", session_id, model)
            if res.endswith(" 0"):                      # conversation pas encore commencée (accueil) : on la crée avec ce choix
                await conn.execute("INSERT INTO sessions (id, title, owner, model) VALUES ($1, '', $2, $3) ON CONFLICT (id) DO UPDATE SET model=$3",
                                   session_id, (me or {}).get("user", "") if me and me["role"] != "admin" else "", model)
        return {"ok": True, "model": model}

    @router.get("/sessions/{session_id}/model")
    async def session_model_lire(session_id: str):
        async with get_pool().acquire() as conn:
            return {"model": (await conn.fetchval("SELECT model FROM sessions WHERE id=$1", session_id)) or ""}

    return router
