from pathlib import Path
from typing import Any

from ... import github as gh
from ..permissions import Permission
from .base import Tool


class GithubInfoTool(Tool):
    name = "github_info"
    description = (
        "Montre la connexion d'EVA à GitHub : connectée ou non, compte, TOUS les dépôts de la personne sur GitHub (nom, privé ou non, "
        "dernière activité) et les copies déjà clonées dans le dossier « depots » (branche, fichiers modifiés, dernier commit). "
        "À utiliser pour « es-tu connectée à mon git ? », « vérifie tous mes dépôts », « quels sont mes projets GitHub ». "
        "Pour le détail d'un dépôt cloné, utilise ensuite git_status / git_log / git_diff avec le chemin « depots/<nom> »."
    )
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, **_: Any) -> dict:
        st = await gh.status()
        if not st["connecte"]:
            return {"connecte": False, "message": "EVA n'est pas connectée à GitHub : colle un jeton dans Paramètres › Services connectés › GitHub."}
        out = {"connecte": True, "compte": st["login"], "copies_locales": await gh.depots(self.root)}
        try:
            out["depots_github"] = (await gh.repos())[:60]
        except Exception as exc:  # noqa: BLE001 — réseau, jeton expiré…
            out["depots_github_erreur"] = str(exc)[:200]
        return out
