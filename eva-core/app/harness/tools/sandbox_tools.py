"""Outils de bac à sable pour EVA : exécuter du code d'un projet, installer des paquets, utiliser une base PostgreSQL de test."""
from pathlib import Path
from typing import Any

from ... import projects, sandbox_proj
from ..permissions import Permission
from .base import Tool


def _clean(project: str) -> str:
    return projects.slugify(project or "")


class SandboxRunTool(Tool):
    name = "sandbox_run"
    description = (
        "Exécute une commande dans le BAC À SABLE d'un projet (conteneur jetable isolé, Python 3.12, dossier de travail = projets/<projet>). "
        "Sert à lancer les scripts, les tests (python -m pytest) et à vérifier que le code fonctionne. "
        "Les paquets installés avec sandbox_install sont disponibles. Si le projet a une base de test (sandbox_db), la variable "
        "DATABASE_URL est fournie automatiquement. Pas d'accès à Internet par défaut (internet=true demande une confirmation)."
    )
    parameters = {"type": "object", "properties": {
        "project": {"type": "string", "description": "Identifiant du projet (dossier dans projets/)"},
        "command": {"type": "string", "description": "Commande shell, ex. 'python main.py' ou 'python -m pytest -q'"},
        "timeout": {"type": "integer", "description": "Secondes (défaut 60, max 600)"},
        "internet": {"type": "boolean", "description": "Autoriser l'accès à Internet (confirmation demandée)"}},
        "required": ["project", "command"]}
    permission = Permission.AUTO
    agent_safe = True

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root

    def permission_for(self, args: dict) -> Permission:
        return Permission.CONFIRM if args.get("internet") else Permission.AUTO

    async def execute(self, project: str = "", command: str = "", timeout: int = 60, internet: bool = False, **_: Any) -> dict:
        try:
            return await sandbox_proj.run(self.ws, _clean(project), command, timeout, bool(internet))
        except projects.ProjectError as exc:
            return {"error": str(exc) + " (crée-le d'abord avec project_init)"}


class SandboxInstallTool(Tool):
    name = "sandbox_install"
    description = (
        "Installe des paquets Python (pip) dans le bac à sable d'un projet (dossier .deps du projet, conservé entre les exécutions). "
        "Demande une confirmation car cela utilise Internet."
    )
    parameters = {"type": "object", "properties": {
        "project": {"type": "string", "description": "Identifiant du projet"},
        "packages": {"type": "array", "items": {"type": "string"}, "description": "Ex. ['requests', 'pytest', 'psycopg[binary]']"}},
        "required": ["project", "packages"]}
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root

    async def execute(self, project: str = "", packages: list | None = None, **_: Any) -> dict:
        pk = packages if isinstance(packages, list) else [str(packages or "")]
        try:
            return await sandbox_proj.install(self.ws, _clean(project), [str(p) for p in pk])
        except projects.ProjectError as exc:
            return {"error": str(exc)}


class SandboxDbTool(Tool):
    name = "sandbox_db"
    description = (
        "Base de données PostgreSQL de TEST propre à un projet (jamais la base d'EVA). Actions : 'create' (la crée si besoin), "
        "'query' (exécute du SQL : CREATE TABLE, INSERT, SELECT…), 'tables' (liste les tables), 'reset' (la vide complètement), 'drop' (la supprime). "
        "Le code lancé avec sandbox_run reçoit l'adresse dans la variable DATABASE_URL."
    )
    parameters = {"type": "object", "properties": {
        "project": {"type": "string", "description": "Identifiant du projet"},
        "action": {"type": "string", "enum": ["create", "query", "tables", "reset", "drop"]},
        "sql": {"type": "string", "description": "Requête SQL (action 'query')"}},
        "required": ["project", "action"]}
    permission = Permission.AUTO
    agent_safe = True

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root

    def permission_for(self, args: dict) -> Permission:
        return Permission.CONFIRM if args.get("action") in ("drop", "reset") else Permission.AUTO

    async def execute(self, project: str = "", action: str = "", sql: str = "", **_: Any) -> dict:
        try:
            slug = _clean(project)
            projects.project_dir(self.ws, slug)
            if action == "create":
                i = await sandbox_proj.ensure_db(slug)
                return {"database": i["database"], "created": i["created"], "note": "Dans sandbox_run, l'adresse est dans DATABASE_URL."}
            if action == "query":
                return await sandbox_proj.query(slug, sql)
            if action == "tables":
                return await sandbox_proj.tables(slug)
            if action == "reset":
                i = await sandbox_proj.reset_db(slug)
                return {"database": i["database"], "reset": True}
            if action == "drop":
                return {"dropped": await sandbox_proj.drop_db(slug)}
            return {"error": "Action inconnue."}
        except projects.ProjectError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Base de test indisponible : {exc}"}
