"""IA du marché (facultatif) : OpenAI, Anthropic, Gemini, Mistral, Groq, DeepSeek, OpenRouter ou tout service « compatible OpenAI ».

EVA reste locale par défaut : rien n'est envoyé sur Internet tant que tu n'as pas ajouté un fournisseur ET choisi un de ses
modèles (sélecteur de la conversation, attribution du routeur) ou activé le repli. Les messages de la conversation sont alors
transmis à ce service. Les clés sont stockées dans la base d'EVA et ne ressortent jamais en clair par l'API.

Les modèles s'appellent « cloud:<fournisseur>/<modèle> » (ex. cloud:openai/gpt-4o-mini)."""
import json
import re
import uuid
from typing import AsyncGenerator, Optional

import httpx

from .db import get_pool

PREFIX = "cloud:"
KV_KEY = "cloud_ai"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

PRESETS = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "example": "gpt-4o-mini"},
    "anthropic": {"label": "Anthropic (Claude)", "base_url": "https://api.anthropic.com/v1", "example": "claude-sonnet-4-5"},
    "gemini": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "example": "gemini-2.5-flash"},
    "mistral": {"label": "Mistral", "base_url": "https://api.mistral.ai/v1", "example": "mistral-small-latest"},
    "groq": {"label": "Groq", "base_url": "https://api.groq.com/openai/v1", "example": "llama-3.3-70b-versatile"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "example": "deepseek-chat"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "example": "openrouter/auto"},
    "custom": {"label": "Autre (compatible OpenAI)", "base_url": "", "example": ""},
}


class CloudError(RuntimeError):
    def __init__(self, msg: str, statut: int = 0, attente: float = 0.0):
        super().__init__(msg)
        self.statut, self.attente = statut, attente


def is_cloud(model: Optional[str]) -> bool:
    return bool(model) and model.startswith(PREFIX)


def split(model: str) -> tuple[str, str]:
    pid, _, name = model[len(PREFIX):].partition("/")
    return pid, name


# ---------- configuration (base de données) ----------

async def load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV_KEY)
    data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    rot = data.get("rotation") or {}
    return {"providers": data.get("providers", {}), "prefer_over_airllm": bool(data.get("prefer_over_airllm", False)),
            "rotation": {"ordre": [str(x) for x in rot.get("ordre", [])], "exclus": [str(x) for x in rot.get("exclus", [])],
                         "exclure_entrainement": bool(rot.get("exclure_entrainement", True)),
                         "repli": bool(rot.get("repli", False))}}


async def save(cfg: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV_KEY, json.dumps(cfg))


def public(cfg: dict) -> dict:  # noqa: D401
    """Vue sans clé : seule une indication « clé enregistrée » sort."""
    out = {}
    for pid, p in cfg["providers"].items():
        out[pid] = {**{k: v for k, v in p.items() if k != "api_key"}, "has_key": bool(p.get("api_key"))}
    return {"providers": out, "prefer_over_airllm": cfg["prefer_over_airllm"], "presets": PRESETS,
            "rotation": {**cfg.get("rotation", {}), "services": etat_rotation(cfg)}}


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if "{account_id}" in url:
        raise ValueError("Remplace {account_id} dans l'adresse par l'identifiant de ton compte Cloudflare (tableau de bord Cloudflare, colonne de droite).")
    if not re.match(r"^https?://[^\s/]+", url):
        raise ValueError("Adresse du service invalide (https://…).")
    return url


async def upsert(pid: str, body: dict) -> dict:
    pid = (pid or "").strip().lower()
    if not ID_RE.match(pid):
        raise ValueError("Identifiant invalide (lettres minuscules, chiffres, - et _).")
    cfg = await load()
    old = cfg["providers"].get(pid, {})
    preset = body.get("preset") or old.get("preset") or "custom"
    if preset not in PRESETS:
        raise ValueError("Fournisseur inconnu.")
    base = body.get("base_url") or old.get("base_url") or PRESETS[preset]["base_url"]
    key = (body.get("api_key") or "").strip() or old.get("api_key", "")
    models = body.get("models", old.get("models", []))
    if isinstance(models, str):
        models = [m for m in re.split(r"[,\s]+", models) if m]
    models = [m.strip() for m in models if isinstance(m, str) and re.match(r"^[\w.:/@+-]{1,100}$", m.strip())][:50]
    cfg["providers"][pid] = {
        "preset": preset, "label": (body.get("label") or old.get("label") or PRESETS[preset]["label"])[:40],
        "base_url": _clean_url(base), "api_key": key, "models": models,
        "enabled": bool(body.get("enabled", old.get("enabled", True))),
        "fallback": bool(body.get("fallback", old.get("fallback", False))),
        "vision": bool(body.get("vision", old.get("vision", False))),
        # Services gratuits (liste awesome-free-llm-apis) : certains marchent sans clé (accès anonyme, limites plus basses).
        "sans_cle": bool(body.get("sans_cle", old.get("sans_cle", False))),
        "gratuit": bool(body.get("gratuit", old.get("gratuit", False))),
        "cree": old.get("cree") or __import__("time").time(),           # ordre d'ajout (la base ne garde pas l'ordre des clés)
        "entrainement": ent if (ent := (body.get("entrainement") if body.get("entrainement") is not None else old.get("entrainement", ""))) in ("", "oui", "hors_ue") else "",
        # Budget (comme Jarvis) : prix en € par million de jetons, plafond mensuel ; 0 = pas de plafond.
        "prix_entree": _nombre(body["prix_entree"] if body.get("prix_entree") is not None else old.get("prix_entree", 0)),
        "prix_sortie": _nombre(body["prix_sortie"] if body.get("prix_sortie") is not None else old.get("prix_sortie", 0)),
        "budget_mois": _nombre(body["budget_mois"] if body.get("budget_mois") is not None else old.get("budget_mois", 0)),
    }
    if "prefer_over_airllm" in body:
        cfg["prefer_over_airllm"] = bool(body["prefer_over_airllm"])
    await save(cfg)
    return public(cfg)


def _nombre(v) -> float:
    try:
        return max(0.0, round(float(str(v).replace(",", ".").strip() or 0), 4))
    except ValueError as exc:
        raise ValueError("Prix et budget : des nombres (ex. 0,15).") from exc


# ---------- budget mensuel ----------

USAGE_KEY = "cloud_usage"
_prevenu: set[str] = set()


def _mois() -> str:
    from datetime import date
    return date.today().strftime("%Y-%m")


async def _usage() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", USAGE_KEY)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def compter(pid: str, jetons_entree: int, jetons_sortie: int) -> None:
    p = (await load())["providers"].get(pid, {})
    eur = (jetons_entree * p.get("prix_entree", 0) + jetons_sortie * p.get("prix_sortie", 0)) / 1_000_000
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1 FOR UPDATE", USAGE_KEY)
            d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
            m = d.setdefault(_mois(), {}).setdefault(pid, {"entree": 0, "sortie": 0, "eur": 0.0, "appels": 0})
            m["entree"] += int(jetons_entree or 0)
            m["sortie"] += int(jetons_sortie or 0)
            m["eur"] = round(m["eur"] + eur, 6)
            m["appels"] += 1
            for k in sorted(d)[:-13]:                     # un an d'historique
                d.pop(k, None)
            await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                               USAGE_KEY, json.dumps(d))


async def depenses() -> dict:
    """Ce mois-ci, par fournisseur : jetons, euros, budget, atteint ou non."""
    u = (await _usage()).get(_mois(), {})
    out = {}
    for pid, p in (await load())["providers"].items():
        x = u.get(pid, {"entree": 0, "sortie": 0, "eur": 0.0, "appels": 0})
        out[pid] = {**x, "budget": p.get("budget_mois", 0), "atteint": bool(p.get("budget_mois")) and x["eur"] >= p["budget_mois"]}
    return {"mois": _mois(), "fournisseurs": out}


async def dans_budget(model: str) -> bool:
    if not is_cloud(model):
        return True
    pid, _ = split(model)
    p = (await load())["providers"].get(pid, {})
    if not p.get("budget_mois"):
        return True
    x = (await _usage()).get(_mois(), {}).get(pid, {})
    if x.get("eur", 0) < p["budget_mois"]:
        return True
    cle = f"{_mois()}:{pid}"
    if cle not in _prevenu:                              # une seule alerte par mois et par fournisseur
        _prevenu.add(cle)
        try:
            from .connections import connection_manager
            await connection_manager._hooks({"type": "proactive", "text": f"💶 Budget du mois atteint pour {p.get('label', pid)} "
                                             f"({x.get('eur', 0):.2f} € / {p['budget_mois']:.2f} €) : EVA repasse sur le modèle local jusqu'au mois prochain."})
        except Exception:  # noqa: BLE001
            pass
    return False


async def remove(pid: str) -> dict:
    cfg = await load()
    cfg["providers"].pop(pid, None)
    await save(cfg)
    return public(cfg)


async def model_entries() -> list[dict]:
    """Modèles du marché proposés à côté de ceux d'Ollama (format de router.installed_models)."""
    cfg = await load()
    out = []
    if eligibles(cfg):                                   # « IA gratuites (automatique) » : passe de l'une à l'autre toute seule
        out.append({"name": MODELE_AUTO, "size_gb": 0, "capabilities": ["completion", "tools"], "tools": True, "vision": False,
                    "embedding": False, "cloud": True, "provider": "IA gratuites (automatique)", "gratuit": True,
                    "services": list(dict.fromkeys(p.get("label", pid) for pid, p, _m in eligibles(cfg)))})
    for pid, p in cfg["providers"].items():
        if not p.get("enabled") or not (p.get("api_key") or p.get("sans_cle")):
            continue
        for m in p.get("models", []):
            out.append({"name": f"{PREFIX}{pid}/{m}", "size_gb": 0, "capabilities": ["completion", "tools"] + (["vision"] if p.get("vision") else []),
                        "tools": True, "vision": bool(p.get("vision")), "embedding": False, "cloud": True, "provider": p.get("label", pid),
                        "gratuit": bool(p.get("gratuit")), "entrainement": entrainement(p) if p.get("gratuit") else ""})
    return out


async def fallback_model() -> str:
    """Repli quand le serveur IA local ne répond pas : la rotation des IA gratuites si elle est cochée « repli »,
    sinon le premier modèle d'un fournisseur marqué « repli », ou ''."""
    cfg = await load()
    if cfg.get("rotation", {}).get("repli") and eligibles(cfg):
        return MODELE_AUTO
    for pid, p in cfg["providers"].items():
        if p.get("enabled") and p.get("fallback") and (p.get("api_key") or p.get("sans_cle")) and p.get("models"):
            return f"{PREFIX}{pid}/{p['models'][0]}"
    return ""


# ---------- appels ----------

def _headers(p: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if p.get("api_key"):
        h["Authorization"] = f"Bearer {p['api_key']}"
    if p.get("preset") == "anthropic":
        h.update({"x-api-key": p["api_key"], "anthropic-version": "2023-06-01"})
    return h


async def _provider(pid: str) -> dict:
    p = (await load())["providers"].get(pid)
    if not p or not p.get("enabled"):
        raise CloudError(f"Fournisseur « {pid} » introuvable ou désactivé (Paramètres › IA du marché).")
    if not p.get("api_key") and not p.get("sans_cle"):
        raise CloudError(f"Aucune clé enregistrée pour « {pid} ».")
    return p


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Format Ollama -> format OpenAI : identifiants d'appels d'outils, arguments en texte JSON, images en data-URI."""
    out, pending = [], []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments") or {}
                cid = tc.get("id") or "call_" + uuid.uuid4().hex[:12]
                pending.append((cid, fn.get("name", "")))
                calls.append({"id": cid, "type": "function",
                              "function": {"name": fn.get("name", ""), "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": calls})
        elif role == "tool":
            idx = next((i for i, (_, n) in enumerate(pending) if n == m.get("name")), 0 if pending else None)
            cid = pending.pop(idx)[0] if idx is not None else "call_" + uuid.uuid4().hex[:12]
            out.append({"role": "tool", "tool_call_id": cid, "content": str(m.get("content", ""))})
        elif role in ("system", "user", "assistant"):
            if m.get("images"):
                parts = [{"type": "text", "text": str(m.get("content", ""))}]
                parts += [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in m["images"]]
                out.append({"role": role, "content": parts})
            else:
                out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def _error_text(resp_text: str, status: int) -> str:
    try:
        d = json.loads(resp_text)
        msg = (d.get("error") or {}).get("message") if isinstance(d.get("error"), dict) else d.get("error") or d.get("message")
        return f"{status} : {str(msg)[:250]}"
    except (ValueError, AttributeError):
        return f"{status} : {resp_text[:200]}"


async def stream(messages: list[dict], tools: Optional[list[dict]], model: str) -> AsyncGenerator[tuple[str, object], None]:
    """Même protocole que ollama_client.stream_decide : ("content", t) …, ("usage", {...}), ("tool_calls", liste|None)."""
    pid, name = split(model)
    if pid == AUTO:
        async for ev in _rotation(messages, tools):
            yield ev
        return
    async for ev in _un(pid, await _provider(pid), name, messages, tools):
        yield ev


async def _un(pid: str, p: dict, name: str, messages: list[dict], tools: Optional[list[dict]]) -> AsyncGenerator[tuple[str, object], None]:
    payload = {"model": name, "messages": to_openai_messages(messages), "stream": True, "stream_options": {"include_usage": True}}
    if tools:
        payload["tools"] = tools
    calls: dict[int, dict] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_duration_ms": 0}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            async with client.stream("POST", p["base_url"] + "/chat/completions", json=payload, headers=_headers(p)) as r:
                if r.status_code != 200:
                    try:
                        attente = float(r.headers.get("retry-after") or 0)
                    except ValueError:
                        attente = 0.0
                    raise CloudError(f"{p.get('label', pid)} a répondu {_error_text((await r.aread()).decode(errors='ignore'), r.status_code)}",
                                     r.status_code, attente)
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        ev = json.loads(data)
                    except ValueError:
                        continue
                    if ev.get("usage"):
                        usage["prompt_tokens"] = ev["usage"].get("prompt_tokens", 0) or 0
                        usage["completion_tokens"] = ev["usage"].get("completion_tokens", 0) or 0
                    for ch in ev.get("choices") or []:
                        d = ch.get("delta") or {}
                        if d.get("content"):
                            yield ("content", d["content"])
                        for tc in d.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
    except httpx.TimeoutException as exc:
        raise CloudError(f"{p.get('label', pid)} n'a pas répondu à temps.") from exc
    except httpx.HTTPError as exc:
        raise CloudError(f"{p.get('label', pid)} injoignable (Internet ?) : {type(exc).__name__}") from exc
    if not usage["prompt_tokens"] and not usage["completion_tokens"]:     # service qui ne donne pas l'usage : estimation (4 caractères ≈ 1 jeton)
        usage["prompt_tokens"] = sum(len(str(m.get("content", ""))) for m in messages) // 4
    try:
        await compter(pid, usage["prompt_tokens"], usage["completion_tokens"])
    except Exception:  # noqa: BLE001 — le compteur ne doit jamais casser une réponse
        pass
    yield ("usage", usage)
    out = []
    for i in sorted(calls):
        c = calls[i]
        try:
            args = json.loads(c["args"]) if c["args"].strip() else {}
        except ValueError:
            args = {}
        out.append({"id": c["id"], "function": {"name": c["name"], "arguments": args}})
    yield ("tool_calls", out or None)

# ---------- rotation automatique entre les IA gratuites ----------

AUTO = "auto"
MODELE_AUTO = f"{PREFIX}{AUTO}/gratuit"
_pauses: dict[str, dict] = {}            # « fournisseur|modèle » (ou fournisseur entier) → {"jusqua": horodatage, "raison": texte}
_derniers: dict[str, dict] = {}          # « fournisseur|modèle » → {"ok": horodatage} ou {"erreur": texte}


_COPIE_GRATUITES: dict | None = None


def entrainement(p: dict) -> str:
    """« oui » si ce service peut entraîner ses modèles avec les messages. Fournisseur ajouté avant que l'info soit gardée :
    on la retrouve dans la liste des IA gratuites livrée avec EVA (par son adresse)."""
    global _COPIE_GRATUITES
    if "entrainement" in p:
        return p.get("entrainement") or ""
    if _COPIE_GRATUITES is None:
        try:
            from . import ia_gratuites
            data = ia_gratuites.normaliser(json.loads(ia_gratuites.COPIE.read_text(encoding="utf-8")))
            _COPIE_GRATUITES = {s["base_url"].rstrip("/"): s["entrainement"] for s in data["services"]}
        except Exception:  # noqa: BLE001
            _COPIE_GRATUITES = {}
    return _COPIE_GRATUITES.get((p.get("base_url") or "").rstrip("/"), "")


def _cle(pid: str, modele: str) -> str:
    return f"{pid}|{modele}"


def entrees(cfg: dict) -> list[dict]:
    """Toutes les IA gratuites ajoutées, modèle par modèle (les quotas sont souvent comptés par modèle), dans l'ordre choisi,
    avec ce qui empêche éventuellement de s'en servir : clé manquante, décochée, exclue (entraînement)."""
    rot = cfg.get("rotation", {})
    exclus = set(rot.get("exclus", []))
    out = []
    for pid, p in cfg["providers"].items():
        if not p.get("gratuit"):
            continue
        for m in p.get("models", []):
            cle = _cle(pid, m)
            bloque = ""
            if not p.get("enabled", True):
                bloque = "service désactivé"
            elif not (p.get("api_key") or p.get("sans_cle")):
                bloque = "clé manquante (Modifier › colle ta clé gratuite)"
            elif rot.get("exclure_entrainement", True) and entrainement(p) == "oui":
                bloque = "exclu : peut entraîner ses modèles avec tes messages"
            out.append({"cle": cle, "pid": pid, "p": p, "modele": m, "coche": cle not in exclus, "bloque": bloque})
    rang = {c: i for i, c in enumerate(rot.get("ordre", []))}
    ancien = {pid: i for i, pid in enumerate(rot.get("ordre", []))}           # ordre enregistré avant (par service)
    out.sort(key=lambda e: (rang.get(e["cle"], ancien.get(e["pid"], 10_000)), e["p"].get("cree", 0), e["pid"], e["p"]["models"].index(e["modele"])))
    return out


def eligibles(cfg: dict) -> list[tuple[str, dict, str]]:
    """Ce que la rotation essaie vraiment : (fournisseur, réglages, modèle)."""
    return [(e["pid"], e["p"], e["modele"]) for e in entrees(cfg) if e["coche"] and not e["bloque"]]


def _pause_pour(exc: CloudError) -> tuple[float, bool]:
    """Combien de temps laisser de côté (secondes), et si c'est tout le service (clé, crédits) ou seulement ce modèle."""
    texte = str(exc).lower()
    if exc.statut == 429:
        journee = bool(re.search(r"day|daily|jour|rpd|per.day|quota", texte))     # quota du jour : en général tout le compte
        m = re.search(r"retry after (\d+)", texte)
        attente = exc.attente or (float(m.group(1)) if m else 0)
        if attente:
            return min(max(attente, 20), 86400), journee
        return (6 * 3600 if journee else 90), journee
    if exc.statut == 402:
        return 24 * 3600, True                       # crédits gratuits du mois épuisés
    if exc.statut in (401, 403):
        return 3600, True                            # clé refusée : à vérifier dans Paramètres
    if exc.statut in (400, 404, 422):
        return 1800, False                           # modèle retiré, outils non pris en charge…
    return 120, False                                # panne passagère, délai dépassé, pas d'Internet


def _en_pause(pid: str, cle: str) -> dict:
    import time as _t
    for k in (cle, pid):
        x = _pauses.get(k, {})
        if x.get("jusqua", 0) > _t.time():
            return x
    return {}


def etat_rotation(cfg: dict) -> list[dict]:
    out = []
    for e in entrees(cfg):
        pause = _en_pause(e["pid"], e["cle"])
        out.append({"cle": e["cle"], "id": e["pid"], "label": e["p"].get("label", e["pid"]), "modele": e["modele"], "coche": e["coche"],
                    "bloque": e["bloque"], "pause_jusqua": int(pause["jusqua"]) if pause else None, "raison": pause.get("raison", ""),
                    **_derniers.get(e["cle"], {})})
    return out


async def regler_rotation(ordre: list | None = None, exclure_entrainement: bool | None = None, repli: bool | None = None,
                          exclus: list | None = None) -> dict:
    cfg = await load()
    rot = cfg["rotation"]
    connues = {e["cle"] for e in entrees(cfg)}
    if ordre is not None:
        rot["ordre"] = [str(x) for x in ordre if str(x) in connues][:200]
    if exclus is not None:
        rot["exclus"] = [str(x) for x in exclus if str(x) in connues][:200]
    if exclure_entrainement is not None:
        rot["exclure_entrainement"] = bool(exclure_entrainement)
    if repli is not None:
        rot["repli"] = bool(repli)
    await save(cfg)
    return {**rot, "services": etat_rotation(cfg)}


async def _rotation(messages: list[dict], tools: Optional[list[dict]]) -> AsyncGenerator[tuple[str, object], None]:
    """Essaie les IA gratuites l'une après l'autre (modèle par modèle) : quota atteint, clé refusée, panne… → la suivante,
    sans rien dire. Ce qui a échoué est mis de côté le temps qu'il faut (minute, quelques heures, jusqu'au lendemain)."""
    import time as _t
    cfg = await load()
    essais = eligibles(cfg)
    if not essais:
        raise CloudError("Aucune IA gratuite prête : ajoute-en (avec leur clé gratuite) dans Paramètres › Intelligence › IA du marché › IA gratuites.")
    rates = []
    for pid, p, modele in essais:
        cle = _cle(pid, modele)
        pause = _en_pause(pid, cle)
        if pause:
            rates.append(f"{p.get('label', pid)} {modele} (en pause jusqu'à {_t.strftime('%H:%M', _t.localtime(pause['jusqua']))})")
            continue
        if p.get("budget_mois") and not await dans_budget(f"{PREFIX}{pid}/x"):
            continue
        commence = False
        try:
            async for ev in _un(pid, p, modele, messages, tools):
                if ev[0] == "content":
                    commence = True
                yield ev
            _derniers[cle] = {"ok": int(_t.time())}
            return
        except CloudError as exc:
            if commence:                              # la réponse avait commencé : on ne la recommence pas ailleurs
                raise
            duree, tout = _pause_pour(exc)
            _pauses[pid if tout else cle] = {"jusqua": _t.time() + duree, "raison": str(exc)[:160]}
            _derniers[cle] = {"erreur": str(exc)[:160]}
            rates.append(f"{p.get('label', pid)} {modele} ({str(exc)[:90]})")
    raise CloudError("Toutes les IA gratuites sont occupées ou à court de quota pour l'instant. Ajoute d'autres services gratuits "
                     "(Paramètres › IA du marché › IA gratuites) ou réessaie plus tard. Détail : " + " ; ".join(rates))


async def complete(messages: list[dict], tools: Optional[list[dict]], model: str) -> dict:
    text, tcs = "", None
    async for kind, v in stream(messages, tools, model):
        if kind == "content":
            text += v
        elif kind == "tool_calls":
            tcs = v
    msg = {"role": "assistant", "content": text}
    if tcs:
        msg["tool_calls"] = tcs
    return msg


async def test(pid: str) -> dict:
    """Vérifie la clé et renvoie la liste des modèles du service (si disponible)."""
    p = await _provider(pid)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(p["base_url"] + "/models", headers=_headers(p))
    except httpx.HTTPError as exc:
        raise CloudError(f"Service injoignable : {type(exc).__name__}") from exc
    if r.status_code in (401, 403):
        raise CloudError("Clé refusée par le service.")
    if r.status_code != 200:
        return {"ok": True, "models": [], "note": f"Clé non vérifiée (liste des modèles indisponible : {r.status_code})."}
    items = r.json().get("data") or r.json().get("models") or []
    ids = sorted({(i.get("id") or i.get("name") or "").removeprefix("models/") for i in items if isinstance(i, dict)} - {""})
    return {"ok": True, "models": ids[:200]}


async def upsert_prefs(prefer_over_airllm: bool) -> dict:
    cfg = await load()
    cfg["prefer_over_airllm"] = bool(prefer_over_airllm)
    await save(cfg)
    return public(cfg)
