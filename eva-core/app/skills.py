"""Skills (compétences) : des instructions réutilisables au format SKILL.md.

Un skill est un dossier `<workspace>/skills/<nom>/SKILL.md` : un en-tête
(`name`, `description`) puis des instructions en Markdown. EVA reçoit le
catalogue (nom + description) dans son prompt et charge les instructions
détaillées d'un skill à la demande avec l'outil `skill_read` — ce qui garde le
prompt court tout en lui donnant un savoir-faire étendu.

Les skills influencent durablement le comportement d'EVA : leur création par
EVA (`skill_save`) et l'installation depuis GitHub exigent donc une
confirmation de l'utilisateur.
"""
import json
import os
import re
import shutil
from pathlib import Path

import httpx

from .config import settings

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
MAX_SKILL_BYTES = 100_000
RAW_HOST = "https://raw.githubusercontent.com"
CATALOG_LIMIT = 30


class SkillError(ValueError):
    pass


def skills_root(workspace: Path | None = None) -> Path:
    return (workspace or Path(settings.workspace_root)) / "skills"


ETAT = ".etat.json"


def inactifs(workspace: Path | None = None) -> set[str]:
    """Skills et rôles mis de côté : gardés, mais EVA ne les propose plus."""
    try:
        return set(json.loads((skills_root(workspace) / ETAT).read_text(encoding="utf-8")).get("inactifs", []))
    except (OSError, ValueError):
        return set()


def set_actifs(names: list[str], actif: bool, workspace: Path | None = None) -> int:
    root = skills_root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    cur = inactifs(workspace)
    ok = [n for n in names if NAME_RE.match(n or "") and (root / n / "SKILL.md").is_file()]
    cur = (cur - set(ok)) if actif else (cur | set(ok))
    (root / ETAT).write_text(json.dumps({"inactifs": sorted(cur)}), encoding="utf-8")
    return len(ok)


def builtin_root() -> Path:
    env = os.getenv("EVA_SKILLS_BUILTIN")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "skills"


def slugify(text: str) -> str:
    out = re.sub(r"[^a-z0-9_-]+", "-", text.lower().strip()).strip("-_")
    return out[:60]


def parse_skill(text: str) -> dict:
    """Sépare l'en-tête (clé: valeur) du corps. Lève SkillError si invalide."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise SkillError("Le fichier doit commencer par un en-tête « --- » avec name et description.")
    end = text.find("\n---", 4)
    if end == -1:
        raise SkillError("En-tête non fermé (deuxième « --- » manquant).")
    meta: dict[str, str] = {}
    lines = text[4:end].split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if ":" not in line or line[:1] in " \t-":
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v in ("", ">", "|", ">-", "|-", ">+", "|+") or not v:       # valeur sur plusieurs lignes (YAML)
            cont = []
            while i < len(lines) and (lines[i][:1] in " \t" or not lines[i].strip()):
                cont.append(lines[i].strip())
                i += 1
            v = " ".join(c for c in cont if c) if k.strip().lower() in ("description", "name") else v
        meta[k.strip().lower()] = v.strip("\"'")
    body = text[end + 4:].lstrip("\n")
    name = slugify(meta.get("name", ""))
    if not NAME_RE.match(name):
        raise SkillError("Nom de skill invalide : lettres minuscules, chiffres, tirets (60 max).")
    if not meta.get("description"):
        raise SkillError("La description est obligatoire (elle sert à EVA à choisir le skill).")
    if not body.strip():
        raise SkillError("Le skill n'a aucune instruction.")
    return {"name": name, "description": meta["description"], "body": body, "meta": meta}


def render_skill(name: str, description: str, body: str) -> str:
    return f"---\nname: {name}\ndescription: {description.strip()}\n---\n{body.strip()}\n"


def ensure_builtin(workspace: Path | None = None) -> list[str]:
    """Copie les skills fournis dans le workspace (sans jamais écraser une version modifiée)."""
    root = skills_root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    copied = []
    src = builtin_root()
    if src.is_dir():
        for d in sorted(src.iterdir()):
            if (d / "SKILL.md").is_file() and not (root / d.name).exists():
                shutil.copytree(d, root / d.name)
                copied.append(d.name)
    return copied


def _builtin_names() -> set[str]:
    src = builtin_root()
    return {d.name for d in src.iterdir() if (d / "SKILL.md").is_file()} if src.is_dir() else set()


def list_skills(workspace: Path | None = None) -> list[dict]:
    root = skills_root(workspace)
    out = []
    builtin = _builtin_names()
    off = inactifs(workspace)
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        f = d / "SKILL.md"
        if not f.is_file():
            continue
        try:
            sk = parse_skill(f.read_text(encoding="utf-8", errors="replace"))
        except SkillError as exc:
            out.append({"name": d.name, "description": f"⚠ invalide : {exc}", "source": "invalid", "valid": False})
            continue
        source = sk["meta"].get("source") or ("fourni" if d.name in builtin else "perso")
        out.append({"name": d.name, "description": sk["description"], "source": source, "valid": True,
                    "kind": "agent" if sk["meta"].get("kind") == "agent" else "skill", "actif": d.name not in off})
    return out


def _skill_dir(name: str, workspace: Path | None = None) -> Path:
    if not NAME_RE.match(name or ""):
        raise SkillError("Nom de skill invalide.")
    return skills_root(workspace) / name


def get_skill(name: str, workspace: Path | None = None) -> dict | None:
    f = _skill_dir(name, workspace) / "SKILL.md"
    if not f.is_file():
        return None
    raw = f.read_text(encoding="utf-8", errors="replace")
    try:
        sk = parse_skill(raw)
    except SkillError as exc:
        return {"name": name, "description": "", "body": "", "raw": raw, "valid": False, "error": str(exc)}
    return {"name": name, "description": sk["description"], "body": sk["body"], "raw": raw, "valid": True}


def save_skill_raw(name: str, raw: str, workspace: Path | None = None) -> dict:
    """Enregistre un SKILL.md complet. Le nom de l'en-tête doit correspondre au dossier."""
    if len(raw.encode("utf-8")) > MAX_SKILL_BYTES:
        raise SkillError("Skill trop volumineux (100 Ko maximum).")
    sk = parse_skill(raw)
    if sk["name"] != name:
        raise SkillError(f"Le nom dans l'en-tête (« {sk['name']} ») doit être « {name} ».")
    d = _skill_dir(name, workspace)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(raw.replace("\r\n", "\n"), encoding="utf-8")
    return {"name": name, "description": sk["description"]}


def delete_skill(name: str, workspace: Path | None = None) -> bool:
    d = _skill_dir(name, workspace)
    if not d.is_dir():
        return False
    shutil.rmtree(d)
    return True


def delete_many(names: list[str], workspace: Path | None = None) -> int:
    return sum(1 for n in names if NAME_RE.match(n or "") and delete_skill(n, workspace))


# ---------- Installation depuis GitHub ----------

_GH_SPEC = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]+)?$")


def parse_github_source(source: str) -> tuple[str, str, str, str]:
    """Accepte `owner/repo`, `owner/repo/chemin/du/skill` ou une URL github.com
    (tree/blob). Retourne (owner, repo, ref, chemin_du_SKILL.md)."""
    s = source.strip()
    ref = "HEAD"
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/(?:tree|blob)/([^/]+)/(.+)$", s)
    if m:
        owner, repo, ref, path = m.groups()
    else:
        m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", s)
        if m:
            owner, repo = m.groups()
            path = ""
        else:
            if not _GH_SPEC.match(s) or ".." in s:
                raise SkillError("Source invalide. Exemples : owner/repo, owner/repo/dossier/skill, ou une URL github.com.")
            parts = s.split("/", 2)
            owner, repo = parts[0], parts[1]
            path = parts[2] if len(parts) > 2 else ""
    path = path.strip("/")
    if ".." in path or not re.match(r"^[A-Za-z0-9_./-]*$", path) or not re.match(r"^[A-Za-z0-9_.-]+$", ref):
        raise SkillError("Chemin invalide.")
    if not path.endswith("SKILL.md"):
        path = f"{path}/SKILL.md" if path else "SKILL.md"
    return owner, repo, ref, path


async def _fetch_text(url: str) -> str | None:
    """Télécharge un texte depuis raw.githubusercontent.com uniquement (hôte fixe)."""
    if not url.startswith(RAW_HOST + "/"):
        raise SkillError("Hôte non autorisé.")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise SkillError(f"GitHub a répondu {resp.status_code}.")
    if len(resp.content) > MAX_SKILL_BYTES:
        raise SkillError("Skill trop volumineux (100 Ko maximum).")
    return resp.text


async def install_from_github(source: str, workspace: Path | None = None) -> dict:
    owner, repo, ref, path = parse_github_source(source)
    raw = await _fetch_text(f"{RAW_HOST}/{owner}/{repo}/{ref}/{path}")
    if raw is None and ref == "HEAD":
        raw = await _fetch_text(f"{RAW_HOST}/{owner}/{repo}/main/{path}")
    if raw is None:
        raise SkillError(f"Aucun {path} trouvé dans {owner}/{repo}.")
    sk = parse_skill(raw)  # valide l'en-tête avant d'écrire quoi que ce soit
    if (_skill_dir(sk["name"], workspace) / "SKILL.md").exists():
        raise SkillError(f"Un skill « {sk['name']} » existe déjà : supprime-le d'abord pour le remplacer.")
    stamped = raw if "\nsource:" in raw.split("\n---", 1)[0] else raw.replace(
        "\n---", f"\nsource: github:{owner}/{repo}\n---", 1
    )
    save_skill_raw(sk["name"], stamped, workspace)
    return {"name": sk["name"], "description": sk["description"], "source": f"github:{owner}/{repo}"}


# ---------- Parcourir un dépôt entier : liste exhaustive + installation de la sélection ----------

API_HOST = "https://api.github.com"
MAX_CATALOG = 400
# Les dépôts d'agents (ex. ECC) rangent un rôle par fichier « agents/nom.md » avec le même en-tête (name, description) :
# ils sont proposés comme des skills (consigne chargée à la demande).
AGENT_RE = re.compile(r"(?:^|/)agents/(?!README)[^/]+\.md$", re.I)


def est_skill_path(p: str) -> bool:
    return p == "SKILL.md" or p.endswith("/SKILL.md") or bool(AGENT_RE.search(p))
_cat_cache: dict[str, tuple[float, dict]] = {}


def parse_repo(source: str) -> tuple[str, str, str, str]:
    """`owner/repo`, `owner/repo/sous/dossier` ou URL github.com → (owner, repo, ref, préfixe de dossier)."""
    s = source.strip()
    m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/(?:tree|blob)/([^/]+)(?:/(.*))?)?/?$", s)
    if m:
        owner, repo, ref, sub = m.group(1), m.group(2), m.group(3) or "HEAD", (m.group(4) or "")
    else:
        if not _GH_SPEC.match(s) or ".." in s:
            raise SkillError("Source invalide. Exemples : owner/repo ou https://github.com/owner/repo")
        parts = s.split("/", 2)
        owner, repo, ref, sub = parts[0], parts[1], "HEAD", (parts[2] if len(parts) > 2 else "")
    sub = sub.strip("/")
    if sub.endswith("SKILL.md"):
        sub = sub[: -len("SKILL.md")].strip("/")
    if ".." in sub or not re.match(r"^[A-Za-z0-9_./-]*$", sub) or not re.match(r"^[A-Za-z0-9_.-]+$", ref) or not re.match(r"^[A-Za-z0-9_.-]+$", owner + repo):
        raise SkillError("Source invalide.")
    return owner, repo, ref, sub


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    if not url.startswith((API_HOST + "/", RAW_HOST + "/")):
        raise SkillError("Hôte non autorisé.")
    return await client.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "EVA"})


async def _list_paths(client: httpx.AsyncClient, owner: str, repo: str, ref: str, sub: str) -> tuple[list[str], str, bool]:
    r = await _get(client, f"{API_HOST}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1")
    if r.status_code == 404:
        raise SkillError(f"Dépôt ou branche introuvable : {owner}/{repo} ({ref}).")
    if r.status_code == 403:
        raise SkillError("GitHub limite les requêtes anonymes (60 par heure). Réessaie plus tard.")
    if r.status_code != 200:
        raise SkillError(f"GitHub a répondu {r.status_code}.")
    data = r.json()
    prefix = sub + "/" if sub else ""
    paths = sorted(t["path"] for t in data.get("tree", []) if t.get("type") == "blob" and est_skill_path(t["path"]) and t["path"].startswith(prefix))
    return paths, data.get("sha", ref), bool(data.get("truncated"))


async def _read_meta(client: httpx.AsyncClient, owner: str, repo: str, ref: str, path: str, sem) -> dict:
    async with sem:
        try:
            r = await _get(client, f"{RAW_HOST}/{owner}/{repo}/{ref}/{path}")
            if r.status_code != 200:
                return {"path": path, "error": f"HTTP {r.status_code}"}
            if len(r.content) > MAX_SKILL_BYTES:
                return {"path": path, "error": "trop volumineux (> 100 Ko)"}
            sk = parse_skill(r.text)
            return {"path": path, "name": sk["name"], "description": sk["description"][:300], "size": len(r.content)}
        except SkillError as exc:
            return {"path": path, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"path": path, "error": f"lecture impossible ({type(exc).__name__})"}


async def catalog(source: str, workspace: Path | None = None) -> dict:
    """Liste TOUS les SKILL.md d'un dépôt (ou d'un sous-dossier), avec nom, description, catégorie et état « déjà installé »."""
    import asyncio
    import time as _t
    owner, repo, ref, sub = parse_repo(source)
    key = f"{owner}/{repo}@{ref}/{sub}"
    hit = _cat_cache.get(key)
    if hit and _t.time() - hit[0] < 600:
        base = hit[1]
    else:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
            paths, sha, truncated = await _list_paths(client, owner, repo, ref, sub)
            if not paths:
                raise SkillError(f"Aucun SKILL.md trouvé dans {owner}/{repo}" + (f"/{sub}" if sub else "") + ".")
            sem = asyncio.Semaphore(8)
            metas = await asyncio.gather(*[_read_meta(client, owner, repo, ref, p, sem) for p in paths[:MAX_CATALOG]])
        base = {"owner": owner, "repo": repo, "ref": ref, "sub": sub, "total": len(paths), "limited": len(paths) > MAX_CATALOG, "truncated": truncated, "items": metas}
        _cat_cache[key] = (_t.time(), base)
    have = {s["name"] for s in list_skills(workspace)}
    items = []
    for m in base["items"]:
        parts = m["path"].split("/")
        agent = bool(AGENT_RE.search(m["path"]))
        items.append({**m, "agent": agent, "category": "agents" if agent else ("/".join(parts[:-2]) if len(parts) > 2 else ""),
                      "folder": parts[-1][:-3] if agent else (parts[-2] if len(parts) > 1 else repo),
                      "installed": m.get("name") in have, "ok": "error" not in m})
    return {**base, "items": items, "source": f"{owner}/{repo}" + (f"/{sub}" if sub else "")}


async def install_many(source: str, paths: list[str], workspace: Path | None = None) -> dict:
    owner, repo, ref, sub = parse_repo(source)
    done, skipped, failed = [], [], []
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
        for path in paths[:MAX_CATALOG]:
            if ".." in path or not est_skill_path(path) or not re.match(r"^[A-Za-z0-9_./-]+$", path) or (sub and not path.startswith(sub + "/")):
                failed.append({"path": path, "error": "chemin refusé"})
                continue
            try:
                r = await _get(client, f"{RAW_HOST}/{owner}/{repo}/{ref}/{path}")
                if r.status_code != 200:
                    raise SkillError(f"HTTP {r.status_code}")
                if len(r.content) > MAX_SKILL_BYTES:
                    raise SkillError("trop volumineux (> 100 Ko)")
                sk = parse_skill(r.text)
                if (_skill_dir(sk["name"], workspace) / "SKILL.md").exists():
                    skipped.append({"path": path, "name": sk["name"], "reason": "déjà installé"})
                    continue
                raw = r.text.replace("\r\n", "\n")
                head = raw.split("\n---", 1)[0]
                if "\nsource:" not in head:
                    raw = raw.replace("\n---", f"\nsource: github:{owner}/{repo}\n---", 1)
                if AGENT_RE.search(path) and "\nkind:" not in head:
                    raw = raw.replace("\n---", "\nkind: agent\n---", 1)       # un rôle d'agent : EVA pourra le faire travailler seul (role_run)
                save_skill_raw(sk["name"], raw, workspace)
                done.append({"path": path, "name": sk["name"]})
            except SkillError as exc:
                failed.append({"path": path, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                failed.append({"path": path, "error": f"GitHub injoignable ({type(exc).__name__})"})
    return {"installed": done, "skipped": skipped, "failed": failed}


# ---------- Prompt ----------

def system_prompt_with_skills(base: str, workspace: Path | None = None) -> str:
    skills = [s for s in list_skills(workspace) if s.get("valid") and s["actif"] and s["kind"] == "skill"][:CATALOG_LIMIT]
    if not skills:
        return base
    lines = "\n".join(f"- {s['name']} : {s['description'][:140]}" for s in skills)
    return (
        f"{base}\n\nCompétences disponibles (skills) :\n{lines}\n"
        "Quand la demande de l'utilisateur correspond à l'une d'elles, appelle d'abord "
        "skill_read avec son nom pour charger les instructions détaillées, puis suis-les."
    )


# ---------- Rôles d'agents (fichiers agents/nom.md installés avec « kind: agent ») ----------
OUTILS_ROLE = {"read": {"fs_read"}, "grep": {"fs_read", "docs_search"}, "glob": {"fs_list"}, "webfetch": {"web_fetch"}, "websearch": {"web_search"}}
OUTILS_ROLE_BASE = {"fs_list", "fs_read", "docs_search"}       # lecture seule : jamais d'écriture ni de commande, quoi que demande le rôle


def role_tools(declared: str) -> set[str]:
    """Outils d'un rôle ECC (« Read, Grep, Glob, Write… ») traduits en outils EVA de LECTURE. Write, Edit et Bash sont ignorés."""
    out = set(OUTILS_ROLE_BASE)
    for t in re.split(r"[,\s]+", declared or ""):
        out |= OUTILS_ROLE.get(t.strip().lower(), set())
    return out


def list_roles(workspace: Path | None = None) -> list[dict]:
    out = []
    root = skills_root(workspace)
    if not root.is_dir():
        return out
    off = inactifs(workspace)
    for d in sorted(root.iterdir()):
        f = d / "SKILL.md"
        if not f.is_file() or d.name in off:
            continue
        try:
            sk = parse_skill(f.read_text(encoding="utf-8", errors="replace"))
        except SkillError:
            continue
        if sk["meta"].get("kind") == "agent":
            out.append({"name": d.name, "description": sk["description"], "body": sk["body"], "tools": sorted(role_tools(sk["meta"].get("tools", "")))})
    return out
