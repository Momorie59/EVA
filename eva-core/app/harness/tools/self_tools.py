from typing import Any

from ... import self_mod
from ..permissions import Permission
from .base import Tool


class SelfReadTool(Tool):
    name = "self_read"
    description = (
        "Lit le code source d'EVA elle-même. Sans chemin : liste les fichiers (app/, skills/). "
        "Avec un chemin (ex: app/skills.py) : renvoie le contenu."
    )
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Chemin relatif, vide pour lister"}},
    }
    permission = Permission.AUTO

    async def execute(self, path: str = "", **_: Any) -> dict:
        try:
            if not (path or "").strip():
                return {"files": self_mod.list_tree()}
            self_mod._require_enabled()
            p = (path or "").strip().replace("\\", "/")
            if p.startswith("/") or ".." in p.split("/"):
                return {"error": "Chemin invalide."}
            text = self_mod.read_live(p)
            if text is None:
                return {"error": f"Fichier introuvable : {p}"}
            return {"path": p, "content": text[:20000], "truncated": len(text) > 20000}
        except self_mod.SelfModError as exc:
            return {"error": str(exc)}


class SelfProposeTool(Tool):
    name = "self_propose"
    description = (
        "Propose une modification de ton propre code. Fournis un titre, la raison, et pour chaque fichier "
        "modifié son contenu COMPLET (pas un extrait) : files = {\"app/xxx.py\": \"contenu complet\"}. "
        "Lis d'abord le fichier avec self_read. La proposition n'est PAS appliquée : elle est contrôlée "
        "(syntaxe, import) puis soumise à l'utilisateur, qui décide. Fichiers de sécurité interdits."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre court de la modification"},
            "rationale": {"type": "string", "description": "Pourquoi, et ce que ça change"},
            "files": {"type": "object", "description": "{chemin: contenu complet du fichier}"},
        },
        "required": ["title", "rationale", "files"],
    }
    permission = Permission.AUTO

    async def execute(self, title: str = "", rationale: str = "", files: Any = None, **_: Any) -> dict:
        try:
            res = await self_mod.propose(title, rationale, files if isinstance(files, dict) else {})
        except self_mod.SelfModError as exc:
            return {"error": str(exc)}
        note = "Proposition enregistrée : l'utilisateur doit la valider dans la page Évolution." if res["status"] == "pending" \
            else "Les contrôles automatiques ont échoué : corrige et repropose."
        return {**res, "note": note}
