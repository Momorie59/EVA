from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..permissions import Permission
from .base import Tool
from .filesystem import WorkspaceError, _resolve_in_workspace

README_TEMPLATE = """# {name}

{description}

## Statut

En cours.
"""

OBJECTIFS_TEMPLATE = """# Objectifs — {name}

- (à compléter)
"""

DECISIONS_TEMPLATE = """# Décisions — {name}

Journal des décisions prises pendant les échanges avec EVA, les plus
récentes en haut.
"""

CHANGELOG_TEMPLATE = """# Changelog — {name}

Le plus récent en haut.
"""

TODO_TEMPLATE = """# À faire — {name}

- (à compléter)
"""


def _project_dir(workspace_root: Path, slug: str) -> Path:
    return workspace_root / "projets" / slug


class ProjectInitTool(Tool):
    name = "project_init"
    description = (
        "Crée un nouveau projet dans le workspace d'EVA, avec son squelette "
        "de documentation (README.md, OBJECTIFS.md, DECISIONS.md, "
        "CHANGELOG.md, TODO.md). N'écrase rien si le projet existe déjà."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "Identifiant court du projet, en minuscules avec tirets (ex: 'gestion-locative')",
            },
            "name": {"type": "string", "description": "Nom lisible du projet"},
            "description": {"type": "string", "description": "Description courte du projet"},
        },
        "required": ["slug", "name", "description"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, slug: str, name: str, description: str, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, f"projets/{slug}")
        except WorkspaceError as exc:
            return {"error": str(exc)}

        already_existed = target.exists()
        target.mkdir(parents=True, exist_ok=True)

        files = {
            "README.md": README_TEMPLATE.format(name=name, description=description),
            "OBJECTIFS.md": OBJECTIFS_TEMPLATE.format(name=name),
            "DECISIONS.md": DECISIONS_TEMPLATE.format(name=name),
            "CHANGELOG.md": CHANGELOG_TEMPLATE.format(name=name),
            "TODO.md": TODO_TEMPLATE.format(name=name),
        }

        created = []
        for filename, content in files.items():
            file_path = target / filename
            if not file_path.exists():
                file_path.write_text(content, encoding="utf-8")
                created.append(filename)

        return {
            "slug": slug,
            "already_existed": already_existed,
            "files_created": created,
        }


class ProjectLogDecisionTool(Tool):
    name = "project_log_decision"
    description = (
        "Note une décision prise pendant la conversation dans le "
        "DECISIONS.md du projet concerné (avec la date). À utiliser dès "
        "qu'un choix clair est fait (techno, architecture, nom...), sans "
        "attendre qu'on te le demande explicitement."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Identifiant du projet (voir project_init)"},
            "decision": {"type": "string", "description": "La décision, formulée simplement"},
        },
        "required": ["slug", "decision"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, slug: str, decision: str, **_: Any) -> dict:
        return _append_dated_entry(
            self.workspace_root, slug, "DECISIONS.md", decision, DECISIONS_TEMPLATE, slug
        )


class ProjectLogChangeTool(Tool):
    name = "project_log_change"
    description = (
        "Note un changement (création, modification, correction) dans le "
        "CHANGELOG.md du projet concerné (avec la date). À utiliser après "
        "toute modification notable faite dans le workspace du projet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Identifiant du projet (voir project_init)"},
            "change": {"type": "string", "description": "Le changement, formulé simplement"},
        },
        "required": ["slug", "change"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, slug: str, change: str, **_: Any) -> dict:
        return _append_dated_entry(
            self.workspace_root, slug, "CHANGELOG.md", change, CHANGELOG_TEMPLATE, slug
        )


def _append_dated_entry(
    workspace_root: Path, slug: str, filename: str, text: str, template: str, name_for_template: str
) -> dict:
    try:
        target = _resolve_in_workspace(workspace_root, f"projets/{slug}/{filename}")
    except WorkspaceError as exc:
        return {"error": str(exc)}

    if not target.parent.exists():
        return {"error": f"Projet introuvable : {slug} (utilise project_init d'abord)"}

    if not target.exists():
        target.write_text(template.format(name=name_for_template), encoding="utf-8")

    entry = f"\n## {date.today().isoformat()}\n\n- {text}\n"
    with target.open("a", encoding="utf-8") as f:
        f.write(entry)

    return {"slug": slug, "file": filename, "logged_at": datetime.now().isoformat(timespec="seconds")}
