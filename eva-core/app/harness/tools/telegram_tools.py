from typing import Any

from ... import telegram as tg
from ..permissions import Permission
from .base import Tool


class TelegramNotifyTool(Tool):
    name = "telegram_notify"
    description = (
        "Envoie un message court sur le Telegram de l'utilisateur (alerte, résumé, rappel). "
        "Ne sert qu'à le prévenir lui : le message ne part que vers ses propres discussions autorisées."
    )
    parameters = {"type": "object", "properties": {
        "text": {"type": "string", "description": "Message à envoyer"},
        "fichier": {"type": "string", "description": "Facultatif : chemin d'un fichier créé par EVA à joindre (ex. exports/Briefing.pdf)"}},
        "required": ["text"]}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, text: str = "", fichier: str = "", **_: Any) -> dict:
        if not str(text).strip():
            return {"error": "Message vide."}
        try:
            if str(fichier or "").strip():
                return await tg.envoyer_fichier(str(fichier).strip(), str(text)[:1000])
            return await tg.notify(str(text)[:3500])
        except tg.TelegramError as exc:
            return {"error": str(exc)}
