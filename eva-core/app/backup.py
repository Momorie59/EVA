"""Sauvegarde / restauration : tables de données d'EVA (conversations, avis, agents, réglages, traces, propositions)
+ fichiers du workspace (skills, projets, notes). Les index de documents sont reconstruits seuls.
ATTENTION : la sauvegarde contient aussi les réglages, donc les jetons (Google, Telegram, Home Assistant…) :
à garder en lieu sûr. Une sauvegarde quotidienne est faite dans workspace/backups (7 conservées)."""
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .config import settings
from .db import get_pool

logger = logging.getLogger("eva-core.backup")

# Ordre = ordre d'insertion (agents avant agent_runs).
TABLES = ["sessions", "messages", "feedback", "kv", "agents", "agent_runs", "proposals", "traces", "memoire", "wiki_pages", "wiki_versions", "recettes",
          "fin_comptes", "fin_operations", "fin_regles", "fin_budgets", "contenus", "rappels"]
OPTIONNELLES = {"memoire", "wiki_pages", "wiki_versions", "recettes", "fin_comptes", "fin_operations", "fin_regles", "fin_budgets", "contenus", "rappels"}          # absentes des sauvegardes plus anciennes : restaurées vides
NAME_RE = re.compile(r"^eva-\d{8}-\d{6}\.zip$")
KEEP = 7
MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 300 * 1024 * 1024


class BackupError(RuntimeError):
    pass


def _root() -> Path:
    return Path(settings.workspace_root).resolve()


def _dir() -> Path:
    d = _root() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def make_zip() -> bytes:
    buf = io.BytesIO()
    total = 0
    async with get_pool().acquire() as conn:
        dumps = {}
        for t in TABLES:
            dumps[t] = await conn.fetchval(f"SELECT coalesce(json_agg(t), '[]'::json)::text FROM {t} t")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"app": "eva", "format": 1, "created": datetime.now().isoformat(timespec="seconds"), "tables": TABLES}))
        for t, text in dumps.items():
            z.writestr(f"db/{t}.json", text)
        root = _root()
        for p in sorted(root.rglob("*")):
            if not p.is_file() or {"backups", ".outils"} & set(p.relative_to(root).parts):
                continue                                   # .outils : agent de code (réinstallable, ~650 Mo)
            size = p.stat().st_size
            if size > MAX_FILE or total + size > MAX_TOTAL:
                logger.warning("Sauvegarde : %s ignoré (taille)", p)
                continue
            total += size
            z.write(p, f"workspace/{p.relative_to(root).as_posix()}")
    return buf.getvalue()


async def create() -> dict:
    data = await make_zip()
    name = datetime.now().strftime("eva-%Y%m%d-%H%M%S.zip")
    d = _dir()
    (d / name).write_bytes(data)
    for old in sorted(d.glob("eva-*.zip"))[:-KEEP]:
        old.unlink(missing_ok=True)
    return {"name": name, "size": len(data)}


def listing() -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size, "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(_dir().glob("eva-*.zip"), reverse=True) if NAME_RE.match(p.name)]


def path_of(name: str) -> Path | None:
    if not NAME_RE.match(name or ""):
        return None
    p = _dir() / name
    return p if p.is_file() else None


async def periodic() -> None:
    try:
        info = await create()
        logger.info("Sauvegarde quotidienne : %s (%d octets)", info["name"], info["size"])
    except Exception:  # noqa: BLE001
        logger.exception("Sauvegarde quotidienne en échec")


async def restore(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BackupError("Ce fichier n'est pas une archive zip valide.") from exc
    names = z.namelist()
    try:
        manifest = json.loads(z.read("manifest.json"))
    except (KeyError, ValueError) as exc:
        raise BackupError("Archive inconnue : manifest.json manquant (ce n'est pas une sauvegarde EVA).") from exc
    if manifest.get("app") != "eva" or manifest.get("format") != 1:
        raise BackupError("Version de sauvegarde non prise en charge.")
    tables = {}
    for t in TABLES:
        if t in OPTIONNELLES and f"db/{t}.json" not in z.namelist():
            tables[t] = []
            continue
        try:
            rows = json.loads(z.read(f"db/{t}.json"))
        except (KeyError, ValueError) as exc:
            raise BackupError(f"Table « {t} » absente ou illisible dans l'archive.") from exc
        if not isinstance(rows, list):
            raise BackupError(f"Table « {t} » invalide.")
        tables[t] = rows
    # Vérification des chemins avant toute écriture.
    root = _root()
    files = []
    for n in names:
        if not n.startswith("workspace/") or n.endswith("/"):
            continue
        rel = Path(n[len("workspace/"):])
        target = (root / rel).resolve()
        if rel.is_absolute() or ".." in rel.parts or root not in target.parents or "backups" in rel.parts:
            raise BackupError(f"Chemin refusé dans l'archive : {n}")
        files.append((n, target))
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("TRUNCATE " + ", ".join(reversed(TABLES)) + " RESTART IDENTITY CASCADE")
            for t in TABLES:
                if tables[t]:
                    await conn.execute(f"INSERT INTO {t} SELECT * FROM json_populate_recordset(null::{t}, $1::json)", json.dumps(tables[t]))
            for t in TABLES:
                has_id = await conn.fetchval(
                    "SELECT 1 FROM information_schema.columns WHERE table_name=$1 AND column_name='id' AND table_schema=current_schema()", t)
                seq = await conn.fetchval("SELECT pg_get_serial_sequence($1, 'id')", t) if has_id else None
                if seq:
                    await conn.execute(f"SELECT setval('{seq}', coalesce((SELECT max(id) FROM {t}), 0) + 1, false)")
    for n, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(n))
    return {"tables": {t: len(r) for t, r in tables.items()}, "files": len(files)}
