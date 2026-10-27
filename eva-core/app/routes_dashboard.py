from pathlib import Path

from fastapi import APIRouter, HTTPException

from .memory import load_recent

DOC_FILES = ["README.md", "OBJECTIFS.md", "DECISIONS.md", "CHANGELOG.md", "TODO.md"]


def _read_if_exists(path: Path) -> str | None:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


def make_router(workspace_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/dashboard")
    projects_root = workspace_root / "projets"

    @router.get("/projects")
    async def list_projects():
        if not projects_root.exists():
            return {"projects": []}

        projects = []
        for entry in sorted(projects_root.iterdir()):
            if not entry.is_dir():
                continue
            readme = _read_if_exists(entry / "README.md")
            description = ""
            if readme:
                # Première ligne non vide après le titre, comme description courte
                lines = [l.strip() for l in readme.splitlines() if l.strip()]
                description = next((l for l in lines[1:] if not l.startswith("#")), "")
            projects.append(
                {
                    "slug": entry.name,
                    "description": description,
                    "docs_present": [f for f in DOC_FILES if (entry / f).exists()],
                }
            )
        return {"projects": projects}

    @router.get("/projects/{slug}")
    async def get_project(slug: str):
        project_dir = projects_root / slug
        try:
            project_dir.resolve().relative_to(projects_root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Chemin invalide.")

        if not project_dir.exists():
            raise HTTPException(status_code=404, detail=f"Projet introuvable : {slug}")

        docs = {f: _read_if_exists(project_dir / f) for f in DOC_FILES}
        return {"slug": slug, "docs": docs}

    @router.get("/memory")
    async def get_memory(session: str = "default", limit: int = 50):
        limit = max(1, min(limit, 200))
        messages = await load_recent(session, limit=limit)
        return {"session": session, "messages": messages}

    return router
