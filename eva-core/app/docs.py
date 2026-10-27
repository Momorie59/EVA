"""Documents et mémoire sémantique : indexation de fichiers texte et de conversations
dans Postgres (vecteurs REAL[]), recherche par similarité cosinus calculée en Python."""
import asyncio
import contextvars
import logging
import math
import re
from pathlib import Path

import httpx

from .config import settings
from .db import get_pool

logger = logging.getLogger("eva-core.docs")

TEXT_EXT = {
    ".md", ".txt", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".csv", ".log", ".html", ".css", ".sh", ".sql", ".env.example",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".cache"}
MAX_FILE_BYTES = 1_000_000
CHUNK_CHARS = 800
CHUNK_OVERLAP = 100
EMBED_BATCH = 16
MAX_FILES = 5000

_lock = asyncio.Lock()


class DocsError(RuntimeError):
    pass


def roots(workspace: Path | None = None) -> list[tuple[str, Path]]:
    """(préfixe affiché, dossier). Le workspace n'a pas de préfixe."""
    ws = Path(workspace or settings.workspace_root)
    out: list[tuple[str, Path]] = [("", ws)]
    for raw in settings.docs_paths.split(","):
        raw = raw.strip()
        if raw and Path(raw).is_dir() and Path(raw).resolve() != ws.resolve():
            out.append((Path(raw).name or "docs", Path(raw)))
    return out


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # paragraphe trop long : on le découpe
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:size])
            p = p[size - overlap:]
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = (tail + "\n\n" + p).strip() if tail else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    url = f"{settings.ollama_host.rstrip('/')}/api/embed"
    out: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            for i in range(0, len(texts), EMBED_BATCH):
                batch = texts[i:i + EMBED_BATCH]
                resp = await client.post(url, json={"model": settings.embed_model, "input": batch})
                if resp.status_code == 404:
                    raise DocsError(
                        f"Le modèle d'embeddings « {settings.embed_model} » est absent du serveur IA. "
                        f"Installe-le avec : ollama pull {settings.embed_model}"
                    )
                if resp.status_code != 200:
                    raise DocsError(f"Ollama a répondu {resp.status_code} : {resp.text[:200]}")
                vecs = resp.json().get("embeddings") or []
                if len(vecs) != len(batch):
                    raise DocsError("Réponse d'embeddings incohérente.")
                out.extend(vecs)
    except httpx.HTTPError as exc:
        raise DocsError(f"Serveur IA injoignable pour les embeddings : {exc}") from exc
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _scan(workspace: Path | None) -> dict[str, tuple[Path, float, int]]:
    found: dict[str, tuple[Path, float, int]] = {}
    for prefix, root in roots(workspace):
        for dirpath, dirnames, filenames in __import__("os").walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                f = Path(dirpath) / fn
                if f.suffix.lower() not in TEXT_EXT or fn.startswith("."):
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                if st.st_size == 0 or st.st_size > MAX_FILE_BYTES:
                    continue
                rel = f.relative_to(root).as_posix()
                found[f"{prefix}/{rel}" if prefix else rel] = (f, st.st_mtime, st.st_size)
                if len(found) >= MAX_FILES:
                    return found
    return found


async def index_files(workspace: Path | None = None) -> dict:
    scan = await asyncio.to_thread(_scan, workspace)
    pool = get_pool()
    async with pool.acquire() as conn:
        known = {r["path"]: (r["mtime"], r["size"]) for r in await conn.fetch("SELECT path, mtime, size FROM doc_files")}
    removed = [p for p in known if p not in scan]
    todo = [k for k, (f, m, s) in scan.items() if known.get(k) != (m, s)]
    async with pool.acquire() as conn:
        for p in removed:
            await conn.execute("DELETE FROM doc_chunks WHERE kind='file' AND source=$1", p)
            await conn.execute("DELETE FROM doc_files WHERE path=$1", p)
    indexed = 0
    chunks_added = 0
    for key in todo:
        f, mtime, size = scan[key]
        try:
            text = await asyncio.to_thread(f.read_text, "utf-8", "replace")
        except OSError:
            continue
        parts = chunk_text(text)
        vecs = await embed([f"{key}\n{c}" for c in parts]) if parts else []
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM doc_chunks WHERE kind='file' AND source=$1", key)
                if parts:
                    await conn.executemany(
                        "INSERT INTO doc_chunks (source, kind, chunk_index, content, embedding) VALUES ($1,'file',$2,$3,$4)",
                        [(key, i, c, v) for i, (c, v) in enumerate(zip(parts, vecs))],
                    )
                await conn.execute(
                    """INSERT INTO doc_files (path, mtime, size, indexed_at) VALUES ($1,$2,$3,now())
                       ON CONFLICT (path) DO UPDATE SET mtime=$2, size=$3, indexed_at=now()""",
                    key, mtime, size,
                )
        indexed += 1
        chunks_added += len(parts)
    return {"files_indexed": indexed, "files_removed": len(removed), "chunks_added": chunks_added, "files_total": len(scan)}


async def index_messages(limit: int = 300) -> dict:
    """Indexe les nouveaux messages des conversations (hors agents) pour la mémoire sémantique."""
    pool = get_pool()
    async with pool.acquire() as conn:
        last = await conn.fetchval("SELECT COALESCE(max(ref::bigint), 0) FROM doc_chunks WHERE kind='message'")
        rows = await conn.fetch(
            """SELECT id, session_id, role, content FROM messages
               WHERE id > $1 AND role IN ('user','assistant') AND length(content) >= 40
                 AND session_id NOT LIKE 'agent:%'
               ORDER BY id LIMIT $2""",
            last, limit,
        )
    if not rows:
        return {"messages_indexed": 0}
    texts = [r["content"][:CHUNK_CHARS * 2] for r in rows]
    vecs = await embed(texts)
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO doc_chunks (source, kind, ref, chunk_index, content, embedding) VALUES ($1,'message',$2,0,$3,$4)",
            [(f"conversation:{r['session_id']}", str(r["id"]), t, v) for r, t, v in zip(rows, texts, vecs)],
        )
    return {"messages_indexed": len(rows)}


async def reindex(workspace: Path | None = None) -> dict:
    if _lock.locked():
        raise DocsError("Une indexation est déjà en cours.")
    async with _lock:
        res = await index_files(workspace)
        res.update(await index_messages())
        return res


# None = administrateur (tout). Sinon : l'utilisateur ne retrouve que SES conversations et les dossiers partagés (jamais ceux des autres).
owner_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("docs_owner", default=None)


def _visible(source: str, own_sessions: set[str], shared: tuple[str, ...], owner: str = "") -> bool:
    if source.startswith("conversation:"):
        return source.split(":", 1)[1] in own_sessions
    if any(source.startswith(p + "/") for p in shared):
        return True
    from . import acces                                  # ses propres fichiers déposés et ses photos
    return acces.source_visible(Path(settings.workspace_root), source, owner)


async def search(query: str, k: int = 5, kind: str | None = None, prefix: str | None = None, owner: str | None | bool = False) -> list[dict]:
    query = (query or "").strip()
    if owner is False:
        owner = owner_var.get()
    if not query:
        return []
    qv = (await embed([query]))[0]
    conds, args = [], []
    if kind:
        args.append(kind); conds.append(f"kind=${len(args)}")
    if prefix:
        args.append(prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"); conds.append(f"source LIKE ${len(args)}")
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT source, kind, ref, chunk_index, content, embedding FROM doc_chunks" + (" WHERE " + " AND ".join(conds) if conds else ""),
            *args,
        )
    if owner is not None:
        async with get_pool().acquire() as conn:
            own = {r["id"] for r in await conn.fetch("SELECT id FROM sessions WHERE owner=$1", owner)}
        shared = tuple(pre for pre, _ in roots()[1:] if pre)
        rows = [r for r in rows if _visible(r["source"], own, shared, owner)]
    scored = sorted(
        ({"source": r["source"], "kind": r["kind"], "chunk": r["chunk_index"],
          "score": round(cosine(qv, list(r["embedding"])), 4), "content": r["content"]} for r in rows),
        key=lambda x: x["score"], reverse=True,
    )
    return scored[: max(1, min(k, 20))]


async def status() -> dict:
    async with get_pool().acquire() as conn:
        files = await conn.fetchval("SELECT count(*) FROM doc_files")
        fchunks = await conn.fetchval("SELECT count(*) FROM doc_chunks WHERE kind='file'")
        mchunks = await conn.fetchval("SELECT count(*) FROM doc_chunks WHERE kind='message'")
        last = await conn.fetchval("SELECT max(indexed_at) FROM doc_files")
    return {
        "files": files, "file_chunks": fchunks, "messages": mchunks,
        "last_indexed_at": last.isoformat() if last else None,
        "embed_model": settings.embed_model,
        "roots": [{"name": n or "workspace", "path": str(p)} for n, p in roots()],
        "running": _lock.locked(),
    }


async def periodic_reindex() -> None:
    try:
        res = await reindex()
        if res.get("files_indexed") or res.get("messages_indexed") or res.get("files_removed"):
            logger.info("Indexation : %s", res)
    except DocsError as exc:
        logger.warning("Indexation impossible : %s", exc)
