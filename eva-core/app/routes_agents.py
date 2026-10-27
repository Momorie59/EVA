from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import agents


class AgentCreate(BaseModel):
    name: str
    template: str = "custom"
    instruction: str = ""
    schedule_type: str = "manual"
    schedule_value: str = ""
    enabled: bool = True


class AgentDesign(BaseModel):
    goal: str


class AgentUpdate(BaseModel):
    name: str | None = None
    instruction: str | None = None
    schedule_type: str | None = None
    schedule_value: str | None = None
    enabled: bool | None = None


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/agent-templates")
    async def templates():
        return {
            "templates": [
                {"id": k, **{f: v[f] for f in ("name", "description", "needs_instruction", "schedule_type", "schedule_value")}}
                for k, v in agents.TEMPLATES.items()
            ]
        }

    @router.post("/agents/design")
    async def design(body: AgentDesign):
        try:
            return await agents.design(body.goal)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/agents")
    async def list_all():
        return {"agents": await agents.list_agents()}

    @router.post("/agents")
    async def create(body: AgentCreate):
        try:
            return await agents.create_agent(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/agents/{agent_id}")
    async def update(agent_id: int, body: AgentUpdate):
        try:
            result = await agents.update_agent(agent_id, body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        return result

    @router.delete("/agents/{agent_id}")
    async def delete(agent_id: int):
        if not await agents.delete_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        return {"ok": True}

    @router.post("/agents/{agent_id}/run")
    async def run(agent_id: int):
        if not await agents.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        try:
            run_id = await agents.start_run(agent_id, manual=True)
        except agents.AlreadyRunning:
            raise HTTPException(status_code=409, detail="Cet agent est déjà en cours d'exécution.")
        return {"run_id": run_id}

    @router.get("/agents/{agent_id}/runs")
    async def runs(agent_id: int):
        return {"runs": await agents.list_runs(agent_id)}

    @router.get("/agent-runs/{run_id}")
    async def run_detail(run_id: int):
        r = await agents.get_run(run_id)
        if not r:
            raise HTTPException(status_code=404, detail="Exécution introuvable.")
        return r

    return router
