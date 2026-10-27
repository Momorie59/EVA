import json
from typing import AsyncGenerator, Optional

import httpx

from . import cloud_ai, perf, llm_opts
from .config import settings

import os as _os
import re as _re

_PENSEURS = _re.compile(r"^(qwen3|qwq|deepseek-r1|magistral|gpt-oss|phi4-reasoning)", _re.I)
REFLEXION = _os.getenv("EVA_REFLEXION", "0") == "1"


def _sans_reflexion(payload: dict) -> dict:
    """Modèles à « réflexion » (qwen3.5…) : on la coupe pour répondre vite, sauf si EVA_REFLEXION=1."""
    if not REFLEXION and _PENSEURS.match(str(payload.get("model") or "")):
        payload["think"] = False
    return payload


async def _hors_budget(model):
    """Modèle du marché dont le budget du mois est atteint → modèle local (comme Jarvis)."""
    if cloud_ai.is_cloud(model) and not await cloud_ai.dans_budget(model):
        return settings.ollama_model
    return model


class OllamaError(RuntimeError):
    """Levée quand le serveur IA (Ollama) est injoignable ou renvoie une erreur."""


AIRLLM = "airllm"


async def _airllm_chat(messages: list[dict]) -> str:
    """Réponse du service AirLLM (très lent : minutes). Pas d'outils, pas de streaming."""
    if not settings.airllm_url:
        raise OllamaError("AirLLM n'est pas configuré (EVA_AIRLLM_URL).")
    plain = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages if m.get("role") in ("system", "user", "assistant")]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.airllm_timeout, connect=10.0)) as client:
            r = await client.post(f"{settings.airllm_url.rstrip('/')}/v1/chat/completions", json={"messages": plain})
    except httpx.HTTPError as exc:
        raise OllamaError(f"Service AirLLM injoignable ou trop lent : {exc}") from exc
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", "")
        except ValueError:
            detail = r.text[:200]
        raise OllamaError(f"AirLLM : {detail or r.status_code}")
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


async def arreter_airllm() -> None:
    """Demande au service AirLLM d'arrêter la réponse en cours (bouton « Arrêter »)."""
    if not settings.airllm_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{settings.airllm_url.rstrip('/')}/stop")
    except httpx.HTTPError:
        pass


async def chat_once(messages: list[dict], tools: Optional[list[dict]] = None, model: Optional[str] = None) -> dict:
    """Appel non-streamé à /api/chat — utilisé par le Harness pour la phase
    de décision (le modèle doit pouvoir renvoyer des tool_calls d'un bloc,
    ce qui est plus simple à traiter qu'en streaming)."""
    model = await _hors_budget(model)
    if cloud_ai.is_cloud(model):
        try:
            return await cloud_ai.complete(messages, tools, model)
        except cloud_ai.CloudError as exc:
            raise OllamaError(str(exc)) from exc
    if model == AIRLLM:
        return {"message": {"role": "assistant", "content": await _airllm_chat(messages)}, "done": True}
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model or settings.ollama_model,
        "keep_alive": settings.keep_alive,
        "messages": messages,
        "stream": False,
        "options": llm_opts.options(),
    }
    if tools:
        payload["tools"] = tools
    _sans_reflexion(payload)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise OllamaError(
                    f"Ollama a répondu {response.status_code} : {response.text[:300]}"
                )
            data = response.json()
            perf.noter(payload["model"], data)
            return data.get("message", {"role": "assistant", "content": ""})
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Impossible de joindre Ollama sur {settings.ollama_host} — "
            "vérifie que le serveur IA est allumé, qu'Ollama tourne, et que "
            "OLLAMA_HOST pointe vers la bonne adresse réseau."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama n'a pas répondu à temps.") from exc


async def stream_decide(
    messages: list[dict], tools: Optional[list[dict]] = None, model: Optional[str] = None
) -> AsyncGenerator[tuple[str, object], None]:
    """Version streamée de la phase de décision du Harness.

    Remplace l'ancien `chat_once` (non-streamé) : permet d'envoyer le texte
    d'une réponse directe au client au fur et à mesure qu'il arrive, plutôt
    que d'attendre la génération complète puis la "rejouer" artificiellement
    mot par mot.

    Émet des tuples :
    - `("content", texte)` pour chaque fragment de texte généré
    - `("usage", {prompt_tokens, completion_tokens, total_duration_ms})` en fin de flux
    - `("tool_calls", liste_ou_None)` une fois le flux terminé — la liste
      des appels d'outils décidés par le modèle, ou None s'il a répondu
      directement sans en demander.

    Hypothèse (non vérifiable sans serveur Ollama réel dans cet
    environnement) : en streaming, Ollama envoie le contenu texte au fil
    des lignes NDJSON et les `tool_calls`, s'il y en a, dans le message
    final (`done: true`) — comportement standard documenté par Ollama,
    cohérent entre les principaux modèles à outils, mais à surveiller si
    un modèle se comporte différemment en usage réel.
    """
    model = await _hors_budget(model)
    if cloud_ai.is_cloud(model):
        try:
            async for ev in cloud_ai.stream(messages, tools, model):
                yield ev
        except cloud_ai.CloudError as exc:
            raise OllamaError(str(exc)) from exc
        return
    if model == AIRLLM:
        text = await _airllm_chat(messages)
        yield ("content", text)
        yield ("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_duration_ms": 0})
        yield ("tool_calls", None)
        return
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model or settings.ollama_model,
        "keep_alive": settings.keep_alive,
        "messages": messages,
        "stream": True,
        "options": llm_opts.options(),
    }
    if tools:
        payload["tools"] = tools
    _sans_reflexion(payload)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise OllamaError(
                        f"Ollama a répondu {response.status_code} : {body.decode(errors='ignore')[:300]}"
                    )

                final_tool_calls = None
                usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_duration_ms": 0}
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    message = data.get("message", {})

                    content = message.get("content", "")
                    if content:
                        yield ("content", content)

                    if message.get("tool_calls"):
                        final_tool_calls = message["tool_calls"]

                    if data.get("done"):
                        mesure = perf.noter(payload["model"], data)
                        usage = {
                            "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
                            "completion_tokens": data.get("eval_count", 0) or 0,
                            "total_duration_ms": int((data.get("total_duration", 0) or 0) / 1e6),
                            "load_ms": mesure["load_ms"],
                        }
                        break

                yield ("usage", usage)
                yield ("tool_calls", final_tool_calls)
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Impossible de joindre Ollama sur {settings.ollama_host} — "
            "vérifie que le serveur IA est allumé, qu'Ollama tourne, et que "
            "OLLAMA_HOST pointe vers la bonne adresse réseau."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama n'a pas répondu à temps.") from exc


async def stream_chat(messages: list[dict], model: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Diffuse les morceaux de réponse d'Ollama au fur et à mesure qu'ils arrivent.

    Utilise l'endpoint /api/chat d'Ollama (streaming NDJSON) : chaque ligne
    reçue est un objet JSON contenant un fragment de la réponse.

    `model` permet d'utiliser un modèle différent de celui par défaut —
    typiquement le modèle vision pour un message avec image, qui n'est pas
    forcément le même que le modèle utilisé pour les outils.
    """
    model = await _hors_budget(model)
    if cloud_ai.is_cloud(model):
        try:
            async for kind, v in cloud_ai.stream(messages, None, model):
                if kind == "content":
                    yield v
        except cloud_ai.CloudError as exc:
            raise OllamaError(str(exc)) from exc
        return
    if model == AIRLLM:
        yield await _airllm_chat(messages)
        return
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model or settings.ollama_model,
        "keep_alive": settings.keep_alive,
        "messages": messages,
        "stream": True,
        "options": llm_opts.options(),
    }
    _sans_reflexion(payload)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise OllamaError(
                        f"Ollama a répondu {response.status_code} : {body.decode(errors='ignore')[:300]}"
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Impossible de joindre Ollama sur {settings.ollama_host} — "
            "vérifie que le serveur IA est allumé, qu'Ollama tourne, et que "
            "OLLAMA_HOST pointe vers la bonne adresse réseau."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama n'a pas répondu à temps.") from exc
