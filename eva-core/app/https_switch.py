"""Active ou désactive le HTTPS d'EVA depuis l'interface : recharge Caddy (conteneur eva-caddy) avec l'une ou l'autre configuration.
Le choix est gardé en base ; il est ré-appliqué au démarrage d'EVA CORE (le fichier monté par Docker, lui, reste en HTTPS)."""
import asyncio
import json
import logging

from .db import get_pool

logger = logging.getLogger("eva-core.https")
CADDY = "eva-caddy"

_ROUTES = """\thandle /ws/chat* {
\t\treverse_proxy eva-core:8000
\t}
\thandle /api/* {
\t\treverse_proxy eva-core:8000
\t}
\thandle_path /voice/* {
\t\treverse_proxy eva-voice:8100
\t}
\thandle {
\t\treverse_proxy eva-interface:80
\t}
}
"""
HTTPS_CONF = """{
\tlocal_certs
\tdefault_sni {$EVA_HOST:localhost}
\tskip_install_trust
\tauto_https disable_redirects
\ton_demand_tls {
\t\task http://eva-core:8000/api/https/ask
\t}
}

# Adresse sans nom d'hôte : EVA répond sous n'importe quel nom autorisé (IP du NAS, nom de domaine, redirection…).
# Les certificats sont fabriqués à la demande, et seulement pour les noms acceptés par EVA (/api/https/ask).
:{$EVA_HTTPS_PORT:8443} {
\ttls internal {
\t\ton_demand
\t}

""" + _ROUTES
HTTP_CONF = """{
\tauto_https off
}

:{$EVA_HTTPS_PORT:8443} {
""" + _ROUTES


NAMES_KV = "https_names"
NAME_RE = __import__("re").compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _static_ok(d: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(d)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return d == "localhost" or d.endswith((".local", ".lan", ".home.arpa", ".internal"))


async def names() -> list[str]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", NAMES_KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return d.get("names", [])


async def set_names(items: list[str]) -> list[str]:
    clean = []
    for n in items[:10]:
        n = str(n).strip().lower().rstrip(".")
        if not n:
            continue
        if not NAME_RE.match(n):
            raise ValueError(f"Nom invalide : {n} (attendu par exemple eva.mondomaine.fr).")
        if n not in clean:
            clean.append(n)
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", NAMES_KV, json.dumps({"names": clean}))
    return clean


async def allowed(domain: str) -> bool:
    """Caddy demande : peut-on fabriquer un certificat pour ce nom ? Oui pour le réseau local et les noms déclarés par l'administrateur."""
    d = (domain or "").strip().lower().rstrip(".")
    if not d or len(d) > 253:
        return False
    return _static_ok(d) or d in await names()


async def enabled() -> bool:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='https'")
    data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return bool(data.get("enabled", True))


async def _remember(on: bool) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('https', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps({"enabled": on}))


def _reload(on: bool) -> str:
    import docker
    from docker.errors import DockerException, NotFound
    try:
        client = docker.from_env()
    except DockerException as exc:
        raise RuntimeError(f"Docker injoignable depuis EVA ({exc}).") from exc
    try:
        try:
            c = client.containers.get(CADDY)
        except NotFound as exc:
            raise RuntimeError(f"Le conteneur {CADDY} est introuvable.") from exc
        import base64
        conf = HTTPS_CONF if on else HTTP_CONF
        cmd = ["sh", "-c", 'echo "$EVA_CONF" | base64 -d > /tmp/eva.caddy && caddy reload --config /tmp/eva.caddy --adapter caddyfile 2>&1']
        code, out = c.exec_run(cmd, environment={"EVA_CONF": base64.b64encode(conf.encode()).decode()})
        text = (out or b"").decode("utf-8", "replace")
        if code not in (0, None):
            raise RuntimeError(f"Caddy a refusé la nouvelle configuration : {text.strip()[:300]}")
        return text
    finally:
        client.close()


async def set_enabled(on: bool) -> dict:
    try:
        out = await asyncio.to_thread(_reload, on)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    await _remember(on)
    return {"enabled": on}


async def _has_choice() -> bool:
    async with get_pool().acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM kv WHERE key='https'"))


async def reapply_at_start() -> None:
    """Après un redémarrage, Caddy repart avec le fichier monté par Docker : on remet le réglage choisi dans EVA (HTTP, ou HTTPS « tous noms »)."""
    try:
        if await _has_choice():
            await asyncio.sleep(8)          # laisse à Caddy le temps de démarrer
            on = await enabled()
            await asyncio.to_thread(_reload, on)
            logger.info("Caddy reconfiguré au démarrage : %s.", "HTTPS" if on else "HTTP")
    except Exception:  # noqa: BLE001 — Docker absent : rien à faire
        logger.warning("Réglage HTTPS non ré-appliqué", exc_info=True)


ROOT_CRT = "/data/caddy/pki/authorities/local/root.crt"


def _root_cert() -> bytes:
    import docker
    from docker.errors import DockerException, NotFound
    try:
        client = docker.from_env()
    except DockerException as exc:
        raise RuntimeError(f"Docker injoignable depuis EVA ({exc}).") from exc
    try:
        try:
            c = client.containers.get(CADDY)
        except NotFound as exc:
            raise RuntimeError(f"Le conteneur {CADDY} est introuvable.") from exc
        code, out = c.exec_run(["cat", ROOT_CRT])
        if code not in (0, None) or b"BEGIN CERTIFICATE" not in (out or b""):
            raise RuntimeError("Certificat pas encore créé : ouvre EVA une fois en HTTPS, puis réessaie.")
        return out
    finally:
        client.close()


async def root_cert() -> bytes:
    try:
        return await asyncio.to_thread(_root_cert)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
