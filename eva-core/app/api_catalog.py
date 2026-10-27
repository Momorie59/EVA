"""Mise à jour automatique du catalogue d'API publiques (dépôt public-apis, README sur GitHub).

Le catalogue fourni avec EVA sert de base ; une copie plus récente, téléchargée automatiquement (1 fois par semaine, ou
sur demande), est gardée en base et prend le relais. Les NOUVELLES API sont signalées à l'utilisateur."""
import json
import logging
import re
import time

import httpx

from .db import get_pool

logger = logging.getLogger("eva-core.api_catalog")

SOURCE = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
INTERVAL_S = 7 * 86400
MIN_ENTRIES = 500                 # garde-fou : un README illisible ou vidé ne remplace jamais le catalogue
MAX_BYTES = 3_000_000
_ROW = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)\s]+)\)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(Yes|No)\s*\|\s*(Yes|No|Unknown)\s*\|\s*$")


def parse_readme(text: str) -> list[dict]:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## Index")), None)
    if start is None:
        return []
    cat, out, seen = None, [], set()
    for ln in lines[start:]:
        if ln.startswith("### "):
            cat = ln[4:].strip()
            continue
        m = _ROW.match(ln)
        if not (m and cat):
            continue
        name, url, desc, auth, https, _cors = m.groups()
        auth = auth.strip("`").strip()
        url = url.split("?utm")[0]
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        out.append({"n": name[:80], "u": url[:300], "d": desc[:300], "a": "" if auth.lower() in ("no", "") else auth[:30], "h": https == "Yes", "c": cat})
    return out


async def _get(key: str):
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", key)
    return (json.loads(raw) if isinstance(raw, str) else raw) if raw else None


async def _set(key: str, value) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", key, json.dumps(value, ensure_ascii=False))


async def load_saved() -> None:
    """Au démarrage : reprend la copie à jour si elle existe."""
    from .harness.tools import api_tools
    entries = await _get("public_apis")
    if isinstance(entries, list) and len(entries) >= MIN_ENTRIES:
        api_tools.set_catalog(entries)


async def status() -> dict:
    from .harness.tools import api_tools
    meta = await _get("public_apis_meta") or {}
    cat = api_tools.catalog()
    return {"total": len(cat), "keyless": sum(1 for e in cat if not e["a"]), "updated_at": meta.get("updated_at"),
            "last_check": meta.get("last_check"), "last_error": meta.get("last_error", ""), "recent": meta.get("recent", [])[:20]}


async def update(force: bool = False, fetch=None) -> dict:
    from .harness.tools import api_tools
    meta = await _get("public_apis_meta") or {}
    now = time.time()
    if not force and now - float(meta.get("last_check") or 0) < INTERVAL_S:
        return {"ran": False}
    meta["last_check"] = now
    try:
        if fetch is None:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                r = await c.get(SOURCE)
            r.raise_for_status()
            text = r.text if len(r.content) <= MAX_BYTES else ""
        else:
            text = await fetch()
        fresh = parse_readme(text)
        if len(fresh) < MIN_ENTRIES:
            raise ValueError(f"README illisible ({len(fresh)} API trouvées) : catalogue conservé.")
    except Exception as exc:  # noqa: BLE001 — pas de réseau, GitHub injoignable… on garde l'ancien catalogue
        meta["last_error"] = str(exc)[:200]
        await _set("public_apis_meta", meta)
        return {"ran": True, "error": meta["last_error"], "new": 0}
    have = {e["u"] for e in api_tools.catalog()}
    new = [e for e in fresh if e["u"] not in have]
    api_tools.set_catalog(fresh)
    await _set("public_apis", fresh)
    meta.update(updated_at=now, last_error="")
    stamp = time.strftime("%Y-%m-%d")
    meta["recent"] = ([{"n": e["n"], "c": e["c"], "u": e["u"], "a": e["a"], "date": stamp} for e in new[:40]] + meta.get("recent", []))[:60]
    await _set("public_apis_meta", meta)
    if new and have:                                   # (le tout premier téléchargement ne « notifie » pas des centaines d'API)
        try:
            from .connections import connection_manager
            from .memory import save_message
            from .sessions import ensure_session
            text = f"🔌 {len(new)} nouvelle(s) API publique(s) ajoutée(s) au catalogue : " + ", ".join(e["n"] for e in new[:8]) + (" …" if len(new) > 8 else "")
            await ensure_session("default")
            await save_message("default", "assistant", text)
            await connection_manager.broadcast_all({"type": "proactive", "text": text, "source": "api_catalog"})
        except Exception:  # noqa: BLE001
            logger.warning("Notification des nouvelles API impossible", exc_info=True)
    return {"ran": True, "new": len(new), "total": len(fresh)}


async def periodic() -> None:
    await update(force=False)
