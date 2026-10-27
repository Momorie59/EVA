import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("eva-core.broker")

DISCONNECT_SENTINEL = {"type": "__disconnect__"}


class MessageBroker:
    """Lit le WebSocket en continu dans une tâche unique et distribue les
    messages via une queue. Sans ça, confirm_gate() et la boucle principale
    se disputeraient receive_text() et un message reçu pendant une
    confirmation en attente serait perdu."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.arret = asyncio.Event()          # bouton « Arrêter » : traité tout de suite, même au milieu d'une réponse
        self._task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        try:
            while True:
                raw = await self.websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("type") == "stop":
                    self.arret.set()
                    continue
                await self.queue.put(payload)
        except WebSocketDisconnect:
            await self.queue.put(DISCONNECT_SENTINEL)
        except Exception:  # noqa: BLE001
            logger.exception("Erreur dans le lecteur WebSocket")
            await self.queue.put(DISCONNECT_SENTINEL)

    async def get(self) -> dict:
        return await self.queue.get()

    def requeue(self, payload: dict) -> None:
        """Remet un message de côté (reçu hors contexte, ex: pendant une
        confirmation) à la disposition de la boucle principale."""
        self.queue.put_nowait(payload)

    def close(self) -> None:
        self._task.cancel()
