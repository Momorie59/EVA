"""Routeur de modèle : choisit le modèle Ollama selon la demande.

Règles simples et prévisibles (pas de second appel au modèle) :
  image -> vision ; code -> code ; demande longue/analytique -> raisonnement ;
  salutation/question courte -> rapide ; sinon -> modèle par défaut.
Une catégorie sans modèle réglé retombe sur le modèle par défaut. Un modèle qui ne
déclare pas la capacité « tools » est utilisé sans outils."""
import json
import os
import re
import time

import httpx

from . import cloud_ai
from .config import settings
from .db import get_pool

CATEGORIES = ("fast", "code", "reasoning", "vision")
_CACHE: dict = {"at": 0.0, "models": None, "fail_at": -1e9}
_AIRLLM: dict = {"at": -1e9, "up": False}

CODE_RE = re.compile(
    r"```|\b(code|script|fonction|function|bug|erreur de syntaxe|traceback|stack ?trace|python|javascript|typescript|"
    r"php|sql|bash|dockerfile|compose|regex|refactor\w*|compile\w*|debug\w*|git|api|json|yaml|html|css|react|"
    r"classe|class|variable|boucle|algorithme)\b|\.(py|js|ts|php|sh|yml|yaml|json|sql|html|css)\b",
    re.I,
)
REASON_RE = re.compile(
    r"\b(analyse\w*|compare\w*|pourquoi|raisonn\w*|explique\w*|d[ée]montre\w*|calcule\w*|strat[ée]gie|"
    r"avantages?|inconv[ée]nients?|plan d'action|architecture|d[ée]cision|r[ée]sume\w* (?:en d[ée]tail|longuement)|"
    r"approfondi\w*|[ée]tape par [ée]tape|probl[èe]me complexe)\b",
    re.I,
)
SMALLTALK_RE = re.compile(r"^(salut|bonjour|bonsoir|coucou|hello|hey|merci|ok|d'accord|oui|non|ça va|ca va)\b", re.I)


def default_config() -> dict:
    # Modèle « rapide » par défaut (salutations, phrases courtes) : petit, il tient à côté du modèle principal
    # sur une carte de 6 Go, donc pas de rechargement. Modifiable dans Paramètres › Intelligence.
    # Profil « rapide » : un petit modèle (qwen3.5:4b, ~3,5 Go) répond à presque tout ; le principal ne sert qu'au code et
    # aux analyses poussées. Comme Jarvis en mode local : 2 à 3 fois plus rapide, un peu moins malin sur les demandes difficiles.
    return {"mode": "auto", "default": "", "fast": os.getenv("EVA_MODELE_RAPIDE", "").strip(), "code": "", "reasoning": "", "vision": "",
            "profil": os.getenv("EVA_PROFIL", "equilibre").strip() or "equilibre", "petit": os.getenv("EVA_PETIT_MODELE", "qwen3.5:4b").strip()}

PROFILS = ("equilibre", "rapide")


async def load_config() -> dict:
    cfg = default_config()
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='model_router'")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        cfg.update({k: v for k, v in data.items() if k in cfg})
    return cfg


async def save_config(new: dict) -> dict:
    cfg = default_config()
    mode = new.get("mode", "auto")
    if mode not in ("auto", "fixed"):
        raise ValueError("mode doit être auto ou fixed.")
    cfg["mode"] = mode
    installed = await installed_models()
    names = {m["name"] for m in installed} if installed else None
    for k in ("default", *CATEGORIES):
        v = (new.get(k) or "").strip()
        if v and names is not None and v not in names:
            raise ValueError(f"Modèle absent du serveur IA : {v}")
        cfg[k] = v
    profil = (new.get("profil") or cfg["profil"]).strip()
    if profil not in PROFILS:
        raise ValueError("profil doit être equilibre ou rapide.")
    cfg["profil"] = profil
    cfg["petit"] = (new.get("petit") or cfg["petit"]).strip()
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO kv (key, value) VALUES ('model_router', $1::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
            json.dumps(cfg),
        )
    return cfg


async def installed_models(force: bool = False) -> list[dict] | None:
    """Modèles installés sur Ollama, avec leurs capacités si le serveur les donne.
    Retourne None si le serveur est injoignable."""
    if not force and _CACHE["models"] is not None and time.monotonic() - _CACHE["at"] < 60:
        return _CACHE["models"]
    if not force and time.monotonic() - _CACHE["fail_at"] < 20:   # serveur IA déjà constaté hors ligne : pas de nouvelle attente de 8 s à chaque message
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
        if r.status_code != 200:
            return None
        out = []
        for m in r.json().get("models", []):
            caps = m.get("capabilities")
            out.append({
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / 1e9, 1),
                "capabilities": caps,
                "tools": ("tools" in caps) if caps is not None else None,
                "vision": ("vision" in caps) if caps is not None else None,
                "embedding": bool(caps) and "embedding" in caps and "completion" not in caps,
            })
        if settings.airllm_url:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    h = await client.get(f"{settings.airllm_url.rstrip('/')}/health")
                if h.status_code == 200:
                    out.append({"name": "airllm", "size_gb": 0, "capabilities": ["completion"], "tools": False, "vision": False,
                                "embedding": False, "slow": True})
            except httpx.HTTPError:
                pass
        try:
            out += await cloud_ai.model_entries()
        except Exception:  # noqa: BLE001
            pass
        _CACHE.update(at=time.monotonic(), models=out, fail_at=-1e9)
        return out
    except (httpx.HTTPError, ValueError):
        _CACHE["fail_at"] = time.monotonic()
        return None


async def repli_airllm() -> bool:
    """AirLLM en repli AUTOMATIQUE quand le serveur IA ne répond pas ? Non par défaut : AirLLM est un choix (sélecteur de
    modèle de la conversation). Réglable dans Paramètres › Intelligence › AirLLM."""
    try:
        from .db import get_pool
        async with get_pool().acquire() as conn:
            raw = await conn.fetchval("SELECT value FROM kv WHERE key='airllm_prefs'")
        d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
        return bool(d.get("repli_auto", False))
    except Exception:  # noqa: BLE001
        return False


async def regler_repli_airllm(actif: bool) -> bool:
    from .db import get_pool
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('airllm_prefs', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                           json.dumps({"repli_auto": bool(actif)}))
    return bool(actif)


async def airllm_up() -> bool:
    """Le service AirLLM répond-il ? (résultat gardé 20 s)"""
    if not settings.airllm_url:
        return False
    if time.monotonic() - _AIRLLM["at"] < 20:
        return _AIRLLM["up"]
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            h = await client.get(f"{settings.airllm_url.rstrip('/')}/health")
        _AIRLLM.update(at=time.monotonic(), up=h.status_code == 200)
    except httpx.HTTPError:
        _AIRLLM.update(at=time.monotonic(), up=False)
    return _AIRLLM["up"]


def suggest(models: list[dict]) -> dict:
    """Propose un réglage à partir des modèles installés (jamais appliqué sans validation)."""
    chat = [m for m in models if not m["embedding"]]
    tools = [m for m in chat if m["tools"]]
    by_size = lambda ms: sorted(ms, key=lambda m: m["size_gb"])  # noqa: E731
    pick = lambda pred, pool: next((m["name"] for m in pool if pred(m["name"])), "")  # noqa: E731
    default = settings.ollama_model if any(m["name"] == settings.ollama_model for m in chat) else (tools[0]["name"] if tools else "")
    code = pick(lambda n: "coder" in n, sorted(tools, key=lambda m: -m["size_gb"]))
    reasoning = pick(lambda n: any(x in n for x in ("nemo", "qwen3", "mistral-small", "gemma")), sorted(tools, key=lambda m: -m["size_gb"])) \
        or pick(lambda n: "phi4" in n and "mini" not in n, chat)
    fast = next((m["name"] for m in by_size(tools) if 1.0 < m["size_gb"] < 3.5 and "coder" not in m["name"]), "")
    vision = next((m["name"] for m in chat if m["vision"] and "llava" in m["name"]), "") or \
        next((m["name"] for m in chat if m["vision"]), "")
    return {"default": default, "fast": fast, "code": code, "reasoning": reasoning, "vision": vision}


def classify(text: str, has_image: bool = False) -> tuple[str, str]:
    """(catégorie, raison) — catégorie parmi default/fast/code/reasoning/vision."""
    t = (text or "").strip()
    if has_image:
        return "vision", "message avec image"
    if CODE_RE.search(t):
        return "code", "demande de code"
    if len(t) > 700 or REASON_RE.search(t):
        return "reasoning", "demande longue ou analytique"
    if len(t) <= 40 and (SMALLTALK_RE.match(t) or "?" not in t and len(t.split()) <= 4 and len(t) <= 25):
        return "fast", "échange court"
    return "default", "demande courante"


async def select(text: str, has_image: bool = False, session_model: str = "", prefer_fast: bool = False, force_cat: str = "") -> dict:
    """Choisit le modèle pour ce message. Retourne {model, category, reason, tools}."""
    cfg = await load_config()
    default = cfg["default"] or settings.ollama_model
    models = await installed_models()
    by_name = {m["name"]: m for m in models} if models else {}

    # Pas de serveur IA local utilisable (éteint, injoignable, aucun modèle de discussion) -> AirLLM et/ou IA du marché de repli.
    local_ok = bool(models) and any(not m["embedding"] and not m.get("cloud") and m["name"] != "airllm" for m in models)
    if not local_ok and not session_model and not has_image:
        try:
            cloud_model = await cloud_ai.fallback_model()
            prefer_cloud = (await cloud_ai.load())["prefer_over_airllm"]
        except Exception:  # noqa: BLE001 — base indisponible : pas de repli cloud
            cloud_model, prefer_cloud = "", False
        air = (not prefer_fast) and await repli_airllm() and await airllm_up()
        if cloud_model and (not air or prefer_cloud):
            return {"model": cloud_model, "category": "cloud", "tools": True,
                    "reason": "serveur IA local indisponible : repli sur l'IA du marché (tes messages partent sur Internet)"}
        if air:
            return {"model": "airllm", "category": "airllm", "tools": False,
                    "reason": "serveur IA local indisponible : repli sur AirLLM (réponses lentes, sans outils)"}

    if session_model:
        model, cat, reason = session_model, "manuel", "choisi pour cette conversation"
    elif cfg["mode"] == "fixed":
        model, cat, reason = default, "default", "routage désactivé"
    else:
        cat, reason = classify(text, has_image)
        if force_cat and not has_image:
            cat, reason = force_cat, "mode développeur"
        from .harness.selection import text_needs_tools
        if cat == "fast" and text_needs_tools(text):               # « allume le salon » n'est pas du bavardage : le petit modèle se trompe d'outil
            cat, reason = "default", "demande avec outils : modèle principal"
        if prefer_fast and cat in ("default", "reasoning") and cfg.get("fast") and not text_needs_tools(text):
            cat, reason = "fast", "conversation vocale : modèle rapide"
        cat_origine = cat
        configured = cfg.get(cat, "") if cat != "default" else ""
        model = configured or (settings.vision_model if cat == "vision" else default)
        if cat != "default" and not configured and cat != "vision":
            cat, reason = "default", f"{reason} (aucun modèle réglé)"
        petit = cfg.get("petit", "")
        if cfg.get("profil") == "rapide" and petit and cat_origine in ("default", "fast"):   # code, analyse, image : le principal
            if models is None or petit in by_name:
                model, cat, reason = petit, "rapide", f"{reason} — profil rapide : petit modèle"
            else:
                reason += f" — profil rapide : « {petit} » pas encore téléchargé"
    # Pas de rechargement pour gagner une seconde : si le modèle rapide n'est pas en mémoire mais que le principal l'est,
    # le principal répond (sur une carte de 6 Go, charger l'un décharge souvent l'autre : plusieurs secondes perdues).
    if cat == "fast" and not session_model and model != default and cfg.get("profil") != "rapide":
        try:
            from . import perf
            if await perf.est_charge(model) is False and await perf.est_charge(default):
                model, cat, reason = default, "default", f"{reason} — modèle principal déjà chargé (évite un rechargement)"
        except Exception:  # noqa: BLE001
            pass
    if models is not None and model not in by_name:
        reason += f" — « {model} » introuvable, repli sur {default}"
        model, cat = default, "default"
    info = by_name.get(model)
    tools = True if not info or info["tools"] is None else bool(info["tools"])
    if has_image:
        tools = False
    return {"model": model, "category": cat, "reason": reason, "tools": tools}
