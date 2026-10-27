"""Question à choix : EVA propose des boutons cliquables quand une précision change vraiment ce qu'elle va faire."""
from typing import Any

from .. import contexte
from ..permissions import Permission
from .base import Tool


class PoserQuestionTool(Tool):
    name = "poser_question"
    description = (
        "Pose UNE question à la personne avec 2 à 6 choix cliquables, et attend sa réponse. À utiliser seulement quand la demande est "
        "ambiguë et qu'une mauvaise supposition coûterait cher (format d'un document, destinataire, période…), jamais pour bavarder "
        "ni pour demander « je continue ? ». Elle peut aussi répondre librement."
    )
    parameters = {"type": "object", "properties": {
        "question": {"type": "string", "description": "Question courte"},
        "choix": {"type": "array", "items": {"type": "string"}, "description": "2 à 6 réponses possibles, courtes"},
        "plusieurs": {"type": "boolean", "description": "true si plusieurs réponses peuvent être cochées"}},
        "required": ["question", "choix"]}
    permission = Permission.AUTO

    async def execute(self, question: str = "", choix: list | None = None, plusieurs: bool = False, **_: Any) -> dict:
        choix = [str(c).strip()[:80] for c in (choix or []) if str(c).strip()][:6]
        question = str(question or "").strip()[:300]
        if not question or len(choix) < 2:
            return {"error": "Il faut une question et au moins 2 choix."}
        demander = contexte.demander.get()
        if demander is None:
            return {"error": "Pas de boutons ici (voix, Telegram, satellite) : pose la question en une phrase dans ta réponse, avec les choix."}
        rep = await demander(question, choix, bool(plusieurs))
        if not rep:
            return {"error": "Pas de réponse : continue avec le choix le plus raisonnable et dis lequel tu as pris."}
        return {"reponse": rep if plusieurs else rep[0], "consigne": "Continue la tâche avec cette réponse, sans reposer la question."}
