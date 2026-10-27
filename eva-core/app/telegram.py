"""Canal Telegram : parler à EVA depuis le téléphone.

Fonctionnement : EVA interroge l'API Telegram (long polling, aucune ouverture de port sur le NAS).
Sécurité : seuls les identifiants de discussion de la liste blanche (Paramètres) sont servis ; les autres
reçoivent uniquement leur propre identifiant pour pouvoir être ajoutés. Les actions sensibles demandent
confirmation par message (« oui » / « non », 2 minutes, sinon refus)."""
import asyncio
import json
import logging

import httpx

from . import router as model_router
from . import skills as skills_mod
from .config import settings
from .db import get_pool
from .memory import load_recent, save_message
from .sessions import effacer_session, ensure_session, touch_session
from .traces import TraceRecorder

logger = logging.getLogger("eva-core.telegram")

CONFIRM_TIMEOUT = 120
MAX_LEN = 3900
YES = {"oui", "o", "yes", "y", "ok", "d'accord", "go"}
NO = {"non", "n", "no", "annule", "stop"}

_registry = None
_workspace = None
_pending: dict[int, asyncio.Future] = {}
_locks: dict[int, asyncio.Lock] = {}
_state = {"running": False, "last_error": "", "username": ""}


class TelegramError(RuntimeError):
    pass


def bind(registry, workspace_root) -> None:
    global _registry, _workspace
    _registry, _workspace = registry, workspace_root


async def _post(token: str, method: str, payload: dict, timeout: float = 15.0) -> dict:
    """Seul point d'accès réseau (remplaçable dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TelegramError(f"Telegram injoignable : {exc}") from exc
    if not data.get("ok"):
        raise TelegramError(data.get("description") or "Réponse Telegram invalide.")
    return data["result"]


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='telegram'")
    saved = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return {"token": saved.get("token", ""), "allowed": [int(x) for x in saved.get("allowed", [])],
            "offset": int(saved.get("offset", 0)), "alerts": bool(saved.get("alerts", True))}


async def _store(cfg: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO kv (key, value) VALUES ('telegram', $1::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", json.dumps(cfg))


async def status() -> dict:
    cfg = await _load()
    return {"configured": bool(cfg["token"]), "allowed": cfg["allowed"], "alerts": cfg["alerts"], "running": _state["running"],
            "username": _state["username"], "last_error": _state["last_error"]}


async def save(token: str, allowed_raw: str, alerts: bool = True) -> dict:
    cfg = await _load()
    token = (token or "").strip() or cfg["token"]
    if not token:
        raise TelegramError("Jeton du bot manquant (donné par @BotFather).")
    me = await _post(token, "getMe", {})
    try:
        allowed = sorted({int(x) for x in allowed_raw.replace(";", ",").replace(" ", ",").split(",") if x.strip()})
    except ValueError as exc:
        raise TelegramError("Identifiants invalides : des nombres séparés par des virgules.") from exc
    await _store({"token": token, "allowed": allowed, "offset": cfg["offset"], "alerts": alerts})
    _state["username"] = me.get("username", "")
    _state["last_error"] = ""
    return await status()


async def remove() -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM kv WHERE key='telegram'")
    _state.update(running=False, username="")


def _chunks(text: str) -> list[str]:
    text = text.strip() or "(réponse vide)"
    return [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)]


async def _send(token: str, chat_id: int, text: str) -> None:
    for part in _chunks(text):
        await _post(token, "sendMessage", {"chat_id": chat_id, "text": part})


async def notify(text: str) -> dict:
    """Envoie un message à chaque discussion autorisée (donc à l'utilisateur seulement)."""
    cfg = await _load()
    if not cfg["token"] or not cfg["allowed"]:
        raise TelegramError("Telegram n'est pas configuré (Paramètres › Telegram).")
    for chat_id in cfg["allowed"]:
        await _send(cfg["token"], chat_id, text)
    return {"sent_to": len(cfg["allowed"])}


async def envoyer_fichier(chemin: str, legende: str = "") -> dict:
    """Envoie un fichier produit par EVA (PDF du briefing, document…) aux discussions autorisées. Seulement dans le workspace."""
    from pathlib import Path
    cfg = await _load()
    if not cfg["token"] or not cfg["allowed"]:
        raise TelegramError("Telegram n'est pas configuré (Paramètres › Telegram).")
    racine = Path(_workspace or ".").resolve()
    p = (racine / chemin).resolve()
    if racine not in p.parents or not p.is_file():
        raise TelegramError(f"Fichier introuvable : {chemin}")
    if p.stat().st_size > 45 * 1024 * 1024:
        raise TelegramError("Fichier trop gros pour Telegram (50 Mo au plus).")
    for chat_id in cfg["allowed"]:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(f"https://api.telegram.org/bot{cfg['token']}/sendDocument",
                                      data={"chat_id": str(chat_id), "caption": (legende or "")[:1000]},
                                      files={"document": (p.name, p.read_bytes())})
            if not r.json().get("ok"):
                raise TelegramError(r.json().get("description") or "Envoi refusé.")
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(f"Telegram injoignable : {exc}") from exc
    return {"sent_to": len(cfg["allowed"]), "fichier": p.name}


_recent_alerts: dict[str, float] = {}


async def push_proactive(message: dict) -> None:
    """Relaie une alerte proactive (monitor, agent planifié) sur Telegram ; ignore les doublons récents."""
    import time
    cfg = await _load()
    if not cfg["token"] or not cfg["allowed"] or not cfg.get("alerts", True):
        return
    text = str(message.get("text", "")).strip()
    if not text:
        return
    now = time.time()
    for k in [k for k, v in _recent_alerts.items() if now - v > 900]:
        del _recent_alerts[k]
    if text in _recent_alerts:
        return
    _recent_alerts[text] = now
    await notify(text[:3500])


async def _turn(token: str, chat_id: int, text: str) -> None:
    from .harness.loop import run_harness  # import tardif : évite un import circulaire avec le registre
    from .harness.selection import SubsetRegistry, select_tool_names
    session_id = f"telegram-{chat_id}"
    lock = _locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        try:
            await ensure_session(session_id, "Telegram")
            past = await load_recent(session_id)
            system = skills_mod.system_prompt_with_skills(settings.system_prompt, _workspace)
            history = [{"role": "system", "content": system}] + past + [{"role": "user", "content": text}]
            await save_message(session_id, "user", text)
            choice = await model_router.select(text)
            trace = TraceRecorder("chat", session_id=session_id, label=text, model=choice["model"])
            recent_user = [text] + [m["content"] for m in reversed(past) if m["role"] == "user"][:2]
            reg = SubsetRegistry(_registry, select_tool_names(recent_user, _registry.names()))
            errors: list[str] = []

            async def send_event(ev: dict) -> None:
                if ev.get("type") == "error":
                    errors.append(ev.get("message", "erreur"))

            async def confirm(tool: str, args: dict) -> bool:
                fut = asyncio.get_running_loop().create_future()
                _pending[chat_id] = fut
                from . import autorisations
                await _send(token, chat_id, f"⚠️ {autorisations.phrase_accord(tool, args)}\nRéponds « oui » ou « non » (2 min).")
                try:
                    return await asyncio.wait_for(fut, CONFIRM_TIMEOUT)
                except asyncio.TimeoutError:
                    await _send(token, chat_id, "Pas de réponse : action refusée.")
                    return False
                finally:
                    _pending.pop(chat_id, None)

            await _post(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
            final = await run_harness(history, reg, send_event, confirm, trace=trace,
                                      model=choice["model"], tools_enabled=choice["tools"])
            if final is None:
                await trace.save(ok=False, error="Erreur du modèle ou d'Ollama")
                await _send(token, chat_id, "Erreur : " + (errors[-1] if errors else "le modèle n'a pas répondu."))
                return
            trace_id = await trace.save(ok=True)
            await save_message(session_id, "assistant", final, trace_id=trace_id)
            await touch_session(session_id)
            await _send(token, chat_id, final)
        except Exception as exc:  # une erreur ne doit jamais tuer la boucle
            logger.exception("Tour Telegram en échec")
            try:
                await _send(token, chat_id, f"Erreur interne : {exc}")
            except Exception:
                pass


async def handle_update(cfg: dict, upd: dict) -> None:
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not text or chat_id is None:
        return
    token = cfg["token"]
    if chat.get("type") != "private" or chat_id not in cfg["allowed"]:
        if chat.get("type") == "private":
            await _send(token, chat_id, f"Accès non autorisé. Ton identifiant : {chat_id}\n"
                                        "Ajoute-le dans EVA › Paramètres › Telegram.")
        return
    fut = _pending.get(chat_id)
    if fut and not fut.done() and text.lower() in YES | NO:
        fut.set_result(text.lower() in YES)
        return
    if text.startswith("/start"):
        await _send(token, chat_id, "EVA à ton service. Écris-moi comme dans l'interface web. /nouveau pour repartir de zéro.")
        return
    if text.startswith("/nouveau"):
        await effacer_session(f"telegram-{chat_id}")
        await _send(token, chat_id, "Nouvelle conversation.")
        return
    asyncio.create_task(_turn(token, chat_id, text))


async def run_forever() -> None:
    """Boucle de réception ; reste inactive tant qu'aucun jeton n'est enregistré."""
    while True:
        try:
            cfg = await _load()
            if not cfg["token"]:
                _state["running"] = False
                await asyncio.sleep(5)
                continue
            _state["running"] = True
            updates = await _post(cfg["token"], "getUpdates",
                                  {"offset": cfg["offset"], "timeout": 20, "allowed_updates": ["message"]}, timeout=35.0)
            _state["last_error"] = ""
            for upd in updates:
                cfg["offset"] = upd["update_id"] + 1
                await handle_update(cfg, upd)
            if updates:
                await _store(cfg)
            else:
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _state["last_error"] = str(exc)[:200]
            logger.warning("Telegram : %s", exc)
            await asyncio.sleep(10)
