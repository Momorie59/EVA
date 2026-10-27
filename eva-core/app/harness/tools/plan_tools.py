"""Plan de travail visible : pour une tâche en plusieurs étapes, EVA les annonce puis les coche au fur et à mesure."""
from typing import Any

from ... import plans
from .. import contexte
from ..permissions import Permission
from .base import Tool


class PlanTachesTool(Tool):
    name = "plan_taches"
    description = (
        "Plan de travail affiché à la personne pour une tâche en PLUSIEURS étapes (recherche + document, analyse de fichiers, projet…). "
        "Au début : etapes = [« Chercher les prix », « Comparer », « Faire le tableau Excel », « Vérifier »]. Ensuite, à chaque avancée : "
        "maj = [{n: 1, etat: 'fait'}, {n: 2, etat: 'en_cours'}]. La dernière étape est toujours une vérification (relire, recompter, "
        "rouvrir le fichier). Inutile pour une question simple."
    )
    parameters = {"type": "object", "properties": {
        "titre": {"type": "string"},
        "etapes": {"type": "array", "items": {"type": "string"}, "description": "Liste des étapes (crée ou remplace le plan)"},
        "maj": {"type": "array", "items": {"type": "object", "properties": {"n": {"type": "integer"}, "etat": {"type": "string", "enum": list(plans.ETATS)}}},
                "description": "Étapes à mettre à jour (n commence à 1)"},
        "effacer": {"type": "boolean"}}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, titre: str = "", etapes: list | None = None, maj: list | None = None, effacer: bool = False, **_: Any) -> dict:
        session = contexte.session.get()
        if not session:
            return {"error": "Pas de conversation : fais simplement les étapes une par une."}
        try:
            plan = await plans.mettre_a_jour(session, str(titre or ""), etapes, maj, bool(effacer))
        except ValueError as exc:
            return {"error": str(exc)}
        envoyer = contexte.envoyer.get()
        if envoyer:
            await envoyer({"type": "plan", "plan": plan})
        if plan is None:
            return {"ok": True, "plan": None}
        reste = plans.restantes(plan)
        return {"ok": True, "plan": [f"{i}. [{e['etat']}] {e['titre']}" for i, e in enumerate(plan["etapes"], 1)],
                "consigne": "Fais maintenant l'étape suivante." if reste else "Tout est fait : conclus en résumant le résultat."}
