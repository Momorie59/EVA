from typing import Any

from ... import docs
from ..permissions import Permission
from .base import Tool


MIN_SCORE = 0.6     # en dessous, l'extrait n'a pas de rapport avec la question : mieux vaut ne rien montrer que polluer la réponse


class DocsSearchTool(Tool):
    name = "docs_search"
    description = (
        "Recherche dans les documents personnels indexés de l'utilisateur (workspace, dossiers partagés) et dans "
        "ses anciennes conversations. Uniquement pour retrouver SES informations ; "
        "pour une question générale ou d'actualité, utilise web_search."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Ce que tu cherches, en langage naturel"},
            "limit": {"type": "integer", "description": "Nombre de passages (1 à 10, défaut 5)"},
        },
        "required": ["query"],
    }
    permission = Permission.AUTO

    async def execute(self, query: str = "", limit: int = 5, **_: Any) -> dict:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        try:
            hits = await docs.search(query, min(max(limit, 1), 10))
        except docs.DocsError as exc:
            return {"error": str(exc)}
        hits = [h for h in hits if float(h.get("score") or 0) >= MIN_SCORE]
        if not hits:
            return {"results": [], "note": "Aucun passage pertinent dans les documents de l'utilisateur. Si la question est générale, utilise web_search."}
        return {"results": [
            {"source": h["source"], "score": h["score"], "extrait": h["content"][:700]} for h in hits
        ]}
