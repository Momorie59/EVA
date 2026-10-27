from pathlib import Path
from typing import Any

from ... import changes as journal
from ... import skills as sk
from ..permissions import Permission
from .base import Tool


class SkillListTool(Tool):
    name = "skill_list"
    description = "Liste les compétences (skills) disponibles avec leur description."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, **_: Any) -> dict:
        return {"skills": [s for s in sk.list_skills(self.root) if s.get("valid") and s["actif"] and s["kind"] == "skill"]}


class SkillReadTool(Tool):
    name = "skill_read"
    description = (
        "Charge les instructions détaillées d'une compétence (skill) par son nom. "
        "À appeler avant d'agir quand la demande correspond à une compétence du catalogue."
    )
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Nom du skill"}},
        "required": ["name"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, name: str = "", **_: Any) -> dict:
        try:
            skill = sk.get_skill(name, self.root)
        except sk.SkillError as exc:
            return {"error": str(exc)}
        if not skill:
            return {"error": f"Skill introuvable : {name}"}
        if not skill["valid"]:
            return {"error": skill["error"]}
        return {"name": skill["name"], "instructions": skill["body"]}


class SkillSaveTool(Tool):
    name = "skill_save"
    description = (
        "Crée ou met à jour une compétence réutilisable (instructions en Markdown). "
        "Demande toujours la confirmation de l'utilisateur."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom court en minuscules (ex: resume-reunion)"},
            "description": {"type": "string", "description": "Quand utiliser ce skill, en une phrase"},
            "instructions": {"type": "string", "description": "Les étapes à suivre, en Markdown"},
        },
        "required": ["name", "description", "instructions"],
    }
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, name: str = "", description: str = "", instructions: str = "", **_: Any) -> dict:
        try:
            slug = sk.slugify(name)
            f = sk.skills_root(self.root) / slug / "SKILL.md"
            before = journal.snapshot(f)
            res = sk.save_skill_raw(slug, sk.render_skill(slug, description, instructions), self.root)
            await journal.record(self.root, f, "skill_save", before)
            return res
        except sk.SkillError as exc:
            return {"error": str(exc)}


class SkillInstallTool(Tool):
    name = "skill_install"
    description = (
        "Installe une compétence depuis GitHub (owner/repo ou owner/repo/dossier). "
        "Demande toujours la confirmation de l'utilisateur."
    )
    parameters = {
        "type": "object",
        "properties": {"source": {"type": "string", "description": "owner/repo[/chemin] ou URL github.com"}},
        "required": ["source"],
    }
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, source: str = "", **_: Any) -> dict:
        try:
            res = await sk.install_from_github(source, self.root)
            if isinstance(res, dict) and res.get("name"):
                await journal.record(self.root, sk.skills_root(self.root) / res["name"] / "SKILL.md", "skill_install", None)
            return res
        except sk.SkillError as exc:
            if "Aucun SKILL.md" in str(exc):
                try:
                    cat = await sk.catalog(source, self.root)
                    n = sum(1 for x in cat["items"] if x.get("ok"))
                    return {"error": f"Ce dépôt contient {n} skills (pas un seul). Dis à l'utilisateur d'ouvrir la page Skills › « Parcourir un dépôt GitHub », "
                                     f"de coller {cat['source']} puis de cocher ceux qu'il veut installer.", "count": n}
                except Exception:  # noqa: BLE001
                    pass
            return {"error": str(exc)}
