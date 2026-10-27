from typing import Any

from ..permissions import Permission
from ... import aiserver
from .base import Tool


class AiServerStatsTool(Tool):
    name = "ai_server_stats"
    description = ("État du SERVEUR IA (la machine qui fait tourner les modèles) : processeur, mémoire, carte graphique (usage, VRAM, température), disques, "
                   "services et consommation électrique. À utiliser pour « comment va le serveur IA / le GPU / la température ».")
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        s = await aiserver.stats()
        return {**s, "resume": aiserver.summary(s)}
