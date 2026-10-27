"""Journal des modifications d'EVA : avant/après de chaque fichier ou skill qu'elle écrit, annulable en un clic.

Ne s'applique qu'aux fichiers texte raisonnables (≤ 200 Ko) du workspace. Une erreur de journalisation ne doit
jamais empêcher l'action elle-même."""
import logging
from pathlib import Path

from .db import get_pool

logger = logging.getLogger("eva-core.changes")
MAX_BYTES = 200_000


def snapshot(path: Path) -> str | None:
    """Contenu texte actuel, ou None si le fichier n'existe pas / n'est pas lisible comme texte."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


async def record(workspace: Path, target: Path, kind: str, before: str | None) -> None:
    try:
        after = snapshot(target)
        if after == before:
            return
        rel = str(target.resolve().relative_to(workspace.resolve()))
        async with get_pool().acquire() as conn:
            await conn.execute("INSERT INTO changes (kind, path, before, after) VALUES ($1,$2,$3,$4)", kind, rel, before, after)
    except Exception:  # noqa: BLE001 — journal facultatif
        logger.debug("journal indisponible", exc_info=True)


async def list_changes(limit: int = 50) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, kind, path, before, after, created_at, undone_at FROM changes ORDER BY id DESC LIMIT $1", limit)
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "kind": r["kind"], "path": r["path"], "created_at": r["created_at"].isoformat(),
            "undone": r["undone_at"] is not None,
            "created": r["before"] is None, "deleted": r["after"] is None,
            "preview": (r["after"] if r["after"] is not None else r["before"] or "")[:300],
        })
    return out


class UndoError(Exception):
    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg)
        self.status = status


async def undo(workspace: Path, change_id: int, force: bool = False) -> dict:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM changes WHERE id=$1", change_id)
        if not r:
            raise UndoError("Modification introuvable.", 404)
        if r["undone_at"] is not None:
            raise UndoError("Déjà annulée.", 409)
        root = workspace.resolve()
        target = (root / r["path"]).resolve()
        if root not in target.parents:
            raise UndoError("Chemin hors du workspace.", 400)
        if not force and snapshot(target) != r["after"]:
            raise UndoError("Ce fichier a été modifié depuis : annuler écraserait des changements plus récents (forcer pour confirmer).", 409)
        if r["before"] is None:
            if target.exists():
                target.unlink()
            parent = target.parent
            try:
                if parent != root and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(r["before"], encoding="utf-8")
        await conn.execute("UPDATE changes SET undone_at=now() WHERE id=$1", change_id)
    return {"ok": True, "path": r["path"], "restored": r["before"] is not None}
