"""Outils « développeur » : explorer un projet, chercher dans le code, modifier un fichier par remplacement ciblé,
vérifier la syntaxe, livrer le résultat en ZIP. Même démarche qu'un assistant de code : lire avant d'écrire, petites modifications."""
import fnmatch
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from ..permissions import Permission
from .base import Tool
from .filesystem import WorkspaceError, _is_sensitive_path, _resolve_in_workspace
from ... import changes as journal

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".cache"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar", ".7z", ".woff", ".woff2", ".ttf", ".onnx", ".bin",
              ".so", ".pyc", ".mp3", ".mp4", ".wav", ".wasm", ".sqlite", ".db", ".docx", ".xlsx", ".pptx"}
MAX_GREP_FILE = 1_000_000


def _walk(root: Path):
    """Parcourt un dossier du workspace sans jamais suivre un lien symbolique (un lien vers /etc ou vers les fichiers
    d'une autre personne ne doit être ni lu, ni cherché, ni archivé)."""
    base = root.resolve()
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or any((root / q).is_symlink() for q in p.relative_to(root).parents if str(q) != ".") \
                or (base not in p.resolve().parents and p.resolve() != base):
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]) or (p.is_dir() and p.name in SKIP_DIRS):
            continue
        yield p


class FsTreeTool(Tool):
    name = "fs_tree"
    description = ("Arborescence d'un dossier du workspace (récursive, sans node_modules/.git), avec la taille des fichiers. "
                   "À utiliser en premier pour comprendre la structure d'un projet ou d'une archive déposée.")
    parameters = {"type": "object", "properties": {
        "path": {"type": "string", "description": "Dossier relatif au workspace (ex. uploads/projet_extrait)"},
        "depth": {"type": "integer", "description": "Profondeur maximale (défaut 3)"}}, "required": ["path"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str = ".", depth: int = 3, **_: Any) -> dict:
        try:
            root = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        if not root.is_dir():
            return {"error": f"Ce n'est pas un dossier : {path}"}
        depth = max(1, min(int(depth or 3), 8))
        lines, total = [], 0
        for p in _walk(root):
            rel = p.relative_to(root)
            if len(rel.parts) > depth:
                continue
            total += 1
            if len(lines) < 400:
                lines.append(("  " * (len(rel.parts) - 1)) + rel.name + ("/" if p.is_dir() else f"  ({p.stat().st_size} o)"))
        return {"path": path, "entries": total, "tree": "\n".join(lines), "truncated": total > len(lines)}


class FsGrepTool(Tool):
    name = "fs_grep"
    description = ("Cherche une expression régulière dans les fichiers texte d'un dossier du workspace ; renvoie fichier:ligne:texte. "
                   "À utiliser pour retrouver une fonction, une variable, un message avant de modifier le code.")
    parameters = {"type": "object", "properties": {
        "pattern": {"type": "string", "description": "Expression régulière (ou simple mot)"},
        "path": {"type": "string", "description": "Dossier ou fichier de départ (défaut '.')"},
        "glob": {"type": "string", "description": "Filtre de noms, ex. *.py ou *.jsx"},
        "ignore_case": {"type": "boolean"}}, "required": ["pattern"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, pattern: str = "", path: str = ".", glob: str = "", ignore_case: bool = True, **_: Any) -> dict:
        try:
            root = _resolve_in_workspace(self.workspace_root, path)
            rx = re.compile(pattern, re.I if ignore_case else 0)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        except re.error as exc:
            return {"error": f"Expression invalide : {exc}"}
        files = [root] if root.is_file() else [p for p in _walk(root) if p.is_file()]
        hits, scanned = [], 0
        for f in files:
            if f.suffix.lower() in BINARY_EXT or (glob and not fnmatch.fnmatch(f.name, glob)):
                continue
            try:
                if f.stat().st_size > MAX_GREP_FILE:
                    continue
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scanned += 1
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f.relative_to(self.workspace_root).as_posix()}:{n}: {line.strip()[:200]}")
                    if len(hits) >= 80:
                        return {"matches": hits, "scanned_files": scanned, "truncated": True}
        return {"matches": hits, "scanned_files": scanned, "truncated": False}


class FsEditTool(Tool):
    name = "fs_edit"
    description = ("Modifie un fichier par remplacement exact : 'old' (texte actuel, copié tel quel depuis fs_read, assez long pour être unique) "
                   "devient 'new'. Préfère cet outil à fs_write pour changer du code existant : petites modifications, le reste du fichier intact. "
                   "Chaque modification est annulable depuis le journal.")
    parameters = {"type": "object", "properties": {
        "path": {"type": "string", "description": "Fichier relatif au workspace"},
        "old": {"type": "string", "description": "Texte exact à remplacer"},
        "new": {"type": "string", "description": "Nouveau texte"},
        "replace_all": {"type": "boolean", "description": "Remplacer toutes les occurrences (sinon 'old' doit être unique)"}},
        "required": ["path", "old", "new"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def permission_for(self, args: dict) -> Permission:
        return Permission.CONFIRM if _is_sensitive_path(args.get("path", "")) else Permission.AUTO

    async def execute(self, path: str = "", old: str = "", new: str = "", replace_all: bool = False, **_: Any) -> dict:
        try:
            target = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        if not target.is_file():
            return {"error": f"Fichier introuvable : {path}"}
        if not old:
            return {"error": "'old' est vide : donne le texte exact à remplacer (ou utilise fs_write pour créer un fichier)."}
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"error": f"Lecture impossible : {exc}"}
        count = text.count(old)
        if count == 0:
            return {"error": "Texte introuvable : relis le fichier avec fs_read et recopie 'old' exactement (espaces et retours à la ligne compris)."}
        if count > 1 and not replace_all:
            return {"error": f"'old' apparaît {count} fois : ajoute des lignes autour pour le rendre unique, ou mets replace_all=true."}
        before = journal.snapshot(target)
        try:
            target.write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1), encoding="utf-8")
        except OSError as exc:
            return {"error": f"Écriture impossible : {exc}"}
        await journal.record(self.workspace_root, target, "fs_edit", before)
        return {"path": path, "replaced": count if replace_all else 1}


class DevCheckTool(Tool):
    name = "dev_check"
    description = ("Vérifie la syntaxe d'un fichier ou d'un dossier SANS l'exécuter (Python, JSON). À lancer après chaque série de modifications ; "
                   "pour lancer les tests du projet, utilise terminal_run.")
    parameters = {"type": "object", "properties": {"path": {"type": "string", "description": "Fichier ou dossier relatif au workspace"}}, "required": ["path"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str = ".", **_: Any) -> dict:
        try:
            root = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        files = [root] if root.is_file() else [p for p in _walk(root) if p.is_file()]
        checked, errors = 0, []
        for f in files:
            ext = f.suffix.lower()
            if ext not in (".py", ".json"):
                continue
            try:
                src = f.read_text(encoding="utf-8")
                checked += 1
                if ext == ".py":
                    compile(src, str(f), "exec")
                else:
                    json.loads(src)
            except SyntaxError as exc:
                errors.append(f"{f.relative_to(self.workspace_root).as_posix()}:{exc.lineno}: {exc.msg}")
            except (ValueError, UnicodeDecodeError, OSError) as exc:
                errors.append(f"{f.relative_to(self.workspace_root).as_posix()}: {exc}")
        return {"checked_files": checked, "ok": not errors, "errors": errors[:30]}


class ZipMakeTool(Tool):
    name = "zip_make"
    description = ("Emballe un dossier (ou un fichier) du workspace dans une archive ZIP et la met à disposition en téléchargement dans l'interface. "
                   "À utiliser à la fin d'un travail sur du code pour livrer le résultat.")
    parameters = {"type": "object", "properties": {
        "path": {"type": "string", "description": "Dossier ou fichier à archiver, relatif au workspace"},
        "name": {"type": "string", "description": "Nom du ZIP (ex. projet-modifie.zip)"}}, "required": ["path"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, path: str = ".", name: str = "", **_: Any) -> dict:
        try:
            src = _resolve_in_workspace(self.workspace_root, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        if not src.exists():
            return {"error": f"Introuvable : {path}"}
        out_dir = self.workspace_root / "exports"
        out_dir.mkdir(exist_ok=True)
        base = re.sub(r"[^\w.\- ]", "_", name or f"{src.name or 'workspace'}.zip")[:100]
        if not base.lower().endswith(".zip"):
            base += ".zip"
        out = out_dir / base
        if src.resolve() == self.workspace_root.resolve():
            return {"error": "Précise un sous-dossier : le workspace entier n'est pas archivé."}
        n = 0
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            if src.is_file():
                z.write(src, src.name); n = 1
            else:
                for p in _walk(src):
                    if p.is_file() and out_dir not in p.parents:
                        z.write(p, p.relative_to(src).as_posix()); n += 1
        rel = out.relative_to(self.workspace_root).as_posix()
        return {"path": rel, "files": n, "size_bytes": out.stat().st_size, "download": f"/api/files/download?path={rel}"}


class FileDeliverTool(Tool):
    name = "file_deliver"
    description = ("Crée un fichier (script shell .sh, Python, texte, config…) ou une archive ZIP de plusieurs fichiers que tu viens d'écrire, et le met à disposition en "
                   "téléchargement dans l'interface. Donne soit `name` + `content` (un seul fichier), soit `files` (liste de {path, content}) + `zip_name` (une archive). "
                   "Les scripts .sh reçoivent automatiquement `#!/bin/bash` et sont exécutables. Ce que tu livres est du texte : explique en une phrase comment le lancer.")
    parameters = {"type": "object", "properties": {
        "name": {"type": "string", "description": "Nom du fichier (ex. sauvegarde.sh)"},
        "content": {"type": "string", "description": "Contenu complet du fichier"},
        "files": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
                  "description": "Plusieurs fichiers à emballer dans un ZIP (chemins relatifs, ex. projet/run.sh)"},
        "zip_name": {"type": "string", "description": "Nom du ZIP (ex. mon-outil.zip)"}}}
    permission = Permission.AUTO
    MAX_BYTES = 2_000_000

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    @staticmethod
    def _safe_name(n: str) -> str:
        n = Path(str(n or "").replace("\\", "/")).name
        return re.sub(r"[^\w.\- ]", "_", n).strip(". ")[:100]

    @staticmethod
    def _text(name: str, content: str) -> bytes:
        text = str(content).replace("\r\n", "\n")
        if name.lower().endswith((".sh", ".bash")) and not text.startswith("#!"):
            text = "#!/bin/bash\n" + text
        if not text.endswith("\n"):
            text += "\n"
        return text.encode("utf-8")

    @staticmethod
    def _rel_path(p: str) -> str | None:
        parts = [x for x in str(p or "").replace("\\", "/").split("/") if x not in ("", ".")]
        if not parts or ".." in parts or len(parts) > 8:
            return None
        return "/".join(re.sub(r"[^\w.\- ]", "_", x)[:80] for x in parts)

    async def execute(self, name: str = "", content: str = "", files: list | None = None, zip_name: str = "", **_: Any) -> dict:
        out_dir = self.workspace_root / "exports"
        out_dir.mkdir(exist_ok=True)
        if files:
            entries: list[tuple[str, bytes]] = []
            for f in files[:200]:
                rel = self._rel_path(f.get("path", "")) if isinstance(f, dict) else None
                if not rel:
                    return {"error": f"Chemin invalide : {f.get('path') if isinstance(f, dict) else f}"}
                entries.append((rel, self._text(rel, f.get("content", ""))))
            if sum(len(b) for _, b in entries) > self.MAX_BYTES:
                return {"error": "Contenu trop gros (2 Mo maximum)."}
            base = self._safe_name(zip_name or "archive-eva.zip") or "archive-eva.zip"
            if not base.lower().endswith(".zip"):
                base += ".zip"
            out = out_dir / base
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                for rel, data in entries:
                    zi = zipfile.ZipInfo(rel, date_time=(2020, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = ((0o755 if rel.lower().endswith((".sh", ".bash", ".py")) else 0o644) << 16)
                    z.writestr(zi, data)
            n = len(entries)
        else:
            fname = self._safe_name(name)
            if not fname or not content:
                return {"error": "Donne le nom du fichier et son contenu (ou une liste `files` pour un ZIP)."}
            data = self._text(fname, content)
            if len(data) > self.MAX_BYTES:
                return {"error": "Contenu trop gros (2 Mo maximum)."}
            out = out_dir / fname
            out.write_bytes(data)
            if fname.lower().endswith((".sh", ".bash", ".py")):
                out.chmod(0o755)
            n = 1
        rel = out.relative_to(self.workspace_root).as_posix()
        return {"path": rel, "files": n, "size_bytes": out.stat().st_size, "download": f"/api/files/download?path={rel}"}
