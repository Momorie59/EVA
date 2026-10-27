"""Projets d'EVA : dossiers du workspace (projets/<slug>) qu'on peut créer, supprimer, remplir de fichiers et modifier
depuis l'interface — et dans lesquels EVA travaille avec ses propres outils (mêmes fichiers, donc modifications visibles en direct)."""
import hashlib
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from .scenes import fold
from .uploads import safe_extract_zip

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,48}$")
HIDDEN = {".deps", "__pycache__", "node_modules", ".git", ".pytest_cache", ".mypy_cache", ".venv"}
MAX_READ = 1_000_000
MAX_WRITE = 2_000_000
MAX_ENTRIES = 3000
MAX_UPLOAD_MB = 200


class ProjectError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", fold(name).strip().lower()).strip("-._")
    return s[:48]


def root(ws: Path) -> Path:
    return ws / "projets"


def project_dir(ws: Path, slug: str) -> Path:
    if not SLUG_RE.match(slug or ""):
        raise ProjectError("Nom de projet invalide.")
    p = root(ws) / slug
    if not p.is_dir():
        raise ProjectError("Projet introuvable.", 404)
    return p


def resolve(ws: Path, slug: str, rel: str = "") -> Path:
    base = project_dir(ws, slug).resolve()
    target = (base / (rel or "")).resolve()
    if target != base and base not in target.parents:
        raise ProjectError("Chemin hors du projet refusé.")
    return target


def _visible(parts) -> bool:
    return not any(p in HIDDEN for p in parts)


def _title(folder: Path) -> tuple[str, str]:
    name, desc = folder.name, ""
    readme = folder / "README.md"
    if readme.is_file():
        lines = [l.strip() for l in readme.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        if lines and lines[0].startswith("#"):
            name = lines[0].lstrip("# ").strip() or name
        desc = next((l for l in lines[1:] if not l.startswith("#")), "")
    return name, desc[:200]


def stats(folder: Path) -> dict:
    count, size, latest = 0, 0, folder.stat().st_mtime
    for p in folder.rglob("*"):
        rel = p.relative_to(folder).parts
        if not _visible(rel) or not p.is_file():
            continue
        st = p.stat()
        count += 1
        size += st.st_size
        latest = max(latest, st.st_mtime)
        if count > 20000:
            break
    return {"files": count, "size": size, "mtime": latest}


def list_projects(ws: Path) -> list[dict]:
    out = []
    r = root(ws)
    if not r.is_dir():
        return out
    for d in sorted(r.iterdir()):
        if d.is_dir() and SLUG_RE.match(d.name):
            name, desc = _title(d)
            out.append({"slug": d.name, "name": name, "description": desc, "deps": (d / ".deps").is_dir(), **stats(d)})
    return out


def create(ws: Path, name: str, description: str = "") -> dict:
    slug = slugify(name)
    if not slug or not SLUG_RE.match(slug):
        raise ProjectError("Donne un nom au projet (lettres, chiffres, tirets).")
    folder = root(ws) / slug
    if folder.exists():
        raise ProjectError(f"Le projet « {slug} » existe déjà.", 409)
    folder.mkdir(parents=True)
    title = name.strip()[:80] or slug
    (folder / "README.md").write_text(f"# {title}\n\n{description.strip()}\n\n## Statut\n\nEn cours.\n", encoding="utf-8")
    return {"slug": slug}


def delete(ws: Path, slug: str) -> None:
    folder = project_dir(ws, slug)
    shutil.rmtree(folder)


def tree(ws: Path, slug: str) -> dict:
    base = project_dir(ws, slug)
    items, h = [], hashlib.sha1()
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if not _visible(rel.parts):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        isdir = p.is_dir()
        items.append({"path": rel.as_posix(), "dir": isdir, "size": 0 if isdir else st.st_size, "mtime": st.st_mtime})
        h.update(f"{rel.as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
        if len(items) >= MAX_ENTRIES:
            break
    return {"rev": h.hexdigest()[:16], "items": items, "truncated": len(items) >= MAX_ENTRIES}


def read_file(ws: Path, slug: str, rel: str) -> dict:
    p = resolve(ws, slug, rel)
    if not p.is_file():
        raise ProjectError("Fichier introuvable.", 404)
    st = p.stat()
    if st.st_size > MAX_READ:
        return {"path": rel, "binary": True, "size": st.st_size, "mtime_ns": str(st.st_mtime_ns), "reason": "trop gros pour l'éditeur"}
    data = p.read_bytes()
    if b"\x00" in data[:8192]:
        return {"path": rel, "binary": True, "size": st.st_size, "mtime_ns": str(st.st_mtime_ns), "reason": "fichier binaire"}
    return {"path": rel, "binary": False, "content": data.decode("utf-8", errors="replace"), "size": st.st_size, "mtime_ns": str(st.st_mtime_ns)}


def write_file(ws: Path, slug: str, rel: str, content: str, base_mtime_ns: int | str | None = None) -> dict:
    # Les horodatages en nanosecondes dépassent 2^53 : transmis en texte pour ne pas perdre de précision côté navigateur.
    if not rel or rel.endswith("/"):
        raise ProjectError("Nom de fichier manquant.")
    p = resolve(ws, slug, rel)
    if any(part in HIDDEN for part in Path(rel).parts):
        raise ProjectError("Dossier réservé.")
    if len(content.encode("utf-8")) > MAX_WRITE:
        raise ProjectError("Fichier trop gros pour l'éditeur (2 Mo maximum).", 413)
    if p.is_dir():
        raise ProjectError("C'est un dossier.")
    if base_mtime_ns is not None and p.exists() and p.stat().st_mtime_ns != int(base_mtime_ns):
        raise ProjectError("Le fichier a été modifié ailleurs (par EVA ou par le partage) depuis que tu l'as ouvert.", 409)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": rel, "mtime_ns": str(p.stat().st_mtime_ns), "size": p.stat().st_size}


def mkdir(ws: Path, slug: str, rel: str) -> None:
    if not rel:
        raise ProjectError("Nom de dossier manquant.")
    resolve(ws, slug, rel).mkdir(parents=True, exist_ok=True)


def delete_path(ws: Path, slug: str, rel: str) -> None:
    if not rel:
        raise ProjectError("Chemin manquant.")
    p = resolve(ws, slug, rel)
    if not p.exists():
        raise ProjectError("Introuvable.", 404)
    shutil.rmtree(p) if p.is_dir() else p.unlink()


def move(ws: Path, slug: str, src: str, dst: str) -> None:
    a, b = resolve(ws, slug, src), resolve(ws, slug, dst)
    if not src or not dst or not a.exists():
        raise ProjectError("Introuvable.", 404)
    if b.exists():
        raise ProjectError("La destination existe déjà.", 409)
    b.parent.mkdir(parents=True, exist_ok=True)
    a.rename(b)


def clean_filename(name: str) -> str:
    n = Path(name.replace("\\", "/")).name.strip().replace("\x00", "")
    return n[:150] or "fichier"


def extract_zip_into(ws: Path, slug: str, zip_path: Path, rel: str = "") -> list[str]:
    dest = resolve(ws, slug, rel)
    dest.mkdir(parents=True, exist_ok=True)
    return safe_extract_zip(zip_path, dest)


def make_zip(ws: Path, slug: str) -> Path:
    base = project_dir(ws, slug)
    tmp = Path(tempfile.mkstemp(prefix=f"{slug}_", suffix=".zip")[1])
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base)
            if p.is_file() and _visible(rel.parts):
                z.write(p, f"{slug}/{rel.as_posix()}")
    return tmp


# ---- corbeille : un projet supprimé reste récupérable 30 jours (sa base de test, elle, n'est pas conservée)
TRASH = ".corbeille"
TRASH_DAYS = 30
TRASH_ID = re.compile(r"^([a-z0-9][a-z0-9._-]{0,48})__(\d{9,12})$")


def _trash_root(ws: Path) -> Path:
    return root(ws) / TRASH


def trash(ws: Path, slug: str) -> str:
    folder = project_dir(ws, slug)
    stamp = int(time.time())
    _trash_root(ws).mkdir(parents=True, exist_ok=True)
    while (_trash_root(ws) / f"{slug}__{stamp}").exists():
        stamp += 1
    tid = f"{slug}__{stamp}"
    folder.rename(_trash_root(ws) / tid)
    return tid


def list_trash(ws: Path) -> list[dict]:
    out, tr = [], _trash_root(ws)
    if not tr.is_dir():
        return out
    for d in sorted(tr.iterdir(), reverse=True):
        m = TRASH_ID.match(d.name)
        if not (m and d.is_dir()):
            continue
        at = int(m.group(2))
        if time.time() - at > TRASH_DAYS * 86400:
            shutil.rmtree(d, ignore_errors=True)
            continue
        out.append({"id": d.name, "slug": m.group(1), "deleted_at": at, "days_left": max(0, TRASH_DAYS - int((time.time() - at) // 86400)), **stats(d)})
    return out


def _trash_dir(ws: Path, tid: str) -> Path:
    if not TRASH_ID.match(tid or ""):
        raise ProjectError("Élément invalide.")
    d = _trash_root(ws) / tid
    if not d.is_dir():
        raise ProjectError("Introuvable dans la corbeille.", 404)
    return d


def restore_trash(ws: Path, tid: str) -> str:
    d = _trash_dir(ws, tid)
    slug = TRASH_ID.match(tid).group(1)
    if (root(ws) / slug).exists():
        raise ProjectError(f"Un projet « {slug} » existe déjà : renomme-le ou supprime-le d'abord.", 409)
    d.rename(root(ws) / slug)
    return slug


def purge_trash(ws: Path, tid: str) -> str:
    d = _trash_dir(ws, tid)
    shutil.rmtree(d)
    return TRASH_ID.match(tid).group(1)
