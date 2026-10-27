"""Auto-modification du code d'EVA, sous contrôle strict.

Principe : EVA PROPOSE (outil self_propose), l'utilisateur VALIDE (page Évolution / API).
- Les propositions ne touchent jamais au code en cours d'exécution ; elles sont stockées avec leur diff.
- Avant toute application : contrôle de syntaxe + import complet du code modifié dans un dossier temporaire.
- L'application écrit dans la copie vivante /eva-self/live (dépôt Git) et la commite ; EVA redémarre.
- Au démarrage, selfboot.py teste la copie ; si elle ne démarre pas, EVA revient au code de l'image.
- Retour arrière : `git revert` du commit de la proposition.
- Fichiers protégés : permissions, boucle d'exécution des outils, authentification, ce mécanisme.
  Une proposition qui les touche est refusée."""
import asyncio
import difflib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import get_pool

logger = logging.getLogger("eva-core.self")

ALLOWED_ROOTS = ("app/", "skills/", "seed_docs/")
ALLOWED_EXT = {".py", ".md", ".json", ".txt", ".yml", ".yaml"}
PROTECTED = {
    "app/harness/permissions.py",
    "app/harness/loop.py",
    "app/harness/tools/base.py",
    "app/harness/tools/terminal.py",
    "app/harness/tools/self_tools.py",
    "app/harness/registry.py",
    "app/self_mod.py",
    "app/routes_self.py",
    "app/main.py",
    "app/config.py",
    "app/db.py",
}
MAX_FILES = 10
MAX_FILE_BYTES = 200_000
MAX_PENDING = 10
CHECK_TIMEOUT = 90

# Hook de redémarrage (remplaçable dans les tests).
_restart_hook = None


class SelfModError(ValueError):
    pass


def self_dir() -> Path:
    return Path(os.getenv("EVA_SELF_DIR", "/eva-self"))


def live_dir() -> Path:
    return self_dir() / "live"


def enabled() -> bool:
    return (live_dir() / ".git").exists() and (live_dir() / "app").is_dir()


def _require_enabled() -> None:
    if not enabled():
        raise SelfModError(
            "L'auto-modification n'est pas active : le volume /eva-self est absent ou la copie du code n'est pas initialisée "
            "(volume « eva-self » de docker-compose.yml)."
        )


def _git(*args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-c", "user.name=EVA", "-c", "user.email=eva@local", *args],
        cwd=live_dir(), capture_output=True, text=True, timeout=60,
    )
    if check and r.returncode != 0:
        raise SelfModError(f"git {args[0]} a échoué : {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip()


def status() -> dict:
    sd = self_dir()
    out = {
        "enabled": enabled(),
        "running_from": os.getenv("EVA_CODE_MODE", "inconnu"),
        "protected": sorted(PROTECTED),
        "boot_error": None,
        "obsolete": None,
        "head": None,
    }
    try:
        if (sd / "boot_error.json").is_file():
            out["boot_error"] = json.loads((sd / "boot_error.json").read_text())
        if (sd / "obsolete.json").is_file():
            out["obsolete"] = json.loads((sd / "obsolete.json").read_text())
    except (OSError, ValueError):
        pass
    if out["enabled"]:
        try:
            out["head"] = _git("log", "-1", "--format=%h %s")
        except SelfModError:
            pass
    return out


def validate_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p or p.startswith("/") or ".." in p.split("/") or "\x00" in p:
        raise SelfModError(f"Chemin invalide : {path!r}")
    if not p.startswith(ALLOWED_ROOTS):
        raise SelfModError(f"Chemin hors des dossiers modifiables ({', '.join(ALLOWED_ROOTS)}) : {p}")
    if Path(p).suffix.lower() not in ALLOWED_EXT:
        raise SelfModError(f"Type de fichier non modifiable : {p}")
    if p in PROTECTED:
        raise SelfModError(f"Fichier protégé, jamais modifiable par EVA : {p}")
    return p


def read_live(path: str) -> str | None:
    p = live_dir() / path
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def list_tree(sub: str = "") -> list[str]:
    _require_enabled()
    root = live_dir()
    base = root / sub if sub else root
    if not base.resolve().is_relative_to(root.resolve()):
        raise SelfModError("Chemin invalide.")
    out = []
    for f in sorted(base.rglob("*")):
        if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts and f.suffix != ".pyc":
            out.append(f.relative_to(root).as_posix())
    return out


def _make_diff(files: dict) -> str:
    chunks = []
    for path, v in files.items():
        old = (v["old"] or "").splitlines(keepends=True)
        new = v["new"].splitlines(keepends=True)
        chunks.append("".join(difflib.unified_diff(old, new, f"a/{path}" if v["old"] is not None else "/dev/null", f"b/{path}")))
    return "\n".join(chunks)


def run_checks(files: dict) -> dict:
    """Copie le code vivant dans un dossier temporaire, y applique les fichiers proposés,
    vérifie la syntaxe et l'import de app.main dans un sous-processus."""
    tmp = Path(tempfile.mkdtemp(prefix="eva-selfcheck-"))
    try:
        for d in ("app", "skills", "seed_docs"):
            if (live_dir() / d).is_dir():
                shutil.copytree(live_dir() / d, tmp / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for path, v in files.items():
            dest = tmp / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(v["new"], encoding="utf-8")
        for path in files:
            if path.endswith(".py"):
                r = subprocess.run([sys.executable, "-m", "py_compile", str(tmp / path)], capture_output=True, text=True, timeout=CHECK_TIMEOUT)
                if r.returncode != 0:
                    return {"ok": False, "stage": "syntaxe", "output": (r.stderr or r.stdout)[-1500:]}
        env = {**os.environ, "PYTHONPATH": str(tmp), "EVA_WORKSPACE": str(tmp / "ws"), "EVA_SELF_DIR": str(tmp / "none")}
        r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=tmp, env=env, capture_output=True, text=True, timeout=CHECK_TIMEOUT)
        if r.returncode != 0:
            return {"ok": False, "stage": "import", "output": (r.stderr or r.stdout)[-1500:]}
        return {"ok": True, "stage": "import", "output": "Syntaxe et import corrects."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "délai", "output": "Contrôle trop long (délai dépassé)."}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def propose(title: str, rationale: str, new_files: dict) -> dict:
    _require_enabled()
    title, rationale = (title or "").strip(), (rationale or "").strip()
    if not title:
        raise SelfModError("Titre manquant.")
    if not isinstance(new_files, dict) or not new_files:
        raise SelfModError("Aucun fichier fourni (attendu : {chemin: contenu complet}).")
    if len(new_files) > MAX_FILES:
        raise SelfModError(f"Trop de fichiers ({MAX_FILES} maximum).")
    async with get_pool().acquire() as conn:
        pending = await conn.fetchval("SELECT count(*) FROM proposals WHERE status='pending'")
    if pending >= MAX_PENDING:
        raise SelfModError(f"{MAX_PENDING} propositions sont déjà en attente : traite-les d'abord.")
    files = {}
    for raw_path, content in new_files.items():
        path = validate_path(raw_path)
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise SelfModError(f"Contenu invalide ou trop gros pour {path}.")
        old = read_live(path)
        if old == content:
            raise SelfModError(f"Aucun changement pour {path}.")
        files[path] = {"old": old, "new": content}
    checks = await asyncio.to_thread(run_checks, files)
    status_ = "pending" if checks["ok"] else "failed_checks"
    diff = _make_diff(files)
    async with get_pool().acquire() as conn:
        pid = await conn.fetchval(
            "INSERT INTO proposals (title, rationale, files, diff, checks, status) VALUES ($1,$2,$3::jsonb,$4,$5::jsonb,$6) RETURNING id",
            title[:200], rationale[:2000], json.dumps(files), diff, json.dumps(checks), status_,
        )
    return {"id": pid, "status": status_, "checks": checks, "files": list(files), "diff_lines": diff.count("\n")}


def _row(r, full: bool = False) -> dict:
    d = {
        "id": r["id"], "title": r["title"], "rationale": r["rationale"], "status": r["status"],
        "commit_sha": r["commit_sha"], "created_at": r["created_at"].isoformat(),
        "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
        "files": list((r["files"] if isinstance(r["files"], dict) else json.loads(r["files"])).keys()),
        "checks": r["checks"] if isinstance(r["checks"], dict) else json.loads(r["checks"]),
    }
    if full:
        d["diff"] = r["diff"]
    return d


async def list_proposals() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM proposals ORDER BY id DESC LIMIT 100")
    return [_row(r) for r in rows]


async def get_proposal(pid: int) -> dict | None:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM proposals WHERE id=$1", pid)
    return _row(r, full=True) if r else None


def _schedule_restart() -> None:
    hook = _restart_hook
    if hook is not None:
        hook()
        return
    asyncio.get_running_loop().call_later(2.0, os._exit, 0)


async def apply(pid: int) -> dict:
    _require_enabled()
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM proposals WHERE id=$1", pid)
    if not r:
        raise SelfModError("Proposition introuvable.")
    if r["status"] != "pending":
        raise SelfModError(f"Cette proposition est « {r['status']} » : elle ne peut pas être appliquée.")
    files = r["files"] if isinstance(r["files"], dict) else json.loads(r["files"])
    for path, v in files.items():
        validate_path(path)
        if read_live(path) != v["old"]:
            raise SelfModError(f"Le fichier {path} a changé depuis la proposition : refuse-la et demande-en une nouvelle.")
    if _git("status", "--porcelain"):
        raise SelfModError("La copie du code contient des changements non commités : application refusée.")
    checks = await asyncio.to_thread(run_checks, files)
    if not checks["ok"]:
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE proposals SET checks=$2::jsonb, status='failed_checks' WHERE id=$1", pid, json.dumps(checks))
        raise SelfModError(f"Contrôles échoués ({checks['stage']}) : {checks['output'][-300:]}")
    for path, v in files.items():
        dest = live_dir() / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(v["new"], encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-q", "-m", f"Proposition #{pid} : {r['title']}")
    sha = _git("rev-parse", "--short", "HEAD")
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE proposals SET status='applied', commit_sha=$2, decided_at=now(), checks=$3::jsonb WHERE id=$1", pid, sha, json.dumps(checks))
    _schedule_restart()
    return {"ok": True, "commit": sha, "restarting": True}


async def reject(pid: int) -> None:
    async with get_pool().acquire() as conn:
        res = await conn.execute("UPDATE proposals SET status='rejected', decided_at=now() WHERE id=$1 AND status IN ('pending','failed_checks')", pid)
    if res.endswith(" 0"):
        raise SelfModError("Proposition introuvable ou déjà traitée.")


async def revert(pid: int) -> dict:
    _require_enabled()
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT status, commit_sha FROM proposals WHERE id=$1", pid)
    if not r or r["status"] != "applied" or not r["commit_sha"]:
        raise SelfModError("Seule une proposition appliquée peut être annulée.")
    if _git("status", "--porcelain"):
        raise SelfModError("La copie du code contient des changements non commités : annulation refusée.")
    res = subprocess.run(["git", "-c", "user.name=EVA", "-c", "user.email=eva@local", "revert", "--no-edit", r["commit_sha"]],
                         cwd=live_dir(), capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        _git("revert", "--abort", check=False)
        raise SelfModError("Annulation impossible (conflit avec des modifications plus récentes). Annule d'abord les plus récentes.")
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE proposals SET status='reverted', decided_at=now() WHERE id=$1", pid)
    _schedule_restart()
    return {"ok": True, "restarting": True}
