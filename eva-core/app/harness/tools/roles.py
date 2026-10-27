from pathlib import Path
from typing import Any, Awaitable, Callable

from ... import skills as sk
from ..permissions import Permission
from .base import Tool

_runner: Callable[[dict, str], Awaitable[dict]] | None = None


def set_runner(fn) -> None:
    global _runner
    _runner = fn


class RoleRunTool(Tool):
    name = "role_run"
    description = (
        "Confie une sous-tâche à un assistant spécialisé installé depuis un dépôt d'agents (relecteur de code, sécurité, architecte…). "
        "Il travaille seul, en lecture seule (fichiers et documents d'EVA, web si son rôle le prévoit), puis renvoie son analyse. "
        "Sans le paramètre role, renvoie la liste des rôles disponibles. Donne une tâche complète : l'assistant ne voit pas la conversation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "description": "Nom du rôle (vide : liste des rôles)"},
            "task": {"type": "string", "description": "La sous-tâche, formulée de façon autonome (chemins de fichiers à relire compris)"},
        },
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, role: str = "", task: str = "", **_: Any) -> dict:
        roles = {r["name"]: r for r in sk.list_roles(self.root)}
        if not role:
            return {"roles": [{"name": n, "description": r["description"][:160]} for n, r in roles.items()]
                    or "Aucun rôle installé : Skills › Parcourir un dépôt GitHub › dossier agents."}
        r = roles.get(sk.slugify(role))
        if not r:
            return {"error": f"Rôle inconnu : {role}. Rôles : {', '.join(roles) or 'aucun installé'}"}
        if not task.strip():
            return {"error": "Tâche vide."}
        if _runner is None:
            return {"error": "Rôles indisponibles."}
        return await _runner(r, task.strip())
