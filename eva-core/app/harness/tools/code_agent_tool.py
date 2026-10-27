"""Outil « code_agent » : confie une tâche de programmation à l'agent de code (Aider + modèle local) sur un projet."""
from pathlib import Path
from typing import Any

from ... import code_agent
from ..permissions import Permission
from .base import Tool


import re

_ANALYSE = re.compile(r"\b(analys\w*|[ée]tudi\w*|examin\w*|audit\w*|explor\w*|lis|lire|relis|relire|comprend\w*|compren\w*|revue|r[ée]sum\w*|explique\w*|d[ée]cri\w*|inspect\w*)\b", re.I)
_MODIFIE = re.compile(r"\b(modifi\w*|corrig\w*|ajout\w*|ajoute\w*|[ée]cri\w*|cr[ée]\w*|supprim\w*|remplac\w*|refactor\w*|impl[ée]ment\w*|r[ée]par\w*|fix\w*|chang\w*|renomm\w*|d[ée]plac\w*|optimis\w*|am[ée]lior\w*|mets? [àa] jour|test\w*)\b", re.I)


class CodeAgentTool(Tool):
    name = "code_agent"
    description = ("Confie une tâche de programmation à l'agent de code (Aider, modèle local) sur un projet de projets/<slug> : "
                   "écrire une fonction, corriger un bug, ajouter des tests, refactorer. Il lit le code, modifie les fichiers et "
                   "enregistre chaque modification dans git (annulable). Donne une consigne précise et, si tu les connais, les "
                   "fichiers concernés. Plusieurs minutes possibles. Montre ensuite le résumé (fichiers modifiés, diff). "
                   "NE SERT PAS à analyser, lire, étudier ou expliquer du code (pour cela : fs_tree, fs_read, fs_grep) : uniquement à MODIFIER du code.")
    parameters = {"type": "object", "properties": {
        "slug": {"type": "string", "description": "Projet (dossier projets/<slug>)"},
        "consigne": {"type": "string", "description": "Ce qu'il faut faire, précisément"},
        "fichiers": {"type": "array", "items": {"type": "string"}, "description": "Fichiers à modifier (chemins dans le projet), optionnel"}},
        "required": ["slug", "consigne"]}
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self._ws = Path(workspace_root)

    async def execute(self, slug: str = "", consigne: str = "", fichiers: Any = None, **_: Any) -> dict:
        if _ANALYSE.search(consigne or "") and not _MODIFIE.search(consigne or ""):
            from ... import fil                              # demande d'analyse : pas d'Aider, on donne le vrai contenu du projet
            apercu = fil.apercu(self._ws, (slug or "").strip().strip("/")) if (slug or "").strip() else ""
            if not apercu:
                return {"error": "Pour analyser, indique le projet (projets existants : " + (", ".join(fil.projets_existants(self._ws)) or "aucun") + ")."}
            return {"analyse": apercu, "consigne": "Ceci est une demande d'analyse, pas de modification : l'agent de code n'a rien changé. "
                    "Lis les fichiers importants avec fs_read / fs_grep, puis rends une analyse complète (structure, rôle de chaque partie, points forts, "
                    "problèmes, améliorations), en citant les fichiers."}
        if isinstance(fichiers, str):
            fichiers = [f.strip() for f in fichiers.split(",") if f.strip()]
        return await code_agent.lancer(self._ws, slug, consigne, fichiers if isinstance(fichiers, list) else None)
