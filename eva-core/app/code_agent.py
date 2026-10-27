"""Agent de code gratuit : Aider (Apache-2.0, https://aider.chat) piloté par EVA, avec les modèles locaux d'Ollama.

EVA lui confie une consigne sur un de tes projets (projets/<slug>) : Aider lit le code, modifie les fichiers et enregistre
chaque modification dans git. EVA renvoie le résumé (commits, fichiers touchés, diff) : tout s'annule avec git.

Aider pèse ~650 Mo : il n'est pas dans l'image d'EVA mais installé une fois, à la demande de l'administrateur
(Paramètres › Intelligence › Agent de code), dans le workspace (.outils/aider) — il survit donc aux mises à jour.
Garde-fous : un seul travail à la fois, durée limitée, aucune commande shell proposée par Aider n'est exécutée,
pas d'accès au web, seulement le dossier du projet."""
import asyncio
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .config import settings

VERSION = os.getenv("EVA_AIDER_VERSION", "0.86.2")
DUREE_MAX = int(os.getenv("EVA_AIDER_TIMEOUT", "900"))
MAX_DIFF = 8000
_verrou = asyncio.Lock()
_installation: dict = {"en_cours": False, "erreur": ""}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def dossier(workspace: Path) -> Path:
    return Path(workspace) / ".outils" / "aider"


def binaire(workspace: Path) -> Path:
    return dossier(workspace) / "bin" / "aider"


def _journal(workspace: Path) -> Path:
    return Path(workspace) / ".outils" / "aider-installation.log"


def statut(workspace: Path) -> dict:
    b = binaire(workspace)
    j = _journal(workspace)
    fin = ""
    if j.is_file():
        fin = "\n".join(j.read_text(errors="replace").splitlines()[-8:])
    return {"installe": b.is_file(), "version": VERSION, "en_cours": _installation["en_cours"], "erreur": _installation["erreur"],
            "travail_en_cours": _verrou.locked(), "journal": fin}


async def _cmd(args: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 900, journal: Path | None = None) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*args, cwd=str(cwd) if cwd else None, env=env,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        await p.wait()
        return 124, f"Délai dépassé ({timeout} s)."
    texte = out.decode(errors="replace")
    if journal:
        with journal.open("a") as f:
            f.write(texte)
    return p.returncode or 0, texte


async def installer(workspace: Path) -> None:
    """Crée le venv et installe Aider (quelques minutes). Appelée en tâche de fond."""
    if _installation["en_cours"]:
        return
    _installation.update(en_cours=True, erreur="")
    d = dossier(workspace)
    j = _journal(workspace)
    try:
        j.parent.mkdir(parents=True, exist_ok=True)
        j.write_text(f"Installation d'Aider {VERSION}…\n")
        if d.exists():
            shutil.rmtree(d)
        code, out = await _cmd([sys.executable, "-m", "venv", str(d)], journal=j)
        if code:
            raise RuntimeError(f"venv : {out[-300:]}")
        code, out = await _cmd([str(d / "bin" / "pip"), "install", "--no-cache-dir", "--disable-pip-version-check", f"aider-chat=={VERSION}"],
                               timeout=1800, journal=j)
        if code or not binaire(workspace).is_file():
            raise RuntimeError(f"pip : {out[-400:]}")
        with j.open("a") as f:
            f.write("\nAgent de code installé.\n")
    except Exception as e:  # noqa: BLE001
        _installation["erreur"] = str(e)[:500]
        shutil.rmtree(d, ignore_errors=True)
    finally:
        _installation["en_cours"] = False


def _git_env() -> dict:
    return {**os.environ, "GIT_AUTHOR_NAME": "EVA", "GIT_AUTHOR_EMAIL": "eva@localhost",
            "GIT_COMMITTER_NAME": "EVA", "GIT_COMMITTER_EMAIL": "eva@localhost", "GIT_TERMINAL_PROMPT": "0"}


async def _git(proj: Path, *args: str) -> tuple[int, str]:
    return await _cmd(["git", "-c", "safe.directory=*", *args], cwd=proj, env=_git_env(), timeout=60)


async def _preparer_git(proj: Path) -> str:
    """Le projet devient un dépôt git (si besoin) et son état actuel est enregistré : la modification de l'agent est isolée."""
    if not (proj / ".git").exists():
        await _git(proj, "init", "-q")
        await _git(proj, "config", "user.name", "EVA")
        await _git(proj, "config", "user.email", "eva@localhost")
    await _git(proj, "add", "-A")
    code, _ = await _git(proj, "diff", "--cached", "--quiet")
    if code:
        await _git(proj, "commit", "-q", "-m", "État avant l'agent de code")
    code, sha = await _git(proj, "rev-parse", "HEAD")
    if code:                                              # projet vide : premier commit vide
        await _git(proj, "commit", "-q", "--allow-empty", "-m", "Début du projet")
        _, sha = await _git(proj, "rev-parse", "HEAD")
    return sha.strip()


async def modele() -> str:
    from . import router
    try:
        cfg = await router.load_config()
    except Exception:  # noqa: BLE001
        cfg = {}
    return (cfg.get("code") or cfg.get("default") or settings.ollama_model).strip()


async def lancer(workspace: Path, slug: str, consigne: str, fichiers: list[str] | None = None, model: str | None = None) -> dict:
    ws = Path(workspace)
    if not binaire(ws).is_file():
        return {"error": "L'agent de code n'est pas installé : un administrateur l'installe dans Paramètres › Intelligence › Agent de code."}
    slug = (slug or "").strip().strip("/")
    if not _SLUG.match(slug):
        return {"error": "Nom de projet invalide."}
    proj = (ws / "projets" / slug).resolve()
    if not proj.is_dir() or (ws / "projets").resolve() not in proj.parents:
        return {"error": f"Projet introuvable : projets/{slug}. Crée-le d'abord (project_init)."}
    consigne = (consigne or "").strip()
    if len(consigne) < 5:
        return {"error": "Donne une consigne précise à l'agent de code."}
    propres = []
    for f in (fichiers or [])[:20]:
        p = (proj / str(f)).resolve()
        if proj not in p.parents:
            return {"error": f"Fichier hors du projet : {f}"}
        propres.append(p.relative_to(proj).as_posix())
    if _verrou.locked():
        return {"error": "L'agent de code travaille déjà sur une autre demande : réessaie dans quelques minutes."}
    async with _verrou:
        avant = await _preparer_git(proj)
        nom_modele = model or await modele()
        with tempfile.TemporaryDirectory(prefix="eva-aider-") as maison:
            env = {**_git_env(), "HOME": maison, "OLLAMA_API_BASE": settings.ollama_host.rstrip("/"),
                   "AIDER_CHECK_UPDATE": "false", "AIDER_ANALYTICS": "false", "PYTHONUNBUFFERED": "1"}
            cmd = [str(binaire(ws)), "--model", f"ollama_chat/{nom_modele}", "--message", consigne,
                   "--yes-always", "--no-pretty", "--no-stream", "--no-fancy-input", "--no-check-update", "--no-analytics",
                   "--no-show-model-warnings", "--no-show-release-notes", "--no-gitignore", "--no-suggest-shell-commands",
                   "--no-detect-urls", "--no-auto-lint", "--no-auto-test", "--no-browser", "--no-restore-chat-history",
                   "--input-history-file", f"{maison}/in.txt", "--chat-history-file", f"{maison}/chat.md",
                   "--llm-history-file", f"{maison}/llm.txt", "--map-tokens", "1024", "--auto-commits", "--dirty-commits",
                   *propres]
            code, sortie = await _cmd(cmd, cwd=proj, env=env, timeout=DUREE_MAX)
        _, commits = await _git(proj, "log", "--oneline", f"{avant}..HEAD")
        _, stat = await _git(proj, "diff", "--stat", f"{avant}..HEAD")
        _, diff = await _git(proj, "diff", f"{avant}..HEAD")
    sortie = re.sub(r"\x1b\[[0-9;]*m", "", sortie)
    res = {"projet": f"projets/{slug}", "modele": nom_modele, "commits": [c for c in commits.splitlines() if c.strip()],
           "fichiers": stat.strip(), "diff": diff[:MAX_DIFF] + ("\n… (diff tronqué)" if len(diff) > MAX_DIFF else ""),
           "journal": sortie[-1500:], "avant": avant[:12]}
    if code == 124:
        res["error"] = f"L'agent de code a dépassé {DUREE_MAX // 60} minutes : arrêté. Ce qu'il a déjà enregistré reste dans git."
    elif not res["commits"]:
        res["info"] = "L'agent de code n'a modifié aucun fichier (consigne trop vague, ou le modèle n'a pas su faire)."
    else:
        res["annuler"] = f"Pour tout annuler : git reset --hard {avant[:12]} dans projets/{slug}."
    return res
