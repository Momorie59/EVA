from typing import Any, Awaitable, Callable

from ..permissions import Permission
from .base import Tool

ROLES = {
    "chercheur": "recherche d'informations sur le web et dans les documents d'EVA",
    "analyste": "calculs, traitement de données et vérifications par du code Python exécuté en bac à sable",
    "systeme": "diagnostic du serveur : ressources, conteneurs Docker, dépôts Git, fichiers",
    "redacteur": "rédaction et mise en forme à partir d'éléments fournis (peut relire les fichiers du workspace)",
}

_runner: Callable[[str, str], Awaitable[dict]] | None = None


def set_runner(fn: Callable[[str, str], Awaitable[dict]]) -> None:
    global _runner
    _runner = fn


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "Confie une sous-tâche précise à un assistant spécialisé et récupère sa réponse. "
        "Rôles : " + " ; ".join(f"{k} ({v})" for k, v in ROLES.items()) + ". "
        "Donne une tâche autonome et complète : l'assistant ne voit pas la conversation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": list(ROLES), "description": "Spécialité de l'assistant"},
            "task": {"type": "string", "description": "La sous-tâche, formulée de façon autonome"},
        },
        "required": ["role", "task"],
    }
    permission = Permission.AUTO
    agents_only = True

    async def execute(self, role: str = "", task: str = "", **_: Any) -> dict:
        if _runner is None:
            return {"error": "Délégation indisponible."}
        if role not in ROLES:
            return {"error": f"Rôle inconnu : {role}. Rôles : {', '.join(ROLES)}"}
        if not task.strip():
            return {"error": "Tâche vide."}
        return await _runner(role, task.strip())
