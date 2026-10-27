"""Historique des projets : une version est enregistrée (git) avant que EVA modifie un projet, puis après son intervention,
et à chaque enregistrement fait depuis la page Projets. On peut voir ce qui a changé, restaurer une version, ou annuler la dernière
modification d'EVA. L'historique est stocké HORS du dossier du projet (workspace/.eva-history/<projet>.git) : un ZIP déposé ne peut ni
l'écraser ni y planter de scripts."""
import contextvars
import os
import subprocess
import time
from pathlib import Path

from . import projects

BIG_FILE = 5 * 1024 * 1024
EXCLUDE = [".deps/", "__pycache__/", "node_modules/", ".venv/", "venv/", "*.pyc", ".git/"]
MAX_DIFF = 200_000
WS: Path | None = None
EVA, YOU = "EVA", "Toi"
_session: contextvars.ContextVar[dict | None] = contextvars.ContextVar("history_session", default=None)
_TOOLS_PATH = {"fs_write", "fs_append", "fs_delete", "fs_edit"}
_TOOLS_PROJECT = {"sandbox_run", "sandbox_install"}


class HistoryError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def configure(ws: Path) -> None:
    global WS
    WS = ws


def gitdir(ws: Path, slug: str) -> Path:
    return ws / ".eva-history" / f"{slug}.git"


def _git(ws: Path, slug: str, *args: str, author: str = YOU, check: bool = True) -> str:
    work = projects.project_dir(ws, slug)
    env = {**os.environ, "GIT_DIR": str(gitdir(ws, slug)), "GIT_WORK_TREE": str(work), "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": "eva@local",
           "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": "eva@local", "GIT_CONFIG_NOSYSTEM": "1", "HOME": os.environ.get("HOME", "/tmp"), "LC_ALL": "C.UTF-8"}
    cmd = ["git", "-c", "core.quotepath=off", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "safe.directory=*",
           "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args]
    r = subprocess.run(cmd, cwd=str(work), env=env, capture_output=True, text=True, timeout=120, errors="replace")
    if check and r.returncode != 0:
        raise HistoryError((r.stderr or r.stdout).strip()[:300] or "git a échoué")
    return r.stdout


def _init(ws: Path, slug: str) -> None:
    gd = gitdir(ws, slug)
    if (gd / "HEAD").exists():
        return
    gd.parent.mkdir(parents=True, exist_ok=True)
    _git(ws, slug, "init", "-q")


def _write_excludes(ws: Path, slug: str) -> None:
    work = projects.project_dir(ws, slug)
    big = []
    for p in work.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink() and p.stat().st_size > BIG_FILE and not any(x in (".deps", "node_modules") for x in p.relative_to(work).parts):
                big.append("/" + p.relative_to(work).as_posix())
        except OSError:
            continue
    info = gitdir(ws, slug) / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "exclude").write_text("\n".join(EXCLUDE + big) + "\n", encoding="utf-8")


def snapshot(ws: Path, slug: str, message: str, author: str = YOU) -> str | None:
    """Enregistre l'état actuel du projet s'il a changé ; renvoie l'identifiant de la version (ou None si rien n'a changé)."""
    _init(ws, slug)
    _write_excludes(ws, slug)
    _git(ws, slug, "add", "-A", "--", ".")
    if _git(ws, slug, "diff", "--cached", "--quiet", check=False) == "" and subprocess_ok(ws, slug):
        return None
    _git(ws, slug, "commit", "-q", "--allow-empty-message", "-m", message[:200] or "Version", author=author)
    return _git(ws, slug, "rev-parse", "HEAD").strip()


def subprocess_ok(ws: Path, slug: str) -> bool:
    """Vrai s'il n'y a rien à enregistrer (diff --cached --quiet renvoie 0)."""
    work = projects.project_dir(ws, slug)
    env = {**os.environ, "GIT_DIR": str(gitdir(ws, slug)), "GIT_WORK_TREE": str(work), "GIT_CONFIG_NOSYSTEM": "1"}
    has_head = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "--verify", "-q", "HEAD"], cwd=str(work), env=env, capture_output=True).returncode == 0
    if not has_head:
        # première version : rien à enregistrer seulement si aucun fichier n'est indexé
        return not _git(ws, slug, "ls-files").strip()
    return subprocess.run(["git", "-c", "safe.directory=*", "diff", "--cached", "--quiet"], cwd=str(work), env=env, capture_output=True).returncode == 0


def log(ws: Path, slug: str, limit: int = 60) -> list[dict]:
    if not (gitdir(ws, slug) / "HEAD").exists():
        return []
    out = _git(ws, slug, "log", f"-n{limit}", "--format=%H%x1f%an%x1f%at%x1f%s", check=False)
    items = []
    for line in out.splitlines():
        sha, author, at, msg = (line.split("\x1f") + ["", "", "", ""])[:4]
        items.append({"sha": sha, "short": sha[:7], "author": author, "time": int(at or 0), "message": msg})
    return items


def show(ws: Path, slug: str, sha: str) -> dict:
    _valid(sha)
    files = _git(ws, slug, "show", "--format=", "--name-status", "-M", sha)
    patch = _git(ws, slug, "show", "--format=", "-M", "--no-color", sha)
    return {"sha": sha, "files": [{"status": l[:1], "path": l.split("\t", 1)[1]} for l in files.splitlines() if "\t" in l],
            "diff": patch[:MAX_DIFF], "truncated": len(patch) > MAX_DIFF}


def _valid(sha: str) -> None:
    import re
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        raise HistoryError("Version invalide.")


def restore(ws: Path, slug: str, sha: str) -> dict:
    _valid(sha)
    if not (gitdir(ws, slug) / "HEAD").exists():
        raise HistoryError("Aucun historique.", 404)
    msg = _git(ws, slug, "log", "-1", "--format=%s", sha, check=False).strip()
    if not msg and _git(ws, slug, "cat-file", "-t", sha, check=False).strip() != "commit":
        raise HistoryError("Version introuvable.", 404)
    snapshot(ws, slug, "Avant restauration")
    target = {p for p in _git(ws, slug, "ls-tree", "-r", "--name-only", "-z", sha).split("\0") if p}
    work = projects.project_dir(ws, slug)
    for p in _git(ws, slug, "ls-files", "-z").split("\0"):
        if p and p not in target:
            f = work / p
            f.unlink(missing_ok=True)
            d = f.parent
            while d != work and d.is_dir() and not any(d.iterdir()):
                d.rmdir(); d = d.parent
    if target:
        _git(ws, slug, "checkout", sha, "--", ".")
    new = snapshot(ws, slug, f"Restauré : {msg}"[:200])
    return {"restored": sha, "sha": new}


def undo_eva(ws: Path, slug: str) -> dict:
    for e in log(ws, slug, 200):
        if e["author"] == EVA:
            parent = _git(ws, slug, "rev-parse", "--verify", "-q", f"{e['sha']}^", check=False).strip()
            if not parent:
                raise HistoryError("Rien avant cette modification d'EVA.", 404)
            res = restore(ws, slug, parent)
            return {**res, "undone": e["message"]}
    raise HistoryError("Aucune modification d'EVA à annuler.", 404)


def purge(ws: Path, slug: str) -> None:
    import shutil
    shutil.rmtree(gitdir(ws, slug), ignore_errors=True)


# ---- intégration au Harness : version « avant » au premier changement d'EVA dans un projet, version « après » en fin d'intervention
def _slug_of(name: str, args: dict) -> str | None:
    if name in _TOOLS_PATH:
        parts = Path(str(args.get("path", "")).replace("\\", "/")).parts
        if len(parts) >= 2 and parts[0] == "projets":
            return parts[1]
    elif name in _TOOLS_PROJECT:
        return projects.slugify(str(args.get("project", ""))) or None
    return None


def begin() -> contextvars.Token:
    return _session.set({})


def before_tool(name: str, args: dict) -> None:
    sess = _session.get()
    if sess is None or WS is None:
        return
    try:
        slug = _slug_of(name, args)
        if not slug or slug in sess:
            return
        projects.project_dir(WS, slug)
        sess[slug] = True
        snapshot(WS, slug, f"Avant EVA : {name}", YOU)
    except Exception:  # noqa: BLE001 — l'historique ne doit jamais empêcher un outil de travailler
        pass


def finish(sess: dict, request: str) -> None:
    """Version « après » de chaque projet que EVA a modifié pendant l'intervention."""
    if not sess or WS is None:
        return
    label = " ".join((request or "").split())[:80] or "intervention"
    for slug in sess:
        try:
            snapshot(WS, slug, f"EVA : {label}", EVA)
        except Exception:  # noqa: BLE001
            pass


def current() -> dict:
    return _session.get() or {}


def end(token: contextvars.Token) -> dict:
    """À appeler dans le même contexte que begin() ; renvoie les projets touchés."""
    sess = dict(_session.get() or {})
    _session.reset(token)
    return sess
