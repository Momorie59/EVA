"""Agent de code : état et installation (Paramètres › Intelligence). L'installation est réservée à l'administrateur."""
import asyncio
from pathlib import Path

from fastapi import APIRouter

from . import code_agent

_taches: set[asyncio.Task] = set()


def make_router(workspace: Path) -> APIRouter:
    r = APIRouter(prefix="/api/code-agent")

    @r.get("")
    async def etat():
        return {**code_agent.statut(workspace), "modele": await code_agent.modele()}

    @r.post("/installer")
    async def installer():
        if not code_agent.statut(workspace)["en_cours"]:
            t = asyncio.create_task(code_agent.installer(workspace))
            _taches.add(t)
            t.add_done_callback(_taches.discard)
        return code_agent.statut(workspace) | {"en_cours": True}

    return r
