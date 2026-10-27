"""Confier une longue tâche à EVA en fond : la conversation reste libre, le résultat arrive quand c'est fini."""
from typing import Any

from ... import profiles, taches_fond
from .. import contexte
from ..permissions import Permission
from .base import Tool


class TacheDeFondTool(Tool):
    name = "tache_de_fond"
    description = (
        "Lance une LONGUE tâche en fond (recherche approfondie + document, comparatif, analyse de plusieurs fichiers…) quand la personne "
        "le demande (« en fond », « préviens-moi quand c'est fini », « prends ton temps ») ou quand la tâche prendra plusieurs minutes. "
        "Écris dans `consigne` TOUT ce qu'il faut savoir (la tâche travaille seule, sans voir cette conversation). Réponds ensuite en une "
        "phrase que c'est lancé."
    )
    parameters = {"type": "object", "properties": {
        "titre": {"type": "string", "description": "Titre court (ex. Comparatif des pompes à chaleur)"},
        "consigne": {"type": "string", "description": "Description complète et autonome de la tâche et du résultat attendu (format de fichier…)"}},
        "required": ["consigne"]}
    permission = Permission.AUTO

    async def execute(self, titre: str = "", consigne: str = "", **_: Any) -> dict:
        try:
            t = await taches_fond.lancer(str(titre or ""), str(consigne or ""), profiles.user_var.get() or "", profiles.role_var.get(),
                                         contexte.session.get())
        except (ValueError, RuntimeError) as exc:
            return {"error": str(exc)}
        return {"ok": True, **t, "consigne": "Dis en une phrase que c'est lancé en fond et que le résultat arrivera ici (et en notification)."}
