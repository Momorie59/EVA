"""Tours de conversation avec une image : photo à décrire (modèle vision), image à créer ou à retoucher, post-its.

Sortis de main.py pour l'alléger ; main.py les importe."""
import asyncio
import logging
import contextvars
from pathlib import Path

from fastapi import WebSocket

from .config import settings
from . import images as images_mod, imageedit as imageedit_mod
from .memory import save_message
from .ollama_client import OllamaError, stream_chat
from . import notes as notes_mod
from . import profiles as profiles_mod
from . import router as model_router
from . import knowledge as knowledge_mod
from .sessions import ensure_session as _ensure_session, touch_session


logger = logging.getLogger("eva-core")
workspace_root = Path(settings.workspace_root)
_ws_owner: contextvars.ContextVar[str] = contextvars.ContextVar("ws_owner", default="")


async def ensure_session(session_id: str, first_text: str = "") -> None:
    """Crée la conversation au nom de l'utilisateur connecté (un utilisateur standard ne voit que les siennes)."""
    await _ensure_session(session_id, first_text, owner=_ws_owner.get())


async def _handle_vision(
    user_text: str, image_b64: str, history: list[dict], session_id: str, websocket: WebSocket
) -> None:
    """Traite un message avec image (photo caméra) comme un tour à part,
    avec le modèle vision (souvent différent du modèle à outils) — pas de
    Harness ici, une image ne se prête pas bien au tool-calling. On garde
    une trace textuelle dans l'historique plutôt que de réinjecter l'image
    à chaque futur appel du modèle à outils."""
    caption = user_text or "Que vois-tu sur cette image ?"
    vision_messages = [
        {"role": "system", "content": settings.system_prompt},
        {"role": "user", "content": caption, "images": [image_b64]},
    ]

    choice = await model_router.select(user_text, has_image=True)
    await websocket.send_json({"type": "model", "model": choice["model"], "category": choice["category"], "reason": choice["reason"]})
    await websocket.send_json({"type": "state", "state": "thinking"})
    full_reply = ""
    first_chunk = True
    try:
        async for chunk in stream_chat(vision_messages, model=choice["model"]):
            if first_chunk:
                await websocket.send_json({"type": "state", "state": "speaking"})
                first_chunk = False
            full_reply += chunk
            await websocket.send_json({"type": "token", "text": chunk})
    except OllamaError as exc:
        await websocket.send_json({"type": "state", "state": "error"})
        await websocket.send_json({"type": "error", "message": str(exc)})
        return

    user_record = f"{caption} [a envoyé une photo]"
    history.append({"role": "user", "content": user_record})
    history.append({"role": "assistant", "content": full_reply})
    await save_message(session_id, "user", user_record)
    await save_message(session_id, "assistant", full_reply)
    await touch_session(session_id)
    try:                                                   # EVA garde la photo et ce qu'elle en a dit : on pourra l'interroger plus tard
        if await asyncio.to_thread(knowledge_mod.remember_photo, workspace_root, image_b64, caption, full_reply, profiles_mod.user_var.get() or ""):
            knowledge_mod.schedule_reindex()
    except OSError:
        logger.warning("Photo non conservée", exc_info=True)

    await websocket.send_json({"type": "state", "state": "idle"})
    await websocket.send_json({"type": "done"})


async def _apply_note_command(cmd: dict, send_event) -> str:
    """Exécute une commande de post-it reconnue, SANS passer par le modèle, et renvoie la phrase de réponse."""
    action = cmd["action"]
    try:
        if action == "create":
            n = await notes_mod.create(cmd["text"], cmd.get("color"), by="eva")
            return f"C'est fait, post-it {n['color']} collé : {n['text']}."
        if action == "clear_all":
            k = await notes_mod.clear(False)
            return "Aucun post-it à ranger." if not k else f"{k} post-it rangé{'s' if k > 1 else ''} dans la corbeille."
        if action == "clear_done":
            k = await notes_mod.clear(True)
            return "La corbeille est déjà vide." if not k else f"Corbeille vidée : {k} post-it supprimé{'s' if k > 1 else ''}."
        if action in ("show", "hide"):
            await send_event({"type": "notes_visibility", "visible": action == "show"})
            return "Post-it affichés." if action == "show" else "Post-it masqués."
        if action == "ask":
            return "Que dois-je écrire sur le post-it ?"
        if action == "list":
            items = await notes_mod.list_notes(False)
            if not items:
                return "Il n'y a aucun post-it à l'écran."
            return "Post-it à l'écran : " + " ; ".join(f"{n['text']}{' (fait)' if n['done'] else ''}" for n in items[:15]) + "."
    except ValueError as exc:
        return f"Je n'ai pas pu créer le post-it : {exc}"
    return ""


async def _handle_image_request(subject: str, user_text: str, history: list[dict], session_id: str, send_event) -> bytes | None:
    """Demande de création d'image : envoyée au serveur d'images (sans passer par le modèle de langage)."""
    await ensure_session(session_id, user_text)
    await save_message(session_id, "user", user_text)
    history.append({"role": "user", "content": user_text})
    reply = ""
    saved_name = ""
    image_event = None
    result_png: bytes | None = None
    cfg = await images_mod.get_config()
    if not cfg["url"]:
        reply = images_mod.NOT_CONFIGURED
    else:
        await send_event({"type": "state", "state": "acting"})
        await send_event({"type": "tool_call", "name": "image_generate", "args": {"prompt": subject}})
        try:
            final = await images_mod.enhance(subject) if cfg.get("enhance", True) else subject
            png = await images_mod.generate(final, cfg)
            result_png = png
            saved_name = ""
            try:
                saved_name = images_mod.save(png, workspace_root, subject, final).name
            except OSError:
                logger.warning("Image générée non sauvegardée", exc_info=True)
            image_event = {"type": "image", "name": saved_name, "image": images_mod.data_uri(png), "prompt": subject}
            reply = f"Voilà, j'ai créé l'image : {subject}."
        except images_mod.ImageError as exc:
            reply = f"Je n'ai pas pu créer l'image : {exc}"
    await send_event({"type": "state", "state": "speaking"})
    await send_event({"type": "token", "text": reply})
    if image_event:
        await send_event(image_event)                      # l'image s'affiche dans la conversation, sous la réponse
    history.append({"role": "assistant", "content": reply})
    mid = await save_message(session_id, "assistant", images_mod.with_mark(reply, saved_name) if saved_name else reply)
    if mid:
        await send_event({"type": "saved", "message_id": mid, "trace_id": None})
    await touch_session(session_id)
    await send_event({"type": "state", "state": "idle"})
    await send_event({"type": "done"})
    return result_png


async def _handle_image_edit(pl: dict, src_png: bytes, user_text: str, history: list[dict], session_id: str, send_event) -> bytes | None:
    """Modification d'une image existante (retouches classiques et/ou IA), sans passer par le modèle de langage."""
    await ensure_session(session_id, user_text)
    await save_message(session_id, "user", user_text)
    history.append({"role": "user", "content": user_text})
    reply, saved_name, image_event, out = "", "", None, None
    await send_event({"type": "state", "state": "acting"})
    await send_event({"type": "tool_call", "name": "image_edit", "args": {"demande": user_text}})
    try:
        out, summary = await imageedit_mod.run(src_png, pl, user_text)
        try:
            saved_name = images_mod.save(out, workspace_root, user_text, summary, kind="edit").name
        except OSError:
            logger.warning("Image modifiée non sauvegardée", exc_info=True)
        image_event = {"type": "image", "name": saved_name, "image": images_mod.data_uri(out), "prompt": user_text}
        reply = f"Voilà, c'est fait : {summary}."
    except images_mod.ImageError as exc:
        reply = f"Je n'ai pas pu modifier l'image : {exc}"
    await send_event({"type": "state", "state": "speaking"})
    await send_event({"type": "token", "text": reply})
    if image_event:
        await send_event(image_event)
    history.append({"role": "assistant", "content": reply})
    mid = await save_message(session_id, "assistant", images_mod.with_mark(reply, saved_name) if saved_name else reply)
    if mid:
        await send_event({"type": "saved", "message_id": mid, "trace_id": None})
    await touch_session(session_id)
    await send_event({"type": "state", "state": "idle"})
    await send_event({"type": "done"})
    return out


async def _handle_image_note(user_text: str, history: list[dict], session_id: str, send_event) -> None:
    """Demande de modification sans aucune image sous la main : on explique comment faire."""
    await ensure_session(session_id, user_text)
    await save_message(session_id, "user", user_text)
    history.append({"role": "user", "content": user_text})
    reply = "Je n'ai pas d'image à modifier. Joins une photo à ton message (ou crée d'abord une image), puis redemande-moi."
    await send_event({"type": "token", "text": reply})
    history.append({"role": "assistant", "content": reply})
    mid = await save_message(session_id, "assistant", reply)
    if mid:
        await send_event({"type": "saved", "message_id": mid, "trace_id": None})
    await touch_session(session_id)
    await send_event({"type": "state", "state": "idle"})
    await send_event({"type": "done"})
