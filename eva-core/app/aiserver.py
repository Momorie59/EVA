"""Pont avec le dashboard web du serveur IA (projet ia-local-automatique, port 7842) : EVA lit ses statistiques (CPU, mémoire, carte
graphique, disques, services, consommation) pour les afficher dans son tableau de bord, avec son propre thème, et pour répondre à
« comment va le serveur IA ? ». Lecture seule : aucun réglage du dashboard n'est modifié depuis EVA."""
import json
import re
import time
from urllib.parse import urlparse

import httpx

from .config import settings
from .db import get_pool

KV = "aiserver"
_cache: dict[str, tuple[float, dict]] = {}


def default_url() -> str:
    host = urlparse(settings.ollama_host).hostname or "127.0.0.1"
    return f"http://{host}:7842"


def clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://[A-Za-z0-9_.\-\[\]:]+(/[A-Za-z0-9_./\-]*)?$", url):
        raise ValueError("Adresse invalide. Exemple : http://192.168.1.20:7842")
    return url


async def get_url() -> str:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    data = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return data.get("url") or default_url()


async def set_url(url: str) -> str:
    url = clean_url(url) if url.strip() else ""
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps({"url": url}))
    _cache.clear()
    return url or default_url()


async def _fetch(path: str, ttl: float = 2.0) -> dict:
    base = await get_url()
    key = base + path
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    async with httpx.AsyncClient(timeout=4.0, follow_redirects=False) as c:
        r = await c.get(base + path)
    if r.status_code != 200:
        raise RuntimeError(f"le dashboard a répondu {r.status_code}")
    data = r.json()
    _cache[key] = (time.monotonic(), data)
    return data


def _pick(d: dict | None, keys: tuple[str, ...]) -> dict:
    d = d or {}
    return {k: d[k] for k in keys if k in d}


def _uptime(u) -> str:
    """Le dashboard renvoie {"seconds": …, "human": "3j 04h12m"} : on n'en garde que le texte."""
    if isinstance(u, dict):
        u = u.get("human")
    return u if isinstance(u, str) and u != "?" else ""


def normalize(raw: dict) -> dict:
    svc = raw.get("services") or {}
    return {
        "ok": True, "hostname": raw.get("hostname", ""), "uptime": _uptime(raw.get("uptime")), "ts": raw.get("ts"),
        "cpu": _pick(raw.get("cpu"), ("pct", "freq_mhz", "temp_c", "model")),
        "memory": _pick(raw.get("memory"), ("ram_total_mb", "ram_used_mb", "ram_pct", "swap_pct")),
        "gpu": _pick(raw.get("gpu"), ("available", "name", "util_pct", "temp_c", "mem_used_mb", "mem_total_mb", "mem_pct", "power_w", "power_limit_w")),
        "disks": [_pick(d, ("mount", "pct", "used_mb", "size_mb", "read_kb_s", "write_kb_s")) for d in (raw.get("disks") or [])][:8],
        "services": {
            "ollama": _pick(svc.get("ollama"), ("active", "model_count", "models")),
            "webui": _pick(svc.get("webui"), ("active",)),
            "docker": _pick(svc.get("docker"), ("active", "containers")),
        },
        "power": {k: v for k, v in (raw.get("power") or {}).items() if isinstance(v, (int, float, str)) and k != "error"} if isinstance(raw.get("power"), dict) else {},
        "install": (raw.get("progress") or {}) if isinstance(raw.get("progress"), dict) and raw["progress"].get("active") else None,
    }


async def stats() -> dict:
    url = await get_url()
    try:
        return {**normalize(await _fetch("/api/stats")), "url": url}
    except Exception as exc:  # noqa: BLE001 — serveur éteint, mauvaise adresse, dashboard non installé…
        return {"ok": False, "url": url, "error": f"Dashboard du serveur IA injoignable ({type(exc).__name__}: {exc})"}


async def power(period: str = "24h") -> dict:
    period = period if period in ("24h", "7d", "30d") else "24h"
    try:
        d = await _fetch(f"/api/power/history?period={period}", ttl=30.0)
        return {"ok": True, "period": period, "points": d.get("points", [])[:400], "avg_w": d.get("avg_w", 0), "kwh_period": d.get("kwh_period", 0), "cost": d.get("cost")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "period": period, "points": [], "error": str(exc)}


def summary(s: dict) -> str:
    if not s.get("ok"):
        return s.get("error", "indisponible")
    g, c, m = s["gpu"], s["cpu"], s["memory"]
    parts = [f"CPU {c.get('pct', '?')} %" + (f" ({c['temp_c']} °C)" if c.get("temp_c") else ""), f"RAM {m.get('ram_pct', '?')} %"]
    if g.get("available"):
        parts.append(f"GPU {g.get('name', '')} {g.get('util_pct', '?')} %, VRAM {g.get('mem_pct', '?')} %, {g.get('temp_c', '?')} °C")
    return ", ".join(parts)
