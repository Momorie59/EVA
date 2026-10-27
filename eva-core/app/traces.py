"""Traces : un enregistrement par tour de conversation ou exécution d'agent.

Chaque trace contient les étapes (appels au modèle avec tokens et durée,
appels d'outils avec durée et résultat tronqué). Sert au débogueur de
trace et aux estimations de coût / énergie.
"""
import json
import time

from .config import settings
from .db import get_pool

RESULT_PREVIEW_CHARS = 600


def _preview(value) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= RESULT_PREVIEW_CHARS else text[:RESULT_PREVIEW_CHARS] + "…"


def _small(value):
    """Garde les arguments tels quels s'ils sont petits, sinon un aperçu texte."""
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)[:RESULT_PREVIEW_CHARS]
    return value if len(raw) <= RESULT_PREVIEW_CHARS else raw[:RESULT_PREVIEW_CHARS] + "…"


class TraceRecorder:
    def __init__(self, kind: str, session_id: str = "", label: str = "", model: str | None = None):
        self.kind = kind
        self.session_id = session_id
        self.label = label[:200]
        self.model = model or settings.ollama_model
        self.steps: list[dict] = []
        self._t0 = time.monotonic()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.erreur = ""                     # échec constaté pendant le tour (ex. trop d'étapes sans conclusion)

    def llm(self, duration_ms: int, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.steps.append(
            {
                "type": "llm",
                "duration_ms": duration_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )

    def tool(self, name: str, args: dict, duration_ms: int, result) -> None:
        ok = not (isinstance(result, dict) and "error" in result)
        self.steps.append(
            {
                "type": "tool",
                "name": name,
                "args": _small(args),
                "duration_ms": duration_ms,
                "ok": ok,
                "result": _preview(result),
            }
        )

    async def save(self, ok: bool = True, error: str = "") -> int:
        if ok and self.erreur and not error:
            ok, error = False, self.erreur
        duration_ms = int((time.monotonic() - self._t0) * 1000)
        async with get_pool().acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO traces (kind, session_id, label, model, duration_ms,
                                    prompt_tokens, completion_tokens, steps, ok, error)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10) RETURNING id
                """,
                self.kind,
                self.session_id,
                self.label,
                self.model,
                duration_ms,
                self.prompt_tokens,
                self.completion_tokens,
                json.dumps(self.steps, ensure_ascii=False),
                ok,
                error[:500],
            )
