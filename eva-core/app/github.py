"""Connexion d'EVA à GitHub : jeton personnel, tes dépôts, copies de travail dans le workspace (dossier « depots »).

Le jeton reste sur le NAS (jamais renvoyé à l'interface, jamais écrit dans l'adresse d'un dépôt ni dans un journal) ; il n'est
transmis à git que le temps de la commande, par l'environnement. Pousser (push) ne se fait qu'avec une confirmation explicite."""
import asyncio
import base64
import json
import os
import re
from contextvars import ContextVar
from pathlib import Path

import httpx

from .config import settings
from .db import get_pool

KV = "github"
API = "https://api.github.com"
GITHUB = "https://github.com"                      # remplaçable dans les tests
_NOM = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
GIT_TIMEOUT = 600
MAX_DIFF = 20000


class GitHubError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


projet_var: ContextVar[str] = ContextVar("github_projet", default="")      # projet dans lequel la demande en cours travaille


def _ws(workspace: Path | None = None) -> Path:
    return Path(workspace or settings.workspace_root)


def racine(workspace: Path | None = None) -> Path:
    """Où vivent les copies : dans le dossier du projet quand la demande vise un projet, sinon workspace/depots."""
    slug = projet_var.get()
    if slug and re.match(r"^[a-z0-9._-]{1,48}$", slug) and (_ws(workspace) / "projets" / slug).is_dir():
        return _ws(workspace) / "projets" / slug
    return _ws(workspace) / "depots"


def projet_cite(texte: str, workspace: Path | None = None, courant: str = "") -> str:
    """Le projet visé : « dans le projet X », « dans X » (nom d'un projet existant) ou « dans ce projet » (celui de la conversation)."""
    base = _ws(workspace) / "projets"
    existants = [d.name for d in base.iterdir() if d.is_dir()] if base.is_dir() else []
    t = (texte or "").lower()
    if courant in existants and re.search(r"\b(?:ce|mon|notre)\s+projet\b|\bici\b", t):
        return courant
    for slug in sorted(existants, key=len, reverse=True):
        for m in {slug, slug.replace("-", " "), slug.replace("-", "")}:
            nom = re.escape(m)
            if re.search(rf"\b(?:projet|dossier)\s+(?:(?:nomm[ée]|appel[ée])\s+)?[«\"']?{nom}(?![\w-])"
                         rf"|\bdans\s+(?:le\s+|mon\s+|notre\s+)?(?:projet\s+|dossier\s+)?[«\"']?{nom}(?![\w-])(?!\s+(?:git|github))", t):
                return slug
    return courant if courant in existants and re.search(r"\bprojet\b", t) else ""


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _save(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


async def status() -> dict:
    d = await _load()
    return {"connecte": bool(d.get("token")), "login": d.get("login", "")}


async def _get(path: str, token: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as c:
        return await c.get(f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "EVA"})


async def connect(token: str) -> dict:
    token = (token or "").strip()
    if not re.match(r"^[A-Za-z0-9_\-]{20,255}$", token):
        raise GitHubError("Ce jeton n'a pas la bonne forme (il commence par ghp_ ou github_pat_).")
    try:
        r = await _get("/user", token)
    except httpx.HTTPError as exc:
        raise GitHubError(f"GitHub injoignable : {type(exc).__name__}", 502) from exc
    if r.status_code == 401:
        raise GitHubError("GitHub refuse ce jeton (expiré ou mal copié).")
    if r.status_code != 200:
        raise GitHubError(f"GitHub a répondu {r.status_code}.", 502)
    login = r.json().get("login", "")
    await _save({"token": token, "login": login})
    return {"connecte": True, "login": login}


async def disconnect() -> dict:
    await _save({})
    return {"connecte": False, "login": ""}


async def _token() -> str:
    t = (await _load()).get("token", "")
    if not t:
        raise GitHubError("Pas connecté à GitHub : colle ton jeton d'abord.", 409)
    return t


_cache_repos: dict = {"t": 0.0, "k": "", "v": []}


async def repos() -> list[dict]:
    import time
    tok = await _token()
    if _cache_repos["k"] == tok[-8:] and time.monotonic() - _cache_repos["t"] < 300:
        return _cache_repos["v"]
    v = await _repos(tok)
    _cache_repos.update(t=time.monotonic(), k=tok[-8:], v=v)
    return v


async def _repos(tok: str) -> list[dict]:
    r = await _get("/user/repos", tok, {"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"})
    if r.status_code != 200:
        raise GitHubError(f"GitHub a répondu {r.status_code}.", 502)
    return [{"nom": x["full_name"], "prive": x.get("private", False), "description": (x.get("description") or "")[:140], "pousse": x.get("pushed_at", "")} for x in r.json()]


# ------------------------------------------------------------------ git
async def _git(cwd: Path, *args: str, token: str = "", timeout: int = GIT_TIMEOUT) -> tuple[int, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C.UTF-8", "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}           # dossier créé par un autre utilisateur : pas de blocage
    if token:
        b = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_1="http.https://github.com/.extraheader", GIT_CONFIG_VALUE_1=f"Authorization: basic {b}")
    try:
        p = await asyncio.create_subprocess_exec("git", *args, cwd=str(cwd), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        await p.wait()
        return 1, f"git a mis plus de {timeout} s (timeout)."
    except OSError as exc:
        return 1, f"Impossible de lancer git : {exc}"
    txt = out.decode("utf-8", errors="replace")
    if token:
        txt = txt.replace(token, "***")
    return p.returncode, txt


def explique(out: str) -> str:
    """Les échecs courants de git, dits simplement."""
    o = (out or "").strip()
    low = o.lower()
    if any(k in low for k in ("authentication failed", "invalid username or password", "bad credentials", "401")):
        return "GitHub refuse le jeton (expiré ou révoqué) : recolle-en un dans Paramètres › Services connectés › GitHub."
    if any(k in low for k in ("permission denied", "403", "write access", "not allowed", "insufficient")):
        return "Le jeton n'a pas la permission sur ce dépôt : crée-le avec « Contents : lecture et écriture » et choisis bien ce dépôt."
    if "repository not found" in low or "not found" in low and "repository" in low:
        return "GitHub ne trouve pas ce dépôt avec ce jeton (privé ? jeton limité à d'autres dépôts ?)."
    if "non-fast-forward" in low or "fetch first" in low or "[rejected]" in low:
        return "GitHub a une version plus récente : dis d'abord « mets à jour <dépôt> », puis réessaie."
    if "would be overwritten" in low or "local changes" in low or "not possible to fast-forward" in low or "diverging" in low or "divergent" in low:
        return "Tes copies ont divergé de GitHub (ou des fichiers modifiés gênent) : enregistre d'abord tes changements (« enregistre <dépôt> »), puis « mets à jour <dépôt> »."
    if "could not resolve host" in low or "unable to access" in low or "timeout" in low or "timed out" in low:
        return "GitHub est injoignable depuis le NAS (réseau coupé ou trop lent) : réessaie dans un moment."
    if "no space left" in low:
        return "Plus de place sur le disque du NAS."
    return o[-300:]


def _depot(nom: str, workspace: Path | None = None) -> Path:
    d = racine(workspace) / nom
    if not _NOM.match(nom or "") or not (d / ".git").exists():
        raise GitHubError("Dépôt introuvable.", 404)
    return d


async def cloner(repo: str, workspace: Path | None = None) -> dict:
    if not _REPO.match(repo or ""):
        raise GitHubError("Nom de dépôt invalide (attendu : propriétaire/nom).")
    token = await _token()
    nom = repo.split("/", 1)[1]
    dest = racine(workspace) / nom
    if dest.exists():
        raise GitHubError(f"« {nom} » existe déjà dans le dossier depots : utilise « Récupérer » (pull).", 409)
    racine(workspace).mkdir(parents=True, exist_ok=True)
    code, out = await _git(racine(workspace), "clone", "--", f"{GITHUB}/{repo}.git", nom, token=token)
    if code != 0:
        raise GitHubError(f"Clonage impossible : {explique(out)}")
    return {"nom": nom}


async def depots(workspace: Path | None = None) -> list[dict]:
    root = racine(workspace)
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not (d / ".git").exists():
            continue
        _, br = await _git(d, "rev-parse", "--abbrev-ref", "HEAD", timeout=15)
        _, st = await _git(d, "status", "--porcelain", timeout=15)
        _, last = await _git(d, "log", "-1", "--format=%h %s", timeout=15)
        _, rem = await _git(d, "remote", "get-url", "origin", timeout=15)
        out.append({"nom": d.name, "branche": br.strip(), "modifies": len([l for l in st.splitlines() if l.strip()]),
                    "dernier": last.strip()[:120], "origine": re.sub(r"//[^@/]+@", "//", rem.strip())})
    return out


async def etat(nom: str, workspace: Path | None = None) -> dict:
    code, out = await _git(_depot(nom, workspace), "status", "-sb", timeout=20)
    return {"texte": out.strip()}


async def historique(nom: str, n: int = 15, workspace: Path | None = None) -> list[dict]:
    code, out = await _git(_depot(nom, workspace), "log", f"-{max(1, min(int(n), 50))}", "--format=%h%x09%an%x09%ad%x09%s", "--date=short", timeout=20)
    rows = [l.split("\t", 3) for l in out.splitlines() if l.count("\t") >= 3]
    return [{"id": r[0], "auteur": r[1], "date": r[2], "message": r[3]} for r in rows]


async def differences(nom: str, workspace: Path | None = None) -> dict:
    d = _depot(nom, workspace)
    _, out = await _git(d, "diff", "HEAD", "--stat", "--patch", "--no-color", timeout=30)
    return {"texte": out[:MAX_DIFF], "tronque": len(out) > MAX_DIFF}


_SECRET = re.compile(r"(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,})")
_FICHIER_SECRET = re.compile(r"(^|/)(\.env(\..+)?|id_rsa|id_ed25519|[^/]+\.(pem|key|p12|pfx))$", re.I)


async def _secrets_prevus(d: Path) -> list[str]:
    """Fichiers prêts à être enregistrés qui ressemblent à des secrets (jeton, clé privée, .env)."""
    _, names = await _git(d, "diff", "--cached", "--name-only", timeout=30)
    trouves = [n for n in names.splitlines() if _FICHIER_SECRET.search(n) and not n.endswith((".example", ".sample"))]
    _, patch = await _git(d, "diff", "--cached", "--no-color", "-U0", timeout=60)
    if _SECRET.search(patch):
        trouves.append("contenu qui ressemble à un jeton ou une clé privée")
    return trouves


async def commit(nom: str, message: str, workspace: Path | None = None) -> dict:
    message = (message or "").strip()
    if len(message) < 3:
        raise GitHubError("Écris un message de commit (3 caractères au moins).")
    d = _depot(nom, workspace)
    login = (await _load()).get("login") or "EVA"
    await _git(d, "add", "-A", timeout=60)
    risque = await _secrets_prevus(d)
    if risque:
        await _git(d, "reset", "-q", timeout=30)                  # rien n'est enregistré
        raise GitHubError("Je n'enregistre pas : " + " ; ".join(risque[:4]) + ". Retire-les ou ajoute-les au .gitignore.")
    code, out = await _git(d, "-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com", "commit", "-m", message[:500], timeout=60)
    if code != 0:
        raise GitHubError("Rien à enregistrer." if "nothing to commit" in out else f"Commit impossible : {out.strip()[-300:]}")
    return {"ok": True, "texte": out.strip()[:300]}


async def recuperer(nom: str, workspace: Path | None = None) -> dict:
    d = _depot(nom, workspace)
    code, out = await _git(d, "pull", "--ff-only", token=(await _load()).get("token", ""))
    if code != 0:
        raise GitHubError(f"Récupération impossible : {explique(out)}")
    return {"ok": True, "texte": out.strip()[-400:]}


async def pousser(nom: str, confirme: bool, workspace: Path | None = None) -> dict:
    if not confirme:
        raise GitHubError("Envoyer vers GitHub demande ta confirmation.", 409)
    d = _depot(nom, workspace)
    code, out = await _git(d, "push", "-u", "origin", "HEAD", token=await _token())
    if code != 0:
        raise GitHubError(f"Envoi impossible : {explique(out)}")
    return {"ok": True, "texte": out.strip()[-400:]}


async def supprimer_copie(nom: str, workspace: Path | None = None) -> None:
    import shutil
    d = _depot(nom, workspace)
    await asyncio.to_thread(shutil.rmtree, d)


# ------------------------------------------------------------------ « es-tu connectée à mon git ? » sans modèle
_PARLE_GIT = re.compile(r"\bgit(?:hub)?\b", re.I)
_REGARDE = re.compile(r"\b(connect\w*|clone\w*|lis|lit|lire|extrai\w*|d[ée]charge\w*|r[ée]cup[èe]re\w*|t[ée]l[ée]charge\w*|ouvre|r[ée]sume\w*|v[ée]rifie\w*|regarde\w*|montre\w*|affiche\w*|lister|quels?|combien|vois|acc[èe]s|d[ée]p[ôo]ts?|projets?)\b", re.I)
_ACTION = re.compile(r"\b(ajoute\w*|courses|commit\w*|push\w*|pull|pousse\w*|envoie\w*|supprim\w*|efface\w*|cr[ée]e\w*|modifie\w*|merge\w*|branche\w*|diff\w*|fichier|code|corrige\w*|fix\w*)\b", re.I)


def demande(texte: str) -> bool:
    """« Tu es connecté à mon git ? », « lis mon git », « vérifie tous mes dépôts » : un coup d'œil sur GitHub, pas une action."""
    t = (texte or "").strip()
    return 0 < len(t) <= 140 and bool(_PARLE_GIT.search(t)) and bool(_REGARDE.search(t)) and not _ACTION.search(t)


_VERBE_DEPOT = re.compile(r"\b(clone\w*|extrai\w*|t[ée]l[ée]charge\w*|d[ée]charge\w*|importe\w*|d[ée]pose\w*|rapatrie\w*|install\w*|copie\w*|mets?|mettre)\b", re.I)
_VERBE_LIRE = re.compile(r"\b(lis|lit|lire|ouvre|regarde\w*|r[ée]cup[èe]re\w*)\b", re.I)
_MOT_DEPOT = re.compile(r"\b(d[ée]p[ôo]ts?|repo|repository)\b", re.I)


async def veut(texte: str) -> bool:
    """Comme demande(), et aussi sans le mot « git » quand la phrase cite un de tes dépôts : « clone eva », « extrait eva »."""
    if demande(texte):
        return True
    t = (texte or "").strip()
    if not 0 < len(t) <= 140 or _ACTION.search(t):
        return False
    if not (_VERBE_DEPOT.search(t) or (_VERBE_LIRE.search(t) and _MOT_DEPOT.search(t))):
        return False
    try:
        if not (await status())["connecte"]:
            return False
        return bool(cible(t, [r["nom"] for r in await repos()]))
    except Exception:  # noqa: BLE001
        return False


def cible(texte: str, noms: list[str]) -> str:
    """Le dépôt cité dans la phrase (« lis le git EVA » → Momorie59/EVA), le nom le plus long d'abord."""
    t = (texte or "").lower()
    for n in sorted(noms, key=lambda x: -len(x)):
        court = n.split("/", 1)[-1].lower()
        if len(court) >= 3 and re.search(rf"(?<![\w-]){re.escape(court)}(?![\w-])", t):
            return n
    return ""


async def lire_depot(repo: str, workspace: Path | None = None) -> str:
    """Clone le dépôt s'il n'est pas déjà là (lecture seule, rien n'est envoyé) et en donne un aperçu."""
    nom = repo.split("/", 1)[1]
    neuf = False
    if (racine(workspace) / nom / ".git").exists():
        _, rem = await _git(racine(workspace) / nom, "remote", "get-url", "origin", timeout=15)
        if repo.lower() not in rem.strip().lower():
            raise GitHubError(f"un dossier « {nom} » existe déjà et vient d'ailleurs ({re.sub(r'//[^@/]+@', '//', rem.strip())})")
    else:
        await cloner(repo, workspace)
        neuf = True
    d = _depot(nom, workspace)
    info = next((x for x in await depots(workspace) if x["nom"] == nom), {})
    _, tree = await _git(d, "ls-tree", "--name-only", "HEAD", timeout=20)
    fichiers = [f for f in tree.splitlines() if f][:40]
    log = await historique(nom, 8, workspace)
    lignes = [f"J'ai {'cloné' if neuf else 'ouvert'} **{repo}** (copie dans `{racine(workspace).relative_to(_ws(workspace))}/{nom}`, branche {info.get('branche', '?')}"
              + (f", {info['modifies']} fichier(s) modifié(s)" if info.get("modifies") else "") + ")."]
    if log:
        lignes.append("\nDerniers commits :")
        lignes += [f"- {c['date']} {c['message']}" for c in log]
    if fichiers:
        lignes.append("\nÀ la racine : " + ", ".join(fichiers))
    for r in ("README.md", "readme.md", "README"):
        f = d / r
        if f.is_file():
            lignes.append("\nDébut du README :\n> " + f.read_text(encoding="utf-8", errors="replace")[:500].strip().replace("\n", "\n> "))
            break
    lignes.append("\nDemande-moi ce que tu veux en savoir : je peux lire n'importe quel fichier de ce dépôt.")
    return "\n".join(lignes)


async def resume(texte: str = "", workspace: Path | None = None) -> str:
    st = await status()
    if not st["connecte"]:
        return ("Non, je ne suis pas encore connectée à GitHub. Colle ton jeton dans **Paramètres › Services connectés › GitHub** "
                "(un « fine-grained token » avec « Contents : lecture et écriture »), puis redemande-moi.")
    lignes = [f"Oui, je suis connectée à GitHub en tant que **{st['login']}**."]
    try:
        rs = await repos()
        voulu = cible(texte, [r["nom"] for r in rs])
        if voulu:
            try:
                return await lire_depot(voulu, workspace)
            except GitHubError as exc:
                return f"Je n'ai pas pu ouvrir **{voulu}** : {exc}"
        if rs:
            lignes.append(f"\nTes dépôts ({len(rs)}) :")
            lignes += [f"- {r['nom']}{' 🔒' if r['prive'] else ''}" + (f" — {r['description']}" if r["description"] else "") for r in rs[:30]]
            if len(rs) > 30:
                lignes.append(f"- … et {len(rs) - 30} autres")
        else:
            lignes.append("\nJe ne vois aucun dépôt avec ce jeton : vérifie les dépôts qu'il autorise.")
    except Exception as exc:  # noqa: BLE001
        lignes.append(f"\nJe n'ai pas pu lister tes dépôts : {str(exc)[:150]}")
    copies = await depots(workspace)
    if copies:
        lignes.append("\nCopies de travail dans EVA :")
        lignes += [f"- {c['nom']} ({c['branche']}, " + (f"{c['modifies']} fichier(s) modifié(s)" if c["modifies"] else "à jour") + f") — {c['dernier']}" for c in copies]
    else:
        lignes.append("\nAucun dépôt cloné pour l'instant : Paramètres › Services connectés › GitHub › Cloner, ou dis-moi lequel.")
    return "\n".join(lignes)


# ------------------------------------------------------------------ enregistrer / mettre à jour / envoyer depuis la conversation
_V_PULL = re.compile(r"\b(met\w*\s+[àa]\s+jour|mises?\s+[àa]\s+jour|actualise\w*|synchronise\w*|pull|r[ée]cup[èe]re\w*\s+(?:les\s+)?(?:mises?|changements|modifs?))\b", re.I)
_V_COMMIT = re.compile(r"\b(enregistre\w*|commit\w*|sauvegarde\w*)\b", re.I)
_V_PUSH = re.compile(r"\b(pousse\w*|push\w*|envoie\w*|publie\w*)\b", re.I)
_MSG = re.compile(r"(?:message|avec le message)\s*:?\s*[«\"']?(.{3,200}?)[»\"']?\s*$|:\s*[«\"']?(.{3,200}?)[»\"']?\s*$", re.I)


async def commande(texte: str, workspace: Path | None = None) -> dict | None:
    """« enregistre eva », « mets à jour eva », « envoie eva sur mon git » : actions sur une copie clonée. Il faut un mot git ou le nom d'une copie."""
    t = (texte or "").strip()
    if not 0 < len(t) <= 200:
        return None
    pull, commit, push = bool(_V_PULL.search(t)), bool(_V_COMMIT.search(t)), bool(_V_PUSH.search(t))
    if not (pull or commit or push):
        return None
    try:
        if not (await status())["connecte"]:
            return None
        copies = [c["nom"] for c in await depots(workspace)]
    except Exception:  # noqa: BLE001
        return None
    nom = cible(t, copies)
    if not nom and not _PARLE_GIT.search(t):
        return None                                   # « enregistre ce fichier » : pas une affaire de Git
    m = _MSG.search(t)
    message = next((g.strip() for g in (m.groups() if m else ()) if g), "")
    if not nom:
        if len(copies) == 1:
            nom = copies[0]
        else:
            return {"action": "inconnu", "copies": copies}
    return {"action": "pull" if pull and not (commit or push) else "agir", "nom": nom, "commit": commit, "push": push, "pull": pull, "message": message}


async def executer(cmd: dict, confirmer, workspace: Path | None = None) -> str:
    """confirmer(outil, args) → bool : la demande d'accord d'EVA (cette fois / toujours)."""
    if cmd["action"] == "inconnu":
        copies = cmd["copies"]
        return ("Je n'ai aucune copie de dépôt : dis-moi d'abord « clone eva » (ou le nom du dépôt)." if not copies
                else "De quel dépôt parles-tu ? Mes copies : " + ", ".join(copies) + ". Redis-le avec le nom.")
    nom = cmd["nom"]
    out: list[str] = []
    try:
        if cmd.get("pull"):
            r = await recuperer(nom, workspace)
            out.append(f"Récupéré depuis GitHub pour **{nom}** : {r['texte'].splitlines()[-1] if r['texte'] else 'à jour'}.")
        if cmd.get("commit"):
            msg = cmd.get("message") or "Mise à jour depuis EVA"
            try:
                await commit(nom, msg, workspace)
                out.append(f"Enregistré dans **{nom}** (commit : « {msg} »).")
            except GitHubError as exc:
                if "Rien à enregistrer" not in str(exc):
                    raise
                out.append(f"Rien à enregistrer dans **{nom}** : aucun fichier modifié.")
        if cmd.get("push"):
            if await confirmer("github_push", {"depot": nom, "vers": "GitHub"}):
                await pousser(nom, True, workspace)
                out.append(f"Envoyé vers GitHub : **{nom}** est à jour.")
            else:
                out.append("D'accord, je n'envoie rien.")
    except GitHubError as exc:
        out.append(f"Je n'ai pas pu terminer pour **{nom}** : {exc}")
    return "\n".join(out)
