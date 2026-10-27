"""OBS, Discord, Instagram, appels/SMS (Twilio). Lecture libre ; tout ce qui se voit de l'extérieur demande l'accord."""
from typing import Any

from ... import connecteurs as cx
from ..permissions import Permission
from .base import Tool


async def _sur(coro) -> dict:
    try:
        return await coro
    except cx.ConnecteurError as exc:
        return {"error": str(exc)}


class ObsEtatTool(Tool):
    name = "obs_etat"
    description = "État d'OBS Studio : live en cours ou non, enregistrement, scène affichée et liste des scènes."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        return await _sur(cx.obs_etat())


class ObsActionTool(Tool):
    name = "obs_action"
    description = ("Pilote OBS Studio : démarrer/arrêter le live ou l'enregistrement, pause, replay (sauver les dernières secondes), "
                   "changer de scène (action=scene + nom de la scène).")
    parameters = {"type": "object", "properties": {
        "action": {"type": "string", "enum": list(cx.OBS_ACTIONS)},
        "scene": {"type": "string", "description": "Nom de la scène (seulement pour action=scene)"}}, "required": ["action"]}
    permission = Permission.CONFIRM

    async def execute(self, action: str = "", scene: str = "", **_: Any) -> dict:
        return await _sur(cx.obs_action(str(action), str(scene or "")))


class DiscordEnvoyerTool(Tool):
    name = "discord_envoyer"
    description = "Publie un message dans un salon Discord relié (par son nom donné dans les réglages)."
    parameters = {"type": "object", "properties": {
        "salon": {"type": "string", "description": "Nom du salon tel qu'enregistré (vide s'il n'y en a qu'un)"},
        "message": {"type": "string"}}, "required": ["message"]}
    permission = Permission.CONFIRM

    async def execute(self, salon: str = "", message: str = "", **_: Any) -> dict:
        return await _sur(cx.discord_envoyer(str(salon or ""), str(message or "")))


class InstagramStatsTool(Tool):
    name = "instagram_stats"
    description = "Statistiques du compte Instagram relié : abonnés, publications, j'aime et commentaires des dernières publications."
    parameters = {"type": "object", "properties": {"nombre": {"type": "integer", "description": "Nombre de publications récentes (1-20)"}}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, nombre: int = 5, **_: Any) -> dict:
        return await _sur(cx.instagram_stats(nombre))


class AppelTelephoneTool(Tool):
    name = "appel_telephone"
    description = ("Appelle un contact de la liste d'appel : soit EVA lit un message (« appelle Maman pour lui dire que… »), soit "
                   "conversation=true pour une vraie conversation où EVA pose la question et écoute la réponse (« appelle Maman et "
                   "demande-lui si elle vient dimanche » : message = l'objectif) ; sms=true pour un SMS. Seulement les contacts "
                   "enregistrés par l'administrateur, jamais un numéro libre. Le compte rendu d'une conversation arrive ici à la fin.")
    parameters = {"type": "object", "properties": {
        "contact": {"type": "string", "description": "Nom du contact (ex. Maman)"},
        "message": {"type": "string", "description": "Ce qu'EVA dira (ou écrira), ou l'objectif de la conversation"},
        "conversation": {"type": "boolean", "description": "true = EVA converse et rapporte la réponse"},
        "sms": {"type": "boolean", "description": "true = SMS au lieu d'un appel"}}, "required": ["contact", "message"]}
    permission = Permission.CONFIRM

    async def execute(self, contact: str = "", message: str = "", sms: bool = False, conversation: bool = False, **_: Any) -> dict:
        if conversation and not sms:
            from ... import appels, profiles
            from .. import contexte
            r = await _sur(appels.lancer(str(contact or ""), str(message or ""), profiles.user_var.get() or "", contexte.session.get()))
            if "error" not in r:
                r["consigne"] = "Dis que l'appel est lancé et que le compte rendu arrivera ici à la fin."
            return r
        return await _sur(cx.twilio(str(contact or ""), str(message or ""), bool(sms)))
