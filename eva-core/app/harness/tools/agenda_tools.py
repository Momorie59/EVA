"""Agendas iCal abonnés par la personne (lecture seule)."""
from typing import Any

from ... import agendas, profiles
from ..permissions import Permission
from .base import Tool


class AgendaIcsTool(Tool):
    name = "agenda_ics"
    description = ("Événements à venir des agendas iCal de la personne (vacances scolaires, agenda partagé Outlook/iCloud, club, école…). "
                   "jours = combien de jours à partir d'aujourd'hui ; agenda = nom d'un agenda précis (facultatif).")
    parameters = {"type": "object", "properties": {"jours": {"type": "integer"}, "agenda": {"type": "string"}}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, jours: int = 7, agenda: str = "", **_: Any) -> dict:
        try:
            return await agendas.a_venir(profiles.user_var.get() or "", jours, str(agenda or ""))
        except agendas.AgendaError as exc:
            return {"error": str(exc)}
