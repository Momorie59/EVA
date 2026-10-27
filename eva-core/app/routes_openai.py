"""API compatible OpenAI (/api/v1/models, /api/v1/chat/completions) : permet d'utiliser EVA depuis n'importe quel
client OpenAI (extensions d'éditeur, Open WebUI, scripts…). Ce n'est PAS l'agent complet : c'est la conversation
avec les modèles locaux. Modèle « eva » = choix automatique du modèle (routeur) + personnalité d'EVA ; tout autre
nom est transmis tel quel à Ollama. Protégé par le même jeton que le reste (Authorization: Bearer …)."""
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import router as model_router
from .config import settings

EVA_MODEL = "eva"


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/models")
    async def models():
        installed = await model_router.installed_models()
        names = [EVA_MODEL] + [m["name"] for m in installed if "embedding" not in (m.get("capabilities") or [])]
        return {"object": "list", "data": [{"id": n, "object": "model", "owned_by": "eva"} for n in names]}

    @router.post("/chat/completions")
    async def completions(request: Request):
        body = await request.json()
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="« messages » est requis.")
        if body.get("model", EVA_MODEL) in (EVA_MODEL, "", None):
            last = next((_text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
            choice = await model_router.select(last)
            body["model"] = choice["model"]
            if not any(m.get("role") == "system" for m in messages):
                body["messages"] = [{"role": "system", "content": settings.system_prompt}] + messages
            if not choice["tools"]:
                body.pop("tools", None)
        url = f"{settings.ollama_host.rstrip('/')}/v1/chat/completions"
        timeout = httpx.Timeout(300.0, connect=10.0)

        if body.get("stream"):
            async def gen():
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        async with client.stream("POST", url, json=body) as r:
                            if r.status_code != 200:
                                err = (await r.aread()).decode(errors="replace")[:300]
                                yield f"data: {json.dumps({'error': {'message': f'Ollama a répondu {r.status_code} : {err}'}})}\n\n"
                                return
                            async for chunk in r.aiter_raw():
                                yield chunk
                except httpx.HTTPError as exc:
                    yield f"data: {json.dumps({'error': {'message': f'Ollama injoignable : {exc}'}})}\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Ollama injoignable : {exc}") from exc
        return JSONResponse(r.json() if r.headers.get("content-type", "").startswith("application/json")
                            else {"error": {"message": r.text[:300]}}, status_code=r.status_code)

    return router
