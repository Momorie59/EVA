import asyncio
from pathlib import Path
from typing import Any

from ..permissions import Permission
from .base import Tool
from .filesystem import WorkspaceError, _resolve_in_workspace

GIT_TIMEOUT = 15


async def _run_git(cwd: Path, *args: str) -> tuple[int, str, str]:
    if not Path(cwd).is_dir():
        return 1, "", f"Dossier introuvable : {cwd.name or cwd}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return 1, "", f"Impossible de lancer git : {exc}"
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=GIT_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 1, "", f"git a mis plus de {GIT_TIMEOUT}s à répondre (timeout)"
    return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


AIDE_DEPOT = " Les dépôts GitHub de la personne sont listés par l'outil github_info ; ceux clonés sont dans « depots/<nom> »."


def _resolve_repo(workspace_root: Path, path: str) -> Path | None:
    try:
        return _resolve_in_workspace(workspace_root, path)
    except WorkspaceError:
        return None


class GitStatusTool(Tool):
    name = "git_status"
    description = "Affiche l'état d'un dépôt Git (fichiers modifiés/ajoutés, branche courante) dans le workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du dépôt, relatif au workspace (ex: 'projets/mon-app')"},
        },
        "required": ["path"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, **_: Any) -> dict:
        repo = _resolve_repo(self.workspace_root, path)
        if repo is None:
            return {"error": f"Chemin hors du workspace refusé : {path!r}"}
        if not repo.exists():
            return {"error": f"Dossier introuvable : {path}"}

        code, out, err = await _run_git(repo, "status", "--porcelain", "--branch")
        if code != 0:
            return {"error": (err.strip() or "Ce n'est pas un dépôt Git.") + AIDE_DEPOT}

        lines = out.splitlines()
        branch_line = lines[0] if lines else ""
        changes = lines[1:]
        return {
            "path": path,
            "branch": branch_line.replace("## ", ""),
            "changes": changes,
            "clean": len(changes) == 0,
        }


class GitLogTool(Tool):
    name = "git_log"
    description = "Affiche les derniers commits d'un dépôt Git dans le workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du dépôt, relatif au workspace"},
            "count": {"type": "integer", "description": "Nombre de commits (défaut 10, max 50)"},
        },
        "required": ["path"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, count: int = 10, **_: Any) -> dict:
        count = max(1, min(count, 50))
        repo = _resolve_repo(self.workspace_root, path)
        if repo is None:
            return {"error": f"Chemin hors du workspace refusé : {path!r}"}

        code, out, err = await _run_git(repo, "log", f"-{count}", "--pretty=format:%h %ad %s", "--date=short")
        if code != 0:
            return {"error": (err.strip() or "Ce n'est pas un dépôt Git, ou aucun commit.") + AIDE_DEPOT}

        return {"path": path, "commits": out.splitlines()}


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Affiche les changements non commités d'un dépôt Git dans le workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du dépôt, relatif au workspace"},
            "staged": {"type": "boolean", "description": "Voir les changements déjà indexés (git add) plutôt que le reste"},
        },
        "required": ["path"],
    }
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, staged: bool = False, **_: Any) -> dict:
        repo = _resolve_repo(self.workspace_root, path)
        if repo is None:
            return {"error": f"Chemin hors du workspace refusé : {path!r}"}

        args = ["diff"] + (["--staged"] if staged else [])
        code, out, err = await _run_git(repo, *args)
        if code != 0:
            return {"error": (err.strip() or "Ce n'est pas un dépôt Git.") + AIDE_DEPOT}

        return {"path": path, "diff": out[:5000], "truncated": len(out) > 5000}


class GitCommitTool(Tool):
    name = "git_commit"
    description = (
        "Ajoute tous les changements (git add -A) et crée un commit dans un "
        "dépôt du workspace. Action sensible : demande toujours confirmation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du dépôt, relatif au workspace"},
            "message": {"type": "string", "description": "Message de commit"},
        },
        "required": ["path", "message"],
    }
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str, message: str, **_: Any) -> dict:
        repo = _resolve_repo(self.workspace_root, path)
        if repo is None:
            return {"error": f"Chemin hors du workspace refusé : {path!r}"}

        code, _, err = await _run_git(repo, "add", "-A")
        if code != 0:
            return {"error": f"git add a échoué : {err.strip()}"}

        code, out, err = await _run_git(repo, "commit", "-m", message)
        if code != 0:
            if "nothing to commit" in (out + err):
                return {"path": path, "committed": False, "reason": "Rien à commiter."}
            return {"error": err.strip() or out.strip() or "git commit a échoué."}

        return {"path": path, "committed": True, "message": message}
