from pathlib import Path, PurePosixPath
from typing import Any

from ..permissions import Permission
from .base import Tool
from ... import changes as journal

MAX_READ_BYTES = 200_000  # évite de faire exploser le contexte du LLM avec un gros fichier

# Permissions contextuelles pour fs_write/fs_append : la création de fichier
# est AUTO par défaut (conforme au brief initial), mais certains chemins
# sont sensibles par nature et passent en CONFIRM même pour une simple
# écriture — config, secrets, .env, docker-compose.yml...
SENSITIVE_DIR_NAMES = {"config", "configs", "secret", "secrets", "credentials"}
SENSITIVE_FILENAMES = {"docker-compose.yml", "docker-compose.yaml"}
SENSITIVE_EXTENSIONS = {".key", ".pem", ".crt", ".p12", ".pfx"}
SENSITIVE_NAME_HINTS = ("password", "secret", "credential", "token")


def _is_sensitive_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    name_lower = p.name.lower()

    if name_lower in SENSITIVE_FILENAMES:
        return True
    if name_lower == ".env" or name_lower.startswith(".env."):
        return True
    if p.suffix.lower() in SENSITIVE_EXTENSIONS:
        return True
    if any(hint in name_lower for hint in SENSITIVE_NAME_HINTS):
        return True
    if any(part.lower() in SENSITIVE_DIR_NAMES for part in p.parts[:-1]):
        return True
    return False


class WorkspaceError(Exception):
    pass


def _resolve_in_workspace(workspace_root: Path, relative_path: str) -> Path:
    """Résout un chemin demandé par le modèle et vérifie qu'il reste dans
    le workspace. C'est la seule barrière entre EVA et le reste du disque
    pour ces outils — ne jamais l'affaiblir."""
    candidate = (workspace_root / relative_path).resolve()
    workspace_resolved = workspace_root.resolve()
    if workspace_resolved not in candidate.parents and candidate != workspace_resolved:
        raise WorkspaceError(
            f"Chemin hors du workspace refusé : {relative_path!r}"
        )
    return candidate


class FsListTool(Tool):
    name = "fs_list"
    description = (
        "Liste les fichiers et dossiers d'un chemin dans le workspace d'EVA "
        "(/eva-workspace). Utilise '.' pour la racine du workspace."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin relatif au workspace, ex: 'projets'"},
        },
        "required": ["path"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str = ".", **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}

        if not target.exists():
            return {"error": f"Chemin introuvable : {path}"}
        if not target.is_dir():
            return {"error": f"Ce n'est pas un dossier : {path}"}

        entries = []
        for entry in sorted(target.iterdir()):
            entries.append(
                {
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else None,
                }
            )
        return {"path": path, "entries": entries}


class FsReadTool(Tool):
    name = "fs_read"
    description = "Lit le contenu texte d'un fichier dans le workspace d'EVA."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du fichier, relatif au workspace"},
            "offset": {"type": "integer", "description": "Position (en octets) où reprendre la lecture d'un long fichier ; 'next_offset' de la réponse précédente"},
        },
        "required": ["path"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, offset: int = 0, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}

        if not target.exists() or not target.is_file():
            return {"error": f"Fichier introuvable : {path}"}

        try:
            data = target.read_bytes()
        except OSError as exc:
            return {"error": f"Lecture impossible : {exc}"}

        start = max(0, int(offset or 0))
        chunk = data[start:start + MAX_READ_BYTES]
        truncated = len(data) > start + MAX_READ_BYTES
        content = chunk.decode("utf-8", errors="replace")
        out = {"path": path, "content": content, "truncated": truncated}
        if truncated:
            out["next_offset"] = start + MAX_READ_BYTES
        return out


class FsAppendTool(Tool):
    name = "fs_append"
    description = (
        "Ajoute du texte à la fin d'un fichier du workspace (le crée s'il "
        "n'existe pas). Utile pour un journal, un changelog, des notes "
        "qui s'accumulent au fil du temps."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du fichier, relatif au workspace"},
            "content": {"type": "string", "description": "Texte à ajouter à la fin"},
        },
        "required": ["path", "content"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def permission_for(self, args: dict) -> Permission:
        if _is_sensitive_path(args.get("path", "")):
            return Permission.CONFIRM
        return Permission.AUTO

    async def execute(self, path: str, content: str, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}

        before = journal.snapshot(target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            return {"error": f"Écriture impossible : {exc}"}
        await journal.record(self.workspace_root, target, "fs_append", before)

        return {"path": path, "bytes_appended": len(content.encode("utf-8"))}


class FsDeleteTool(Tool):
    name = "fs_delete"
    description = (
        "Supprime un fichier dans le workspace d'EVA. Action destructive : "
        "nécessite une confirmation explicite de l'utilisateur."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du fichier à supprimer, relatif au workspace"},
        },
        "required": ["path"],
    }
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}

        if not target.exists() or not target.is_file():
            return {"error": f"Fichier introuvable : {path}"}

        before = journal.snapshot(target)
        try:
            target.unlink()
        except OSError as exc:
            return {"error": f"Suppression impossible : {exc}"}
        await journal.record(self.workspace_root, target, "fs_delete", before)

        return {"path": path, "deleted": True}


class FsWriteTool(Tool):
    name = "fs_write"
    description = (
        "Crée ou remplace un fichier dans le workspace d'EVA. Les chemins "
        "sensibles (config, secrets, .env, docker-compose.yml, clés...) "
        "demandent une confirmation même pour une simple écriture."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du fichier, relatif au workspace"},
            "content": {"type": "string", "description": "Contenu texte complet à écrire"},
        },
        "required": ["path", "content"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def permission_for(self, args: dict) -> Permission:
        if _is_sensitive_path(args.get("path", "")):
            return Permission.CONFIRM
        return Permission.AUTO

    async def execute(self, path: str, content: str, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}

        before = journal.snapshot(target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"error": f"Écriture impossible : {exc}"}
        await journal.record(self.workspace_root, target, "fs_write", before)

        return {"path": path, "bytes_written": len(content.encode("utf-8"))}
