import re
from .config import settings
from .db import get_pool


async def save_message(session_id: str, role: str, content: str, trace_id: int | None = None) -> int | None:
    if not content:
        return None
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO messages (session_id, role, content, trace_id) VALUES ($1, $2, $3, $4) RETURNING id",
            session_id,
            role,
            content,
            trace_id,
        )


_IMG_MARK = re.compile(r"\n?\[\[image:img-\d+\.png\]\]")      # repère d'image (voir images.py) : inutile pour le modèle


async def load_recent(session_id: str, limit: int | None = None) -> list[dict]:
    """Recharge les derniers messages d'une session, dans l'ordre chronologique.

    Ne renvoie que les rôles user/assistant : les messages "tool" d'un tour
    d'outils passé n'ont pas besoin d'être rejoués au modèle à la reprise.
    """
    limit = limit or settings.history_limit
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = $1 AND role IN ('user', 'assistant')
                ORDER BY created_at DESC
                LIMIT $2
            ) recent
            ORDER BY created_at ASC
            """,
            session_id,
            limit,
        )
    return [{"role": r["role"], "content": _IMG_MARK.sub("", r["content"])} for r in rows]
