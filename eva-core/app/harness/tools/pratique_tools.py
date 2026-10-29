"""Infos pratiques du foyer (app/pratique.py) : poubelles, vacances et jours fériés, carburants, éphéméride, actualités."""
from typing import Any

from ... import pratique
from ..permissions import Permission
from .base import Tool


async def _sur(coro) -> dict:
    try:
        return await coro
    except pratique.PratiqueError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 — service en ligne injoignable
        return {"error": f"Service injoignable pour l'instant ({type(e).__name__})."}


class PoubellesTool(Tool):
    name = "pratique_poubelles"
    description = ("Quelle poubelle sortir et quand, d'après le calendrier de ramassage réglé : « quelle poubelle je sors ce soir ? », "
                   "« c'est quand le verre ? », « on sort les poubelles demain ? ». Réponds avec la phrase renvoyée.")
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        return await _sur(pratique.poubelles())


class VacancesTool(Tool):
    name = "pratique_vacances"
    description = ("Vacances scolaires (en cours, prochaines, dates) et prochains jours fériés en France, d'après l'Éducation "
                   "nationale : « c'est quand les prochaines vacances ? », « le prochain jour férié ? », « quand finissent les vacances ? ». "
                   "zone = A, B, C ou Corse (vide = celle du foyer).")
    parameters = {"type": "object", "properties": {"zone": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, zone: str = "", **_: Any) -> dict:
        return await _sur(pratique.vacances(zone or None))


class CarburantsTool(Tool):
    name = "pratique_carburants"
    description = ("Prix des carburants dans les stations d'une commune ou d'un code postal (flux officiel), la moins chère d'abord : "
                   "« combien coûte le gazole ? », « où est l'essence la moins chère à Lons ? ». lieu = commune ou code postal "
                   "(vide = celui du foyer) ; carburant = gazole, e10, sp95, sp98, e85 ou gplc (vide = celui du foyer).")
    parameters = {"type": "object", "properties": {"lieu": {"type": "string"}, "carburant": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, lieu: str = "", carburant: str = "", **_: Any) -> dict:
        return await _sur(pratique.carburants(lieu, carburant))


class EphemerideTool(Tool):
    name = "pratique_ephemeride"
    description = ("Éphéméride : ce qui s'est passé un jour comme aujourd'hui les années passées (Wikipédia) : « que s'est-il passé "
                   "un jour comme aujourd'hui ? », « l'éphéméride du jour ». jour = AAAA-MM-JJ (vide = aujourd'hui).")
    parameters = {"type": "object", "properties": {"jour": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, jour: str = "", **_: Any) -> dict:
        return await _sur(pratique.ephemeride(jour))


class ActuTool(Tool):
    name = "pratique_actu"
    description = ("Titres de l'actualité du jour, lus dans le flux RSS du journal réglé (franceinfo par défaut) : « quoi de neuf "
                   "dans l'actualité ? », « les titres du jour », « les infos ». Plus fiable et plus rapide qu'une recherche web "
                   "pour les grands titres. url = autre flux RSS (facultatif).")
    parameters = {"type": "object", "properties": {"nombre": {"type": "integer"}, "url": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, nombre: int = 0, url: str = "", **_: Any) -> dict:
        return await _sur(pratique.actu(url, nombre))


def all_tools() -> list[Tool]:
    return [PoubellesTool(), VacancesTool(), CarburantsTool(), EphemerideTool(), ActuTool()]
