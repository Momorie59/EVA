"""Connecteur Home Assistant (API REST locale, jeton d'accès longue durée).

Lecture : états des entités. Commandes : services (allumer, éteindre, régler…), toujours soumis à
l'accord de l'utilisateur, avec une liste d'actions sensibles INTERDITES (déverrouiller, désarmer,
ouvrir un garage/portail, éteindre Home Assistant)."""
import json
import re
from urllib.parse import urlparse

import httpx

from .config import settings
from .db import get_pool

ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
SERVICE_RE = re.compile(r"^[a-z_]+$")
FORBIDDEN_SERVICES = {
    ("lock", "unlock"), ("lock", "open"),
    ("alarm_control_panel", "alarm_disarm"), ("alarm_control_panel", "alarm_arm_home"),
    ("alarm_control_panel", "alarm_arm_away"), ("alarm_control_panel", "alarm_trigger"),
    ("cover", "open_cover"), ("cover", "toggle"),  # garages / portails / volets : à faire à la main
    ("homeassistant", "stop"), ("homeassistant", "restart"),
    ("hassio", "host_shutdown"), ("hassio", "host_reboot"),
    ("shell_command", "*"), ("python_script", "*"), ("script", "*"), ("automation", "*"),
    ("rest_command", "*"), ("persistent_notification", "*"),
}
FORBIDDEN_DOMAINS_READ = {"person", "device_tracker"}  # localisation des personnes : jamais exposée
MAX_STATES = 60


class HAError(RuntimeError):
    pass


async def _http(method: str, url: str, **kw) -> tuple[int, object]:
    """Seul point d'accès réseau (remplaçable dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise HAError(f"Home Assistant injoignable : {exc}") from exc
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:200], "text": r.text[:400000]}
    return r.status_code, data


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='homeassistant'")
    saved = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return {"url": saved.get("url") or settings.ha_url, "token": saved.get("token") or settings.ha_token}


def normalize_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HAError("Adresse invalide : attendu http://IP:8123 ou https://….")
    if p.path not in ("", "/") or p.query or p.username:
        raise HAError("Indique seulement l'adresse de base, sans chemin (ex. http://192.168.1.20:8123).")
    return u


async def save(url: str, token: str) -> dict:
    url = normalize_url(url)
    token = token.strip()
    if len(token) < 20:
        raise HAError("Jeton invalide (jeton d'accès longue durée de Home Assistant).")
    st, data = await _http("GET", f"{url}/api/", headers={"Authorization": f"Bearer {token}"})
    if st == 401:
        raise HAError("Jeton refusé par Home Assistant.")
    if st != 200:
        raise HAError(f"Home Assistant a répondu {st} : adresse incorrecte ?")
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('homeassistant',$1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                           json.dumps({"url": url, "token": token}))
    return await status()


async def remove() -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM kv WHERE key='homeassistant'")


async def status() -> dict:
    cfg = await _load()
    return {"configured": bool(cfg["url"] and cfg["token"]), "url": cfg["url"]}


async def _api(method: str, path: str, **kw):
    cfg = await _load()
    if not (cfg["url"] and cfg["token"]):
        raise HAError("Home Assistant n'est pas configuré (Paramètres → Home Assistant).")
    st, data = await _http(method, cfg["url"] + path, headers={"Authorization": f"Bearer {cfg['token']}"}, **kw)
    if st == 401:
        raise HAError("Jeton Home Assistant refusé : recrée-en un dans Paramètres.")
    if st == 404:
        raise HAError("Entité ou service introuvable.")
    if st >= 400:
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("message") or data.get("raw") or "")[:160]
        raise HAError(f"Home Assistant a répondu {st}" + (f" : {detail}" if detail else "."))
    return data


def _slim(s: dict) -> dict:
    a = s.get("attributes", {}) or {}
    return {"entity_id": s["entity_id"], "etat": s.get("state"), "nom": a.get("friendly_name", ""),
            **({"unite": a["unit_of_measurement"]} if a.get("unit_of_measurement") else {})}


async def list_states(domain: str = "", search: str = "") -> dict:
    data = await _api("GET", "/api/states")
    out = []
    for s in data:
        eid = s.get("entity_id", "")
        d = eid.split(".")[0]
        if d in FORBIDDEN_DOMAINS_READ:
            continue
        if domain and d != domain:
            continue
        slim = _slim(s)
        if search and search.lower() not in (eid + " " + slim["nom"]).lower():
            continue
        out.append(slim)
    return {"entites": out[:MAX_STATES], "total": len(out), "tronque": len(out) > MAX_STATES}


async def get_state(entity_id: str) -> dict:
    if not ENTITY_RE.match(entity_id or ""):
        raise HAError("Identifiant d'entité invalide (ex. light.salon).")
    if entity_id.split(".")[0] in FORBIDDEN_DOMAINS_READ:
        raise HAError("Cette entité n'est pas exposée à EVA.")
    s = await _api("GET", f"/api/states/{entity_id}")
    attrs = {k: v for k, v in (s.get("attributes") or {}).items() if isinstance(v, (str, int, float, bool)) or v is None}
    return {**_slim(s), "attributs": dict(list(attrs.items())[:25]), "modifie": s.get("last_changed", "")}


def check_service(domain: str, service: str) -> None:
    if not SERVICE_RE.match(domain or "") or not SERVICE_RE.match(service or ""):
        raise HAError("Service invalide (ex. light / turn_on).")
    if (domain, service) in FORBIDDEN_SERVICES or (domain, "*") in FORBIDDEN_SERVICES:
        raise HAError(f"Action interdite à EVA pour des raisons de sécurité : {domain}.{service}.")


async def call_service(domain: str, service: str, entity_id: str, data: dict | None = None) -> dict:
    check_service(domain, service)
    if not ENTITY_RE.match(entity_id or ""):
        raise HAError("Identifiant d'entité invalide.")
    if entity_id.split(".")[0] != domain and domain != "homeassistant":
        raise HAError("L'entité doit appartenir au domaine du service.")
    payload = {k: v for k, v in (data or {}).items() if k != "entity_id"}
    payload["entity_id"] = entity_id
    await _api("POST", f"/api/services/{domain}/{service}", json=payload)
    return {"ok": True, "action": f"{domain}.{service}", "entite": entity_id}


# ── Import des appareils depuis Home Assistant ───────────────────────────────
# domaine HA -> type EVA ; les serrures, alarmes, caméras, scripts, automatisations ne sont jamais proposés.
IMPORT_DOMAINS = {"light": "light", "switch": "switch", "input_boolean": "switch", "fan": "fan", "climate": "climate",
                  "cover": "cover", "media_player": "media", "scene": "other", "humidifier": "other"}
SAFE_COVER_CLASSES = {"blind", "curtain", "shade", "shutter", "awning", "damper"}      # volets / stores ; garage, portail, porte : jamais


async def cover_is_safe(entity_id: str) -> bool:
    s = await _api("GET", f"/api/states/{entity_id}")
    return (s.get("attributes") or {}).get("device_class") in SAFE_COVER_CLASSES


async def call_cover(service: str, entity_id: str) -> dict:
    """Ouvre / ferme / arrête un volet (ou store), seulement si Home Assistant le classe comme tel."""
    if service not in ("open_cover", "close_cover", "stop_cover"):
        raise HAError("Action de volet inconnue.")
    if not ENTITY_RE.match(entity_id or "") or not entity_id.startswith("cover."):
        raise HAError("Identifiant de volet invalide.")
    if not await cover_is_safe(entity_id):
        raise HAError("Cette ouverture (portail, garage, porte…) n'est pas commandable par EVA : à faire à la main.")
    await _api("POST", f"/api/services/cover/{service}", json={"entity_id": entity_id})
    return {"ok": True, "action": f"cover.{service}", "entite": entity_id}


async def import_candidates() -> dict:
    """Entités commandables de Home Assistant, avec leur pièce (zone) quand elle est connue."""
    data = await _api("GET", "/api/states")
    areas: dict[str, str] = {}
    try:                                                   # les zones n'existent que via un modèle
        cfg = await _load()
        st, txt = await _http("POST", cfg["url"] + "/api/template", headers={"Authorization": f"Bearer {cfg['token']}"},
                              json={"template": "{% for s in states %}{{ s.entity_id }}|{{ area_name(s.entity_id) or '' }}\n{% endfor %}"})
        raw = (txt.get("text") or txt.get("raw") or "") if isinstance(txt, dict) else (txt if isinstance(txt, str) else "")
        for line in (raw or "").splitlines():
            if "|" in line:
                k, v = line.split("|", 1)
                areas[k.strip()] = v.strip()
    except HAError:
        pass
    out = []
    for st_ in data:
        eid = st_.get("entity_id", "")
        dom = eid.split(".")[0]
        if dom not in IMPORT_DOMAINS:
            continue
        a = st_.get("attributes") or {}
        if dom == "cover" and a.get("device_class") not in SAFE_COVER_CLASSES:
            continue
        if a.get("entity_id") and isinstance(a["entity_id"], list):   # groupes de lumières : on garde, c'est pratique
            pass
        out.append({"entity_id": eid, "name": a.get("friendly_name") or eid, "room": areas.get(eid, ""), "type": IMPORT_DOMAINS[dom],
                    "state": st_.get("state")})
    out.sort(key=lambda x: (x["room"] or "~", x["type"], x["name"].lower()))
    return {"entities": out[:400], "total": len(out)}


# ── Annonces sur les Echo (Alexa), via l'intégration « Alexa Media Player » de Home Assistant (comme Jarvis) ──

async def echos() -> list[dict]:
    """Enceintes Alexa vues par Home Assistant (lecteurs média de l'intégration Alexa Media Player)."""
    out = []
    for s in await _api("GET", "/api/states"):
        eid, at = s.get("entity_id", ""), s.get("attributes") or {}
        if eid.startswith("media_player.") and ("last_called" in at or "echo" in eid or "alexa" in eid):
            out.append({"entity_id": eid, "nom": at.get("friendly_name", eid)})
    return out


async def annonce_alexa(texte: str, piece: str = "") -> list[str]:
    """Annonce sur les Echo de la pièce (ou partout). Liste vide si Home Assistant ou l'intégration ne sont pas là."""
    try:
        lst = await echos()
    except Exception:  # noqa: BLE001 — pas de Home Assistant : rien à faire
        return []
    n = (piece or "").strip().lower()
    if n and n not in ("partout", "tous", "toute la maison", "toutes les pièces"):
        lst = [e for e in lst if n in e["nom"].lower() or n in e["entity_id"].lower()]
    if not lst:
        return []
    await _api("POST", "/api/services/notify/alexa_media",
               json={"message": texte[:500], "target": [e["entity_id"] for e in lst], "data": {"type": "announce"}})
    return [e["nom"] for e in lst]
