"""Génération d'images : EVA transmet la demande à un serveur d'images local (Stable Diffusion via l'API d'AUTOMATIC1111 / Forge,
ou toute API compatible OpenAI « /v1/images/generations »). Un modèle « vision » COMPREND des images, il n'en crée pas."""
import base64
import contextvars
import json
import re
import time
from pathlib import Path

import httpx

from .config import settings
from .db import get_pool
from .scenes import fold

_VERB = (r"(?:genere|generer|cree|creer|dessine|dessiner|fais|faire|fabrique|produis|produire|peins|peindre|imagine|imaginer|realise|realiser|"
         r"donne|montre|sors|propose|invente|inventer|concois|concevoir|designe|illustre|illustrer|visualise|elabore|esquisse|croque|"
         r"veux|voudrais|aimerais|souhaite|desire|besoin)")
_THING = (r"(?:coloriage|coloriages|page a colorier|pages a colorier|dessin a colorier|dessins a colorier|mandala|mandalas|bande dessinee|bd|"
          r"carte d anniversaire|carte de voeux|invitation|etiquette|etiquettes|"
          r"image|images|illustration|illustrations|dessin|dessins|photo|photos|portrait|portraits|affiche|logo|logos|wallpaper|fond d ecran|peinture|visuel|"
          r"icone|avatar|caricature|banniere|miniature|sticker|autocollant|pochette|fresque|croquis|esquisse|poster|carte postale|oeuvre|rendu 3d|render|meme)")
_ASK = re.compile(r"\b" + _VERB + r"\b[^.:!?\n]{0,30}?\b(?:un|une|des|l|le|la)?\s*(?P<noun>" + _THING + r")\b")
# « un dessin d'un dragon », « photo réaliste de … » : la phrase commence directement par le type d'image
_NOUN_LEAD = re.compile(r"^\s*(?:(?:s il te plait|svp|stp)\s+)?(?:(?:un|une|des|l|le|la)\s+)?(?P<noun>" + _THING + r")\s+(?:(?:realiste|photorealiste|hd|4k|numerique|artistique)\s+)?(?=(?:de|d|du|des|representant|avec|montrant|ou|qui)\b)")
_LEAD = re.compile(r"^[\s,:;.\-–]*(?:(?:de |d |du |des |d un |d une |representant |avec |montrant |ou |qui represente |sur )\s*)*", re.I)

# « dessine un chat », « dessine-moi un mouton », « peins un coucher de soleil » : le verbe suffit
_DRAW = re.compile(r"^\s*(?:(?:s il te plait|svp|stp|peux tu|pourrais tu|tu peux|veux tu)\s+)*(?:me\s+)?(?:dessine|dessiner|peins|peindre|croque|croquer)(?:\s+moi)?\s+(?P<s>.+)$")

# Coloriage : dessin au trait noir sur fond blanc, sans couleur ni ombre (les modèles d'images comprennent l'anglais)
_COLORIAGE = re.compile(r"colori|coloring|colouring|mandala|line ?art|a colorier|à colorier", re.I)
STYLE_COLORIAGE = ("coloring page for kids, black and white line art, thick clean black outlines, simple shapes, "
                   "no color, no shading, no gray, pure white background")
NEGATIF_COLORIAGE = "color, colored, colorful, shading, shadows, gray, gradient, photo, realistic, texture, background scenery"


def est_coloriage(texte: str) -> bool:
    return bool(_COLORIAGE.search(texte or ""))
_GENERIC = {"image", "images", "illustration", "illustrations", "visuel"}
_NOT = re.compile(r"\b(?:que je t ai|sur l image|sur la photo|dans l image|dans la photo|cette image|cette photo|ci jointe|envoye|de profil|sur le site|dans le dossier|le dossier|les dossiers|le fichier|la galerie|mes images|mes photos|mon dossier)\b")

KINDS = ("a1111", "openai")
DEFAULT_NEGATIVE = "blurry, low quality, deformed, bad anatomy, extra fingers, text, watermark, logo"
MASK = "••••"


def wants_image(text: str) -> str | None:
    """Retourne le sujet de l'image demandée (texte d'origine), ou None si ce n'est pas une demande de création d'image."""
    folded = fold(text)
    if len(folded) != len(text):
        return None
    d = _DRAW.match(folded)
    if d and not _NOT.search(folded) and not _ASK.search(folded):
        return text[d.start("s"):].strip(" \t\n\"'«»,;.!?") or None
    m = _ASK.search(folded) or _NOUN_LEAD.match(folded)
    if not m or _NOT.search(folded):
        return None
    if m.group("noun") not in _GENERIC:                        # « photo », « logo », « affiche »… : le type d'image fait partie de la demande, on le garde
        return text[m.start("noun"):].strip(" \t\n\"'«»,;.!?") or text.strip()
    rest = text[m.end():]
    lead = _LEAD.match(fold(rest))
    subject = rest[lead.end():].strip(" \t\n\"'«»,;.!?")
    return subject or text.strip()


async def get_config() -> dict:
    cfg = {"url": settings.imagegen_url, "kind": "a1111", "model": "", "steps": 0, "size": 0, "negative": DEFAULT_NEGATIVE, "enhance": True, "token": ""}
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='image_gen'")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        cfg.update({k: v for k, v in data.items() if k in cfg})
    return cfg


async def set_config(url: str, kind: str, model: str = "", steps: int = 0, size: int = 0, negative: str | None = None, enhance: bool = True, token: str | None = None) -> dict:
    url = (url or "").strip().rstrip("/")
    if url and not re.match(r"^https?://", url):
        raise ValueError("Adresse invalide : attendu http://… ou https://…")
    if kind not in KINDS:
        raise ValueError("Type inconnu.")
    old = await get_config()
    size = int(size or 0)
    cfg = {"url": url, "kind": kind, "model": (model or "").strip()[:100], "steps": max(0, min(int(steps or 0), 80)),   # 0 = réglage automatique du serveur
           "size": 0 if not size else max(256, min(size, 1024)),
           "negative": (old["negative"] if negative is None else negative.strip()[:300]), "enhance": bool(enhance),
           "token": old["token"] if token in (None, MASK) else token.strip()[:200]}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('image_gen', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(cfg))
    return public(cfg)


def public(cfg: dict) -> dict:
    return {**cfg, "token": MASK if cfg.get("token") else ""}


class ImageError(Exception):
    pass


def _headers(cfg: dict) -> dict:
    return {"Authorization": f"Bearer {cfg['token']}"} if cfg.get("token") else {}


async def generate(prompt: str, cfg: dict | None = None, negative: str | None = None) -> bytes:
    cfg = cfg or await get_config()
    if not cfg["url"]:
        raise ImageError("not_configured")
    size = int(cfg.get("size") or 0)
    neg = ((cfg.get("negative", "") if negative is None else negative) + ", " + neg_extra_var.get()).strip(", ")
    if est_coloriage(prompt):                                  # page à colorier : trait noir, rien à peindre d'avance
        if "line art" not in prompt.lower():
            prompt = f"{prompt}, {STYLE_COLORIAGE}"
        neg = f"{neg}, {NEGATIF_COLORIAGE}".strip(", ")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0), headers=_headers(cfg)) as c:
            if cfg["kind"] == "openai":
                body = {"prompt": prompt, "n": 1, "response_format": "b64_json"}
                if size:
                    body["size"] = f"{size}x{size}"
                if cfg["model"]:
                    body["model"] = cfg["model"]
                r = await c.post(f"{cfg['url']}/v1/images/generations", json=body)
                if r.status_code != 200:
                    raise ImageError(_http_error(r))
                b64 = r.json()["data"][0]["b64_json"]
            else:
                body = {"prompt": prompt, "batch_size": 1}
                if neg:
                    body["negative_prompt"] = neg
                if cfg.get("steps"):
                    body["steps"] = int(cfg["steps"])
                if size:
                    body["width"] = body["height"] = size
                if cfg["model"]:
                    body["override_settings"] = {"sd_model_checkpoint": cfg["model"]}
                r = await c.post(f"{cfg['url']}/sdapi/v1/txt2img", json=body)
                if r.status_code != 200:
                    raise ImageError(_http_error(r))
                b64 = r.json()["images"][0]
    except httpx.HTTPError as exc:
        raise ImageError(f"Serveur d'images injoignable ({type(exc).__name__}). Vérifie que le conteneur eva-imagegen tourne et que l'adresse est la bonne.") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise ImageError("Réponse inattendue du serveur d'images.") from exc
    try:
        return base64.b64decode(b64.split(",", 1)[-1])
    except ValueError as exc:
        raise ImageError("Image illisible.") from exc


NEEDS_UPDATE = ("Ton serveur d'images ne sait pas encore modifier des images : il faut mettre à jour le dossier eva-imagegen sur le serveur IA "
                "(procédure dans IMAGES.md, « Mettre à jour le serveur d'images »).")
NO_EDIT = "Modifier une image demande le serveur eva-imagegen (ou Stable Diffusion WebUI / Forge) : choisis ce type d'API dans Paramètres › Génération d'images."


async def edit_remote(png: bytes, prompt: str, cfg: dict | None = None, target: str = "", strength: float | None = None) -> bytes:
    """Modification par l'IA : toute l'image (img2img) ou seulement la zone désignée par un mot (`target`)."""
    cfg = cfg or await get_config()
    if not cfg["url"]:
        raise ImageError("not_configured")
    if cfg["kind"] != "a1111":
        raise ImageError(NO_EDIT)
    b64 = base64.b64encode(png).decode()
    neg = (cfg.get("negative", "") + ", " + neg_extra_var.get()).strip(", ")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(400.0, connect=10.0), headers=_headers(cfg)) as c:
            if target:
                body = {"image": b64, "prompt": prompt, "target": target, "negative_prompt": neg}
                if strength is not None:
                    body["strength"] = strength
                if cfg["model"]:
                    body["model"] = cfg["model"]
                r = await c.post(f"{cfg['url']}/eva/edit", json=body)
            else:
                body = {"init_images": [b64], "prompt": prompt, "negative_prompt": neg, "denoising_strength": strength if strength is not None else 0.6}
                if cfg.get("steps"):
                    body["steps"] = int(cfg["steps"])
                if cfg["model"]:
                    body["override_settings"] = {"sd_model_checkpoint": cfg["model"]}
                r = await c.post(f"{cfg['url']}/sdapi/v1/img2img", json=body)
            if r.status_code in (404, 405):
                raise ImageError(NEEDS_UPDATE)
            if r.status_code != 200:
                raise ImageError(_http_error(r))
            out = r.json()["images"][0]
    except httpx.HTTPError as exc:
        raise ImageError(f"Serveur d'images injoignable ({type(exc).__name__}). Vérifie que le conteneur eva-imagegen tourne.") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise ImageError("Réponse inattendue du serveur d'images.") from exc
    try:
        return base64.b64decode(out.split(",", 1)[-1])
    except ValueError as exc:
        raise ImageError("Image illisible.") from exc


def _http_error(r) -> str:
    try:
        d = r.json().get("detail")
    except ValueError:
        d = ""
    return f"Le serveur d'images a répondu {r.status_code}" + (f" : {d}" if isinstance(d, str) and d else ".")


_ENH_SYS = ("You write prompts for the Stable Diffusion image model. Rewrite the user's request (any language) as ONE English prompt, 25 to 50 words: "
            "subject, setting, style, lighting, camera or medium, quality keywords. Keep every detail the user gave. Answer with the prompt only, no quotes, no explanation.")


_REFUSAL = re.compile(r"\b(?:i can'?t|i cannot|i can not|i'?m sorry|i am sorry|i'?m unable|i am unable|i won'?t|i will not|as an ai|as a language model|cannot (?:assist|help|comply|fulfill)|"
                      r"d[ée]sol[ée]|je ne peux pas|je ne suis pas en mesure|je refuse|en tant qu'?(?:ia|assistant))\b", re.I)


async def ask_small(system: str, user: str, timeout: float = 40) -> str:
    """Une question courte au petit modèle local (rapide) ; chaîne vide s'il n'est pas disponible, s'il refuse ou s'il bavarde."""
    try:
        import asyncio
        from . import ollama_client, router
        sel = await router.select(user, prefer_fast=True)
        if sel["model"] == "airllm":
            return ""
        msg = await asyncio.wait_for(ollama_client.chat_once([{"role": "system", "content": system}, {"role": "user", "content": user}], model=sel["model"]), timeout)
        text = re.sub(r"<think>.*?</think>", "", (msg.get("content") or ""), flags=re.S).strip().strip("\"'«» ")
        text = text.splitlines()[0].strip() if text else ""
        return "" if (len(text) < 2 or _REFUSAL.search(text)) else text[:500]
    except Exception:  # noqa: BLE001
        return ""


async def enhance(subject: str) -> str:
    """Traduit et enrichit la demande (les modèles d'images comprennent surtout l'anglais). Sans modèle de langage disponible : demande telle quelle."""
    try:
        import asyncio
        from . import ollama_client, router
        sel = await router.select(subject, prefer_fast=True)
        model = sel["model"]
        if model == "airllm":                                  # trop lent pour une étape intermédiaire
            return subject
        msg = await asyncio.wait_for(ollama_client.chat_once([{"role": "system", "content": _ENH_SYS}, {"role": "user", "content": subject}], model=model), 40)
        text = (msg.get("content") or "").strip().strip("\"'«» ")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        text = text.splitlines()[0].strip() if text else ""
        if len(text) < 8 or _REFUSAL.search(text):             # le petit modèle refuse ou bavarde : on garde la demande telle que tu l'as écrite
            return subject
        if est_coloriage(subject) and not est_coloriage(text):   # la traduction a perdu « coloriage » : on le remet
            text = f"{text}, {STYLE_COLORIAGE}"
        return text[:500]
    except Exception:  # noqa: BLE001 — l'amélioration est un confort, jamais un obstacle
        return subject


async def status(cfg: dict | None = None) -> dict:
    """État du serveur d'images : joignable ? modèle, carte graphique, modèles disponibles."""
    cfg = cfg or await get_config()
    if not cfg["url"]:
        return {"up": False, "configured": False}
    try:
        async with httpx.AsyncClient(timeout=6, headers=_headers(cfg)) as c:
            r = await c.get(f"{cfg['url']}/health")
            if r.status_code == 200 and isinstance(r.json(), dict) and r.json().get("ok"):
                return {"up": True, "configured": True, "own": True, **{k: v for k, v in r.json().items() if k != "ok"}}
            r = await c.get(f"{cfg['url']}/sdapi/v1/sd-models")                          # Stable Diffusion WebUI / Forge
            if r.status_code == 200:
                return {"up": True, "configured": True, "own": False, "models": [m.get("title") for m in r.json() if isinstance(m, dict)]}
            return {"up": False, "configured": True, "error": f"Le serveur a répondu {r.status_code}."}
    except httpx.HTTPError as exc:
        return {"up": False, "configured": True, "error": f"Injoignable ({type(exc).__name__})."}
    except ValueError:
        return {"up": False, "configured": True, "error": "Réponse inattendue."}


async def detect() -> dict | None:
    """Cherche un serveur eva-imagegen : serveur IA (même machine qu'Ollama), conteneur voisin, hôte Docker."""
    from urllib.parse import urlparse
    hosts = []
    h = urlparse(settings.ollama_host).hostname
    if h:
        hosts.append(h)
    hosts += ["eva-imagegen", "host.docker.internal"]
    for host in dict.fromkeys(hosts):
        url = f"http://{host}:7860"
        st = await status({"url": url, "token": ""})
        if st.get("up") and st.get("own"):
            return {"url": url, **st}
    return None


# Propriétaire des images : None = administrateur (voit tout) ; sinon le nom de l'utilisateur connecté (réglé par la requête ou la conversation en cours).
neg_extra_var: contextvars.ContextVar[str] = contextvars.ContextVar("image_neg_extra", default="")   # filtre du profil (enfant, ado…)
owner_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("image_owner", default=None)


def can_see(meta_owner: str, owner: str | None) -> bool:
    return owner is None or meta_owner == owner


def save(png: bytes, workspace: Path, prompt: str = "", final: str = "", kind: str = "create") -> Path:
    d = workspace / "generated"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"img-{int(time.time() * 1000)}"
    p = d / f"{stem}.png"
    p.write_bytes(png)
    try:
        (d / f"{stem}.json").write_text(json.dumps({"prompt": prompt, "final": final, "kind": kind, "owner": owner_var.get() or ""}, ensure_ascii=False))
    except OSError:
        pass
    return p


_NAME = re.compile(r"^img-\d+\.png$")


def gallery(workspace: Path, limit: int = 24, owner: str | None = None) -> list[dict]:
    d = workspace / "generated"
    if not d.is_dir():
        return []
    out = []
    for p in sorted((x for x in d.glob("img-*.png") if _NAME.match(x.name)), key=lambda x: x.name, reverse=True):
        meta = {}
        try:
            meta = json.loads(p.with_suffix(".json").read_text())
        except (OSError, ValueError):
            pass
        if not can_see(meta.get("owner", ""), owner):
            continue
        if len(out) >= limit:
            break
        out.append({"name": p.name, "at": p.stat().st_mtime, "size": p.stat().st_size, "prompt": meta.get("prompt", ""), "final": meta.get("final", ""),
                    "kind": meta.get("kind", "create"), "pinned": bool(meta.get("pinned")), "owner": meta.get("owner", "")})
    return out


def _meta_path(workspace: Path, name: str) -> Path:
    return workspace / "generated" / (name[:-4] + ".json")


def check_access(workspace: Path, name: str, owner: str | None) -> None:
    """Un utilisateur standard n'accède qu'à ses propres images."""
    if owner is None:
        return
    try:
        meta = json.loads(_meta_path(workspace, name).read_text())
    except (OSError, ValueError):
        meta = {}
    if not can_see(meta.get("owner", ""), owner):
        raise ImageError("Image introuvable.")


def set_pinned(workspace: Path, name: str, pinned: bool) -> None:
    """Une image « gardée » échappe à la purge automatique."""
    if not _NAME.match(name):
        raise ImageError("Nom d'image invalide.")
    if not (workspace / "generated" / name).is_file():
        raise ImageError("Image introuvable.")
    mp = _meta_path(workspace, name)
    try:
        meta = json.loads(mp.read_text()) if mp.is_file() else {}
    except (OSError, ValueError):
        meta = {}
    meta["pinned"] = bool(pinned)
    mp.write_text(json.dumps(meta, ensure_ascii=False))


def latest(workspace: Path, max_age: float = 1800.0) -> tuple[str, bytes] | None:
    """Dernière image de la galerie (si assez récente) : sert de « cette image » quand on demande de la modifier sans en joindre une."""
    items = gallery(workspace, 1, owner_var.get())
    if not items or time.time() - items[0]["at"] > max_age:
        return None
    return items[0]["name"], (workspace / "generated" / items[0]["name"]).read_bytes()


def purge(workspace: Path, keep_days: int = 30, max_items: int = 200, now: float | None = None) -> dict:
    """Purge automatique : supprime les images (non gardées) plus vieilles que `keep_days` jours, puis les plus anciennes au-delà de `max_items`.
    0 = pas de limite. Retire aussi les fiches orphelines."""
    now = now or time.time()
    d = workspace / "generated"
    removed = 0
    if not d.is_dir():
        return {"removed": 0, "kept": 0}
    items = gallery(workspace, limit=100000)                      # du plus récent au plus ancien
    candidates = [it for it in items if not it["pinned"]]
    doomed: set[str] = set()
    if keep_days and keep_days > 0:
        doomed |= {it["name"] for it in candidates if now - it["at"] > keep_days * 86400}
    if max_items and max_items > 0:
        survivors = [it for it in candidates if it["name"] not in doomed]
        doomed |= {it["name"] for it in survivors[max_items:]}
    for name in doomed:
        try:
            remove(workspace, name)
            removed += 1
        except OSError:
            pass
    for j in d.glob("img-*.json"):                                # fiche sans image
        if not (d / (j.stem + ".png")).exists():
            j.unlink(missing_ok=True)
    return {"removed": removed, "kept": len(items) - removed}


GALLERY_DEFAULT = {"keep_days": 30, "max_items": 200}


async def get_gallery_cfg() -> dict:
    cfg = dict(GALLERY_DEFAULT)
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='image_gallery'")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        cfg.update({k: int(v) for k, v in data.items() if k in cfg and isinstance(v, (int, float))})
    return cfg


async def set_gallery_cfg(keep_days: int, max_items: int) -> dict:
    cfg = {"keep_days": max(0, min(int(keep_days), 3650)), "max_items": max(0, min(int(max_items), 5000))}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('image_gallery', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(cfg))
    return cfg


def thumb(workspace: Path, name: str, px: int = 256) -> str:
    """Miniature (data URI) d'une image de la galerie ; px=0 → image entière."""
    if not _NAME.match(name):
        raise ImageError("Nom d'image invalide.")
    p = workspace / "generated" / name
    if not p.is_file():
        raise ImageError("Image introuvable.")
    data = p.read_bytes()
    if px:
        try:
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(data)); im.thumbnail((px, px)); buf = io.BytesIO(); im.save(buf, format="JPEG", quality=80)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:  # noqa: BLE001
            pass
    return "data:image/png;base64," + base64.b64encode(data).decode()


def remove(workspace: Path, name: str) -> None:
    if not _NAME.match(name):
        raise ImageError("Nom d'image invalide.")
    for ext in (".png", ".json"):
        (workspace / "generated" / (name[:-4] + ext)).unlink(missing_ok=True)


# Repère rangé à la fin du message d'EVA en base : permet de réafficher l'image dans la conversation après rechargement.
MARK = re.compile(r"\n?\[\[image:(img-\d+\.png)\]\]")


def with_mark(text: str, name: str) -> str:
    return f"{text}\n[[image:{name}]]"


def strip_marks(text: str) -> str:
    return MARK.sub("", text or "")


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def scene(prompt: str, png: bytes) -> dict:
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    return {"kind": "slides", "slides": [{"title": prompt[:80], "image": uri, "note": "Image générée localement"}]}


NOT_CONFIGURED = ("Je ne sais pas encore créer d'images : le modèle « vision » sert à comprendre tes photos, pas à en générer. "
                  "Il faut un serveur de génération d'images : lance eva-imagegen sur ton serveur IA (dossier eva-imagegen, « docker compose up -d --build »), "
                  "puis Paramètres › Génération d'images › « Détecter le serveur ».")
