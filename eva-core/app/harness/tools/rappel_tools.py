"""Outils « rappels et minuteurs » : EVA programme un rappel (une fois ou tous les jours / semaines), les liste, les annule."""
from typing import Any

from ... import profiles, rappels
from ..contexte import session as session_var
from ..permissions import Permission
from .base import Tool


class RappelCreerTool(Tool):
    name = "rappel_creer"
    description = ("Programme un rappel ou un minuteur : « rappelle-moi d'appeler le garage à 17 h », « minuteur 10 minutes », "
                   "« rappelle-moi tous les jours à 8 h de prendre mes médicaments ». quand = la phrase de la personne "
                   "(« dans 10 minutes », « à 17 h », « demain matin », « lundi à 9 h », « le 3 novembre à 14 h ») ou une date ISO. "
                   "Le rappel sonne dans l'interface, sur le satellite de la pièce et sur Telegram. piece = pour l'annoncer à voix haute "
                   "dans une pièce précise.")
    parameters = {"type": "object", "properties": {
        "texte": {"type": "string", "description": "Ce qu'il faut rappeler (« sortir le gâteau du four »)"},
        "quand": {"type": "string"},
        "recurrence": {"type": "string", "enum": ["", "jour", "semaine", "heure"], "description": "vide = une seule fois"},
        "piece": {"type": "string"}}, "required": ["texte", "quand"]}
    permission = Permission.AUTO

    async def execute(self, texte: str = "", quand: str = "", recurrence: str = "", piece: str = "", **_: Any) -> dict:
        try:
            r = await rappels.creer(profiles.user_var.get() or "", texte, quand, recurrence or "", session_var.get() or "", piece)
        except rappels.RappelError as e:
            return {"error": str(e)}
        rep = {"": "", "jour": " puis tous les jours", "semaine": " puis toutes les semaines", "heure": " puis toutes les heures"}[r["recurrence"]]
        return {"ok": True, "id": r["id"], "texte": r["texte"], "sonnera": r["quand_lisible"] + rep}


class RappelListerTool(Tool):
    name = "rappel_lister"
    description = "Liste les rappels et minuteurs en attente (« quels sont mes rappels ? »)."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        lst = await rappels.lister(profiles.user_var.get() or "")
        return {"rappels": [{"id": r["id"], "texte": r["texte"], "quand": r["quand_lisible"], "recurrence": r["recurrence"]} for r in lst]}


class RappelAnnulerTool(Tool):
    name = "rappel_annuler"
    description = "Annule un rappel ou un minuteur : par son numéro (rappel_lister) ou par des mots de son texte (« annule le rappel du garage »)."
    parameters = {"type": "object", "properties": {"id": {"type": "integer"}, "texte": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, id: int = 0, texte: str = "", **_: Any) -> dict:  # noqa: A002
        try:
            faits = await rappels.annuler(profiles.user_var.get() or "", id or None, texte)
        except rappels.RappelError as e:
            return {"error": str(e)}
        if not faits:
            return {"error": "Aucun rappel en attente ne correspond."}
        return {"ok": True, "annules": [f"{r['texte']} ({r['quand_lisible']})" for r in faits]}


def all_tools() -> list[Tool]:
    return [RappelCreerTool(), RappelListerTool(), RappelAnnulerTool()]
