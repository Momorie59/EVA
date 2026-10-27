"""Point d'entrée d'EVA CORE : choisit le code à lancer, puis démarre uvicorn.

- Sans volume /eva-self : lance le code de l'image (/app), comme avant.
- Avec le volume : maintient une copie « vivante » du code dans /eva-self/live (dépôt Git).
  Les modifications validées par l'utilisateur y sont commitées. Au démarrage, la copie
  vivante est testée (import de app.main) ; si elle est cassée, EVA retombe sur le code de
  l'image et note l'erreur dans /eva-self/boot_error.json — une modification ne peut donc
  jamais empêcher EVA de démarrer.
- Si l'image a été reconstruite avec une nouvelle version d'EVA, l'ancienne copie vivante est
  archivée (/eva-self/archive-<date>), remplacée par le nouveau code de base, puis les modifications
  d'EVA y sont rejouées (celles qui ne s'appliquent plus proprement sont laissées de côté et notées) :
  ce qu'EVA a appris à faire survit aux mises à jour.

Uniquement la bibliothèque standard : ce fichier ne dépend pas du code qu'il lance."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CODE_DIRS = ("app", "skills", "seed_docs")
EXTRA_FILES = ("requirements.txt",)
IMPORT_TIMEOUT = 120


def self_dir() -> Path:
    return Path(os.getenv("EVA_SELF_DIR", "/eva-self"))


def _ignore(_dir, names):
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]


def fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for d in CODE_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                h.update(f.relative_to(root).as_posix().encode())
                h.update(f.read_bytes())
    for name in EXTRA_FILES:
        if (root / name).is_file():
            h.update((root / name).read_bytes())
    return h.hexdigest()


def _git(live: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=EVA", "-c", "user.email=eva@local", *args],
        cwd=live, capture_output=True, text=True, timeout=60,
    )


def seed(live: Path, base: Path = APP_DIR) -> None:
    live.mkdir(parents=True)
    for d in CODE_DIRS:
        if (base / d).is_dir():
            shutil.copytree(base / d, live / d, ignore=_ignore)
    for name in EXTRA_FILES:
        if (base / name).is_file():
            shutil.copyfile(base / name, live / name)
    _git(live, "init", "-q", "-b", "main")
    _git(live, "add", "-A")
    _git(live, "commit", "-q", "-m", "Code de base d'EVA")
    (live.parent / "base.json").write_text(json.dumps({"fingerprint": fingerprint(base), "seeded_at": time.time()}))


def replay(archive: Path, live: Path) -> dict:
    """Rejoue sur le nouveau code de base les commits d'EVA faits dans l'ancienne copie (sauf le commit de base)."""
    r = _git(archive, "rev-list", "--reverse", "HEAD")
    commits = r.stdout.split()[1:] if r.returncode == 0 else []
    reportees, laissees = [], []
    for sha in commits:
        titre = _git(archive, "log", "-1", "--format=%s", sha).stdout.strip()
        patch = _git(archive, "format-patch", "-1", "--stdout", sha).stdout
        a = subprocess.run(["git", "-c", "user.name=EVA", "-c", "user.email=eva@local", "am", "-q", "--3way"],
                           cwd=live, input=patch, capture_output=True, text=True, timeout=60)
        if a.returncode == 0:
            reportees.append(titre)
        else:
            _git(live, "am", "--abort")
            laissees.append(titre)
    return {"reportees": reportees, "laissees": laissees}


def import_check(code_root: Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONPATH": str(code_root), "EVA_WORKSPACE": str(Path(os.getenv("TMPDIR", "/tmp")) / "eva-bootcheck")}
    try:
        r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=code_root, env=env,
                           capture_output=True, text=True, timeout=IMPORT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "Délai dépassé pendant l'import du code."
    return r.returncode == 0, (r.stderr or r.stdout)[-2000:]


def choose_code_dir(base: Path = APP_DIR) -> tuple[Path, str]:
    sd = self_dir()
    if not sd.is_dir() or not os.access(sd, os.W_OK):
        return base, "base (auto-modification désactivée : pas de volume)"
    live = sd / "live"
    meta = sd / "base.json"
    fp = fingerprint(base)
    if live.exists():
        try:
            same = json.loads(meta.read_text()).get("fingerprint") == fp
        except (OSError, ValueError):
            same = False
        if not same:
            name = f"archive-{time.strftime('%Y%m%d-%H%M%S')}"
            live.rename(sd / name)
            seed(live, base)
            info = {"archived": name, "at": time.time(), "reportees": [], "laissees": []}
            try:
                info.update(replay(sd / name, live))
                if info["reportees"] and not import_check(live)[0]:   # l'ensemble ne démarre plus : nouveau code seul
                    shutil.rmtree(live)
                    seed(live, base)
                    info["laissees"] += info["reportees"]
                    info["reportees"] = []
            except Exception as exc:  # noqa: BLE001 — jamais bloquant
                info["erreur"] = str(exc)[:300]
            (sd / "obsolete.json").write_text(json.dumps(info))
    if not live.exists():
        seed(live, base)
    ok, err = import_check(live)
    boot_err = sd / "boot_error.json"
    if ok:
        boot_err.unlink(missing_ok=True)
        return live, "live"
    boot_err.write_text(json.dumps({"at": time.time(), "error": err}))
    return base, "base (la copie modifiée ne démarre pas)"


def main() -> None:
    target, label = choose_code_dir()
    print(f"[selfboot] code lancé : {target} — {label}", flush=True)
    os.chdir(target)
    env = {**os.environ, "PYTHONPATH": str(target), "EVA_CODE_ROOT": str(target), "EVA_CODE_MODE": "live" if label == "live" else "base"}
    os.execvpe(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], env)


if __name__ == "__main__":
    main()
