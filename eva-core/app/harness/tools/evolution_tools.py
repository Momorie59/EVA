"""Outil « demande d'évolution » : EVA note ce qu'on lui demande et qu'elle ne sait pas encore faire (page Évolution)."""
from typing import Any

from ... import evolution_demandes, profiles
from ..permissions import Permission
from .base import Tool


class EvolutionDemanderTool(Tool):
    name = "evolution_demander"
    description = ("Note une demande d'évolution quand la personne demande quelque chose qu'aucun de tes outils (même combinés) ne permet : "
                   "« pouvoir réserver un restaurant », « lire mes SMS »… texte = ce qu'il faudrait savoir faire ; exemple = la demande "
                   "telle qu'elle a été formulée. Dis ensuite que c'est noté pour une prochaine version (page Évolution).")
    parameters = {"type": "object", "properties": {"texte": {"type": "string"}, "exemple": {"type": "string"}}, "required": ["texte"]}
    permission = Permission.AUTO

    async def execute(self, texte: str = "", exemple: str = "", **_: Any) -> dict:
        try:
            d = await evolution_demandes.ajouter(profiles.user_var.get() or "", texte, exemple)
        except ValueError as e:
            return {"error": str(e)}
        return {"ok": True, "note": d["texte"], "deja_demandee": d.get("fois", 1) > 1}
