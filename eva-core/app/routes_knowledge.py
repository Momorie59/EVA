from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import changes, personality
from .db import get_pool

MAX_NODES = 120


class UndoBody(BaseModel):
    force: bool = False


def make_router(workspace_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/personality")
    async def get_personality():
        return {"current": await personality.get(), "presets": [{"id": k, "label": v["label"]} for k, v in personality.PRESETS.items()]}

    @router.put("/personality")
    async def put_personality(body: dict):
        try:
            return {"current": await personality.set_(str(body.get("id", "")))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/changes")
    async def list_changes(limit: int = Query(50, ge=1, le=200)):
        return {"changes": await changes.list_changes(limit)}

    @router.post("/changes/{change_id}/undo")
    async def undo(change_id: int, body: UndoBody | None = None):
        try:
            return await changes.undo(workspace_root, change_id, bool(body and body.force))
        except changes.UndoError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    @router.get("/memory/node")
    async def node(source: str = Query(..., min_length=1, max_length=500)):
        async with get_pool().acquire() as conn:
            rows = await conn.fetch("SELECT kind, content FROM doc_chunks WHERE source=$1 ORDER BY chunk_index LIMIT 3", source)
        if not rows:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        return {"source": source, "kind": rows[0]["kind"], "chunks": [r["content"][:400] for r in rows]}

    @router.get("/memory/graph")
    async def graph(threshold: float = Query(0.55, ge=0.2, le=0.95)):
        """Carte de ce qu'EVA sait : un nœud par document ou conversation indexé, relié aux plus proches (embeddings)."""
        async with get_pool().acquire() as conn:
            rows = await conn.fetch("SELECT source, kind, embedding FROM doc_chunks")
        from collections import Counter
        dims = Counter(len(r["embedding"]) for r in rows)
        dim = dims.most_common(1)[0][0] if dims else 0       # si le modèle d'embeddings a changé, on garde la dimension majoritaire
        agg: dict[str, dict] = {}
        for r in rows:
            if len(r["embedding"]) != dim:
                continue
            e = agg.setdefault(r["source"], {"kind": r["kind"], "sum": None, "n": 0})
            v = np.asarray(r["embedding"], dtype=np.float32)
            e["sum"] = v if e["sum"] is None else e["sum"] + v
            e["n"] += 1
        items = sorted(agg.items(), key=lambda kv: -kv[1]["n"])[:MAX_NODES]
        if not items:
            return {"nodes": [], "edges": []}
        mat = np.stack([it[1]["sum"] / it[1]["n"] for it in items])
        mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        sim = mat @ mat.T
        np.fill_diagonal(sim, -1)
        edges, seen = [], set()
        for i in range(len(items)):
            for j in np.argsort(-sim[i])[:3]:
                if sim[i, j] >= threshold:
                    key = (min(i, int(j)), max(i, int(j)))
                    if key not in seen:
                        seen.add(key)
                        edges.append({"a": key[0], "b": key[1], "w": round(float(sim[i, j]), 3)})
        nodes = []
        for src, e in items:
            label = src.replace("conversation:", "Conversation ") if e["kind"] == "message" else src.rsplit("/", 1)[-1]
            nodes.append({"id": src, "label": label[:40], "kind": e["kind"], "chunks": e["n"]})
        return {"nodes": nodes, "edges": edges}

    return router
