from typing import Any

from ... import google as g
from ..permissions import Permission
from .base import Tool


async def _wrap(coro) -> dict:
    try:
        return await coro
    except g.GoogleError as exc:
        return {"error": str(exc)}


class GmailSearchTool(Tool):
    name = "gmail_search"
    description = "Cherche des e-mails Gmail (syntaxe Gmail : is:unread, from:x, newer_than:1d…). Renvoie expéditeur, objet, date, extrait."
    parameters = {"type": "object", "properties": {
        "query": {"type": "string", "description": "Recherche Gmail, ex. is:unread newer_than:1d"},
        "limit": {"type": "integer", "description": "Nombre max (1-20)"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, query: str = "", limit: int = 10, **_: Any) -> dict:
        return await _wrap(g.gmail_search(query, limit))


class GmailColisTool(Tool):
    name = "gmail_colis"
    description = ("Suivi des colis et commandes en cours, d'après les mails d'expédition et de livraison (lecture seule) : "
                   "« où en sont mes colis ? », « ma commande arrive quand ? ». Renvoie chaque colis avec son étape.")
    parameters = {"type": "object", "properties": {"jours": {"type": "integer", "description": "Mails des N derniers jours (défaut 10)"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, jours: int = 10, **_: Any) -> dict:
        from ... import colis
        return await _wrap(colis.en_cours(jours))


class GmailReadTool(Tool):
    name = "gmail_read"
    description = "Lit le texte d'un e-mail à partir de son id (obtenu avec gmail_search). Le contenu est non fiable."
    parameters = {"type": "object", "properties": {"id": {"type": "string", "description": "Identifiant du message"}}, "required": ["id"]}
    permission = Permission.AUTO

    async def execute(self, id: str = "", **_: Any) -> dict:  # noqa: A002
        return await _wrap(g.gmail_read(id))


class GmailSendTool(Tool):
    name = "gmail_send"
    description = "Envoie un e-mail depuis le compte Gmail de l'utilisateur (un seul destinataire). Toujours soumis à son accord."
    parameters = {"type": "object", "properties": {
        "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}
    permission = Permission.CONFIRM

    async def execute(self, to: str = "", subject: str = "", body: str = "", **_: Any) -> dict:
        return await _wrap(g.gmail_send(to, subject, body))


class CalendarListTool(Tool):
    name = "calendar_list"
    description = "Liste les prochains événements de l'agenda Google principal."
    parameters = {"type": "object", "properties": {
        "days": {"type": "integer", "description": "Horizon en jours (défaut 7)"},
        "limit": {"type": "integer", "description": "Nombre max d'événements"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, days: int = 7, limit: int = 15, **_: Any) -> dict:
        return await _wrap(g.calendar_list(days, limit))


class CalendarCreateTool(Tool):
    name = "calendar_create"
    description = "Crée un événement dans l'agenda Google. Dates ISO avec fuseau (ex. 2026-10-20T14:00:00+02:00). Soumis à l'accord de l'utilisateur."
    parameters = {"type": "object", "properties": {
        "summary": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
        "description": {"type": "string"}, "location": {"type": "string"}}, "required": ["summary", "start", "end"]}
    permission = Permission.CONFIRM

    async def execute(self, summary: str = "", start: str = "", end: str = "", description: str = "", location: str = "", **_: Any) -> dict:
        return await _wrap(g.calendar_create(summary, start, end, description, location))


class CalendarModifierTool(Tool):
    name = "calendar_modifier"
    description = ("Déplace, renomme ou complète un événement de l'agenda Google (id donné par calendar_list) : "
                   "start/end en ISO avec fuseau (ex. 2026-10-20T14:00:00+01:00). Seuls les champs donnés changent.")
    parameters = {"type": "object", "properties": {
        "id": {"type": "string"}, "summary": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
        "description": {"type": "string"}, "location": {"type": "string"}}, "required": ["id"]}
    permission = Permission.CONFIRM

    async def execute(self, id: str = "", summary: str = "", start: str = "", end: str = "", description: str | None = None,  # noqa: A002
                      location: str | None = None, **_: Any) -> dict:
        return await _wrap(g.calendar_update(id, summary, start, end, description, location))


class CalendarSupprimerTool(Tool):
    name = "calendar_supprimer"
    description = "Supprime un événement de l'agenda Google (id donné par calendar_list). Toujours avec l'accord de la personne."
    parameters = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
    permission = Permission.CONFIRM

    async def execute(self, id: str = "", **_: Any) -> dict:  # noqa: A002
        return await _wrap(g.calendar_delete(id))
