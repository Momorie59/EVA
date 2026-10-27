from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .harness.tools.code_run import CodeRunTool


class RunBody(BaseModel):
    code: str


def make_router() -> APIRouter:
    """Exécution de code à la demande de l'utilisateur (bouton « Exécuter » sous un bloc de code).
    Le clic vaut accord ; l'exécution reste isolée dans le conteneur jetable de code_run."""
    router = APIRouter(prefix="/api/sandbox")
    tool = CodeRunTool()

    @router.post("/run")
    async def run(body: RunBody):
        result = await tool.execute(code=body.code)
        if "error" in result and "exit_code" not in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    return router
