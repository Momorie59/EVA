from abc import ABC, abstractmethod
from typing import Any

from ..permissions import Permission


class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema des arguments, format attendu par Ollama/OpenAI
    permission: Permission = Permission.AUTO
    # Outil réservé aux agents (invisible en conversation) / utilisable par un agent
    # sans humain malgré une permission CONFIRM (cas du bac à sable isolé).
    agents_only: bool = False
    agent_safe: bool = False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict:
        """Exécute l'outil et retourne un résultat sérialisable en JSON.

        Ne doit jamais lever d'exception pour un échec "normal" (fichier
        introuvable, etc.) — retourner {"error": "..."} à la place, pour que
        le modèle puisse réagir. Les exceptions sont réservées aux bugs.
        """

    def permission_for(self, args: dict) -> Permission:
        """Permission réellement appliquée pour CET appel précis. Par
        défaut, renvoie la permission statique de l'outil — un outil peut
        la surcharger pour décider en fonction des arguments (typiquement
        le chemin visé par une écriture)."""
        return self.permission

    def schema(self) -> dict:
        """Format attendu par l'API `tools` d'Ollama (compatible OpenAI)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
