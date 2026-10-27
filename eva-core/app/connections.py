import logging

from fastapi import WebSocket

logger = logging.getLogger("eva-core.connections")


class ConnectionManager:
    """Suit les WebSocket ouverts par session, pour permettre à une tâche
    de fond (un Monitor) d'envoyer un message sans qu'il y ait eu de
    question de l'utilisateur juste avant — le coeur du comportement
    proactif façon Jarvis."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self.proactive_hooks: list = []

    def register(self, session_id: str, websocket: WebSocket) -> None:
        self._connections.setdefault(session_id, set()).add(websocket)

    def unregister(self, session_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(session_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                del self._connections[session_id]

    async def _hooks(self, message: dict) -> None:
        # Les messages proactifs sont aussi relayés ailleurs (Telegram), jamais au prix d'une erreur ici.
        if message.get("type") != "proactive":
            return
        for hook in self.proactive_hooks:
            try:
                await hook(message)
            except Exception:  # noqa: BLE001
                logger.warning("Relais proactif en échec", exc_info=True)

    async def broadcast(self, session_id: str, message: dict) -> None:
        await self._deliver(session_id, message)
        await self._hooks(message)

    async def _deliver(self, session_id: str, message: dict) -> None:
        sockets = list(self._connections.get(session_id, ()))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — une connexion morte ne doit pas casser les autres
                logger.warning("Échec d'envoi proactif à une connexion, on l'ignore")


    async def broadcast_all(self, message: dict) -> None:
        for session_id in list(self._connections.keys()):
            await self._deliver(session_id, message)
        await self._hooks(message)


connection_manager = ConnectionManager()
