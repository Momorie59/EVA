from datetime import timedelta
"""Conversations : liste, titres, historique, recherche."""
import uuid

from .db import get_pool

DEFAULT_TITLE = "Nouvelle conversation"
# Les sessions techniques (agents) n'apparaissent pas dans la liste de l'utilisateur.
HIDDEN_PREFIX = "agent:"


def new_session_id() -> str:
    return f"c-{uuid.uuid4().hex[:12]}"


def _make_title(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57].rstrip() + "…"


async def create_session(title: str = "", owner: str = "") -> dict:
    sid = new_session_id()
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO sessions (id, title, owner) VALUES ($1, $2, $3)", sid, title.strip(), owner)
    return {"id": sid, "title": title.strip()}


async def can_access(session_id: str, owner: str | None) -> bool:
    """`owner` = None : administrateur (tout). Sinon : la conversation doit appartenir à cet utilisateur (ou ne pas encore exister)."""
    if owner is None:
        return True
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT owner FROM sessions WHERE id=$1", session_id)
    return row is None or row["owner"] == owner


async def ensure_session(session_id: str, first_text: str = "", owner: str = "") -> None:
    """Crée la session si besoin et pose un titre automatique à partir du
    premier message de l'utilisateur."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, title, owner) VALUES ($1, '', $2) ON CONFLICT (id) DO NOTHING",
            session_id,
            owner,
        )
        if first_text:
            await conn.execute(
                "UPDATE sessions SET title = $2 WHERE id = $1 AND title = ''",
                session_id,
                _make_title(first_text),
            )


async def touch_session(session_id: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE sessions SET updated_at = now(), supprime_le = NULL WHERE id = $1", session_id)   # on y reparle : elle revient


async def list_sessions(limit: int = 100, owner: str | None = None) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.title, s.owner, s.created_at, s.updated_at, coalesce(s.project,'') AS project,
                   coalesce(s.resume,'') <> '' AS has_fil,
                   (SELECT count(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT content FROM messages m WHERE m.session_id = s.id
                      AND m.role IN ('user','assistant') ORDER BY m.created_at DESC LIMIT 1) AS preview
            FROM sessions s
            WHERE s.id NOT LIKE $2 AND ($3::text IS NULL OR s.owner = $3) AND s.supprime_le IS NULL
            ORDER BY s.updated_at DESC
            LIMIT $1
            """,
            limit,
            HIDDEN_PREFIX + "%",
            owner,
        )
    out = []
    for r in rows:
        title = r["title"] or ("Conversation principale" if r["id"] == "default" else DEFAULT_TITLE)
        out.append(
            {
                "id": r["id"],
                "title": title,
                "owner": r["owner"] or "",
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "message_count": r["message_count"],
                "preview": (r["preview"] or "")[:120],
                "project": r["project"],
                "has_fil": r["has_fil"],
            }
        )
    return out


async def get_messages(session_id: str, limit: int = 500) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.role, t.content, t.created_at, t.trace_id, f.rating FROM (
                SELECT id, role, content, created_at, trace_id FROM messages
                WHERE session_id = $1 AND role IN ('user','assistant')
                ORDER BY created_at DESC, id DESC LIMIT $2
            ) t LEFT JOIN feedback f ON f.message_id = t.id
            ORDER BY t.created_at ASC, t.id ASC
            """,
            session_id,
            limit,
        )
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"].isoformat(),
         "trace_id": r["trace_id"], "rating": r["rating"] or 0}
        for r in rows
    ]


async def rename_session(session_id: str, title: str) -> bool:
    async with get_pool().acquire() as conn:
        res = await conn.execute(
            "UPDATE sessions SET title = $2 WHERE id = $1", session_id, _make_title(title)
        )
    return res.endswith("1")


CORBEILLE_JOURS = 30


async def delete_session(session_id: str) -> bool:
    """Met la conversation à la corbeille (récupérable 30 jours). Ses passages ne servent plus aux recherches ni au rappel."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            res = await conn.execute("UPDATE sessions SET supprime_le = now() WHERE id = $1 AND supprime_le IS NULL", session_id)
            if res.endswith("1"):
                await conn.execute("DELETE FROM doc_chunks WHERE kind = 'message' AND source = $1", f"conversation:{session_id}")
    return res.endswith("1")


async def corbeille(owner: str | None = None) -> list[dict]:
    """Conversations à la corbeille (owner None : administrateur, toutes)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT s.id, s.title, s.owner, s.supprime_le, (SELECT count(*) FROM messages m WHERE m.session_id = s.id) AS n "
            "FROM sessions s WHERE s.supprime_le IS NOT NULL AND ($1::text IS NULL OR s.owner = $1) ORDER BY s.supprime_le DESC LIMIT 500", owner)
    return [{"id": r["id"], "title": r["title"] or DEFAULT_TITLE, "owner": r["owner"] or "", "message_count": r["n"],
             "supprime_le": r["supprime_le"].isoformat(),
             "efface_le": (r["supprime_le"] + timedelta(days=CORBEILLE_JOURS)).isoformat()} for r in rows]


async def restaurer(session_id: str) -> bool:
    async with get_pool().acquire() as conn:
        res = await conn.execute("UPDATE sessions SET supprime_le = NULL WHERE id = $1 AND supprime_le IS NOT NULL", session_id)
    return res.endswith("1")


async def purger_corbeille(jours: int = CORBEILLE_JOURS) -> int:
    """Efface pour de bon ce qui est à la corbeille depuis plus de `jours` jours."""
    async with get_pool().acquire() as conn:
        ids = [r["id"] for r in await conn.fetch(
            "SELECT id FROM sessions WHERE supprime_le IS NOT NULL AND supprime_le < now() - make_interval(days => $1)", jours)]
    n = 0
    for sid in ids:
        n += await effacer_session(sid)
    return n


async def boucle_corbeille() -> None:
    import asyncio
    while True:
        try:
            await purger_corbeille()
        except Exception:  # noqa: BLE001 — base indisponible : on réessaiera
            pass
        await asyncio.sleep(6 * 3600)


async def effacer_session(session_id: str) -> bool:
    """Efface définitivement (messages compris)."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM messages WHERE session_id = $1", session_id)
            await conn.execute(
                "DELETE FROM doc_chunks WHERE kind = 'message' AND source = $1", f"conversation:{session_id}"
            )
            res = await conn.execute("DELETE FROM sessions WHERE id = $1", session_id)
    return res.endswith("1")


async def search_sessions(query: str, limit: int = 30, owner: str | None = None) -> list[dict]:
    """Recherche plein texte simple (titres + contenu des messages)."""
    q = f"%{query.strip()}%"
    if not query.strip():
        return []
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (s.id) s.id, s.title, s.owner, s.updated_at, m.content AS snippet
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id AND m.content ILIKE $1
            WHERE s.id NOT LIKE $2 AND ($3::text IS NULL OR s.owner = $3) AND (s.title ILIKE $1 OR m.id IS NOT NULL) AND s.supprime_le IS NULL
            ORDER BY s.id, m.created_at DESC
            """,
            q,
            HIDDEN_PREFIX + "%",
            owner,
        )
    rows = sorted(rows, key=lambda r: r["updated_at"], reverse=True)[:limit]
    return [
        {
            "id": r["id"],
            "title": r["title"] or DEFAULT_TITLE,
            "owner": r["owner"] or "",
            "snippet": (r["snippet"] or "")[:160],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    ]


async def owners_of(ids: list[str]) -> dict[str, str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, owner FROM sessions WHERE id = ANY($1::text[])", ids)
    return {r["id"]: r["owner"] or "" for r in rows}


async def ids_of_owner(owner: str) -> list[str]:
    """Toutes les conversations visibles d'une personne ("" = celles de l'administrateur / d'EVA sans compte)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id FROM sessions WHERE owner=$1 AND id NOT LIKE $2", owner, HIDDEN_PREFIX + "%")
    return [r["id"] for r in rows]
