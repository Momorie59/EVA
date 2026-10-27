from fastapi import APIRouter, HTTPException, Query

from . import costs
from .db import get_pool


def _llm_ms(steps) -> int:
    return sum(int(s.get("duration_ms") or 0) for s in steps if s.get("type") == "llm")


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/traces")

    @router.get("/summary")
    async def summary(days: int = Query(7, ge=1, le=90)):
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, kind, model, started_at, duration_ms, prompt_tokens, completion_tokens, steps, ok
                   FROM traces WHERE started_at > now() - make_interval(days => $1)""", days)
        import json
        pt = sum(r["prompt_tokens"] for r in rows)
        ct = sum(r["completion_tokens"] for r in rows)
        llm_ms = 0
        tools: dict[str, int] = {}
        models: dict[str, int] = {}
        per_day: dict[str, dict] = {}
        for r in rows:
            steps = r["steps"] if isinstance(r["steps"], list) else json.loads(r["steps"])
            llm_ms += _llm_ms(steps)
            for st in steps:
                if st.get("type") == "tool":
                    tools[st["name"]] = tools.get(st["name"], 0) + 1
            models[r["model"]] = models.get(r["model"], 0) + 1
            d = r["started_at"].date().isoformat()
            e = per_day.setdefault(d, {"day": d, "traces": 0, "tokens": 0})
            e["traces"] += 1
            e["tokens"] += r["prompt_tokens"] + r["completion_tokens"]
        kwh = costs.energy_kwh(llm_ms)
        return {
            "days": days,
            "traces": len(rows),
            "errors": sum(1 for r in rows if not r["ok"]),
            "prompt_tokens": pt, "completion_tokens": ct,
            "llm_seconds": round(llm_ms / 1000, 1),
            "energy_kwh": round(kwh, 5),
            "local_cost_eur": round(costs.local_cost_eur(llm_ms), 5),
            "cloud_equivalents": costs.cloud_equivalents(pt, ct),
            "assumptions": {"gpu_watts": costs.settings.gpu_watts, "kwh_price_eur": costs.settings.kwh_price,
                            "note": "Estimations : puissance GPU moyenne × temps de calcul ; tarifs cloud approximatifs."},
            "tools": sorted(({"name": k, "count": v} for k, v in tools.items()), key=lambda x: -x["count"]),
            "models": [{"name": k, "count": v} for k, v in models.items()],
            "per_day": sorted(per_day.values(), key=lambda x: x["day"]),
        }

    @router.get("")
    async def list_traces(limit: int = Query(50, ge=1, le=200), kind: str | None = None):
        if kind not in (None, "chat", "agent"):
            raise HTTPException(status_code=400, detail="kind doit être chat ou agent.")
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, kind, session_id, label, model, started_at, duration_ms,
                          prompt_tokens, completion_tokens, ok, jsonb_array_length(steps) AS n_steps
                   FROM traces WHERE ($1::text IS NULL OR kind = $1) ORDER BY id DESC LIMIT $2""",
                kind, limit)
        return {"traces": [{**dict(r), "started_at": r["started_at"].isoformat()} for r in rows]}

    @router.get("/{trace_id}")
    async def get_trace(trace_id: int):
        import json
        async with get_pool().acquire() as conn:
            r = await conn.fetchrow("SELECT * FROM traces WHERE id=$1", trace_id)
        if not r:
            raise HTTPException(status_code=404, detail="Trace introuvable.")
        d = dict(r)
        d["started_at"] = d["started_at"].isoformat()
        d["steps"] = d["steps"] if isinstance(d["steps"], list) else json.loads(d["steps"])
        d["energy_kwh"] = round(costs.energy_kwh(_llm_ms(d["steps"])), 6)
        return d

    return router
