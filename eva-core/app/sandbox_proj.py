"""Bac à sable de projet : EVA (ou toi) peut y exécuter du Python, installer des paquets pip et utiliser une base
PostgreSQL de test, sans toucher à ses propres données.

Isolation : chaque exécution a lieu dans un conteneur Docker jetable (système de fichiers en lecture seule, aucune capacité Linux,
utilisateur non privilégié, mémoire/CPU/processus plafonnés) qui ne voit que le dossier du projet.
Réseau : aucun par défaut ; « db » = réseau interne qui ne joint que la base de test ; « internet » = sortie web (pip), à confirmer.
Base de test : une base `sbx_<projet>` dans le Postgres d'EVA, avec un rôle `eva_sandbox` qui n'a accès à rien d'autre."""
import asyncio
import json
import os
import re
import secrets
import socket
from pathlib import Path
from urllib.parse import urlparse, unquote

from .config import settings
from .db import get_pool

IMAGE = os.getenv("EVA_SANDBOX_IMAGE", "python:3.12-slim")
NET_DB = "eva-sandbox-db"          # interne : pas de sortie vers Internet
NET_WEB = "eva-sandbox-web"        # sortie Internet (installation de paquets)
ROLE = "eva_sandbox"
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 600
MAX_OUTPUT = 8000
PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-\[\],<>=!~]*$")

_client_factory = None       # injectable pour les tests
_mount_override = None       # idem : {"volume": nom} ou {"bind": chemin}
_sem = asyncio.Semaphore(2)


def _docker():
    if _client_factory is not None:
        return _client_factory()
    import docker
    return docker.from_env()


def db_name(slug: str) -> str:
    return ("sbx_" + re.sub(r"[^a-z0-9]", "_", slug.lower()))[:60]


def _dsn_parts() -> dict:
    u = urlparse(settings.database_url)
    return {"host": u.hostname or "localhost", "port": u.port or 5432, "dbname": (u.path or "/eva").lstrip("/") or "eva"}


# ---------------------------------------------------------------- base de test
async def _password(conn) -> str:
    raw = await conn.fetchval("SELECT value FROM kv WHERE key='sandbox_db'")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data.get("password"):
            return data["password"]
    pw = secrets.token_urlsafe(18)
    await conn.execute("INSERT INTO kv (key, value) VALUES ('sandbox_db', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps({"password": pw}))
    return pw


async def _ensure_role(conn) -> str:
    pw = await _password(conn)
    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", ROLE)
    lit = pw.replace("'", "''")
    if not exists:
        await conn.execute(f"CREATE ROLE {ROLE} LOGIN PASSWORD '{lit}' NOSUPERUSER NOCREATEDB NOCREATEROLE")
    else:
        await conn.execute(f"ALTER ROLE {ROLE} PASSWORD '{lit}'")
    # Le rôle de test ne doit pas pouvoir ouvrir la base principale d'EVA.
    main = _dsn_parts()["dbname"]
    await conn.execute(f'REVOKE CONNECT ON DATABASE "{main}" FROM PUBLIC')
    return pw


def dsn_for(slug: str, pw: str, host: str | None = None) -> str:
    p = _dsn_parts()
    return f"postgresql://{ROLE}:{pw}@{host or p['host']}:{p['port']}/{db_name(slug)}"


async def db_exists(slug: str) -> bool:
    async with get_pool().acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name(slug)))


async def ensure_db(slug: str) -> dict:
    name = db_name(slug)
    async with get_pool().acquire() as conn:
        pw = await _ensure_role(conn)
        existed = bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name))
        if not existed:
            await conn.execute(f'CREATE DATABASE "{name}" OWNER {ROLE}')
    return {"database": name, "created": not existed, "dsn": dsn_for(slug, pw)}


async def drop_db(slug: str) -> bool:
    name = db_name(slug)
    async with get_pool().acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name):
            return False
        await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    return True


async def reset_db(slug: str) -> dict:
    await drop_db(slug)
    return await ensure_db(slug)


async def query(slug: str, sql: str, limit: int = 200) -> dict:
    import asyncpg
    if not sql.strip():
        return {"error": "Requête vide."}
    info = await ensure_db(slug)
    try:
        conn = await asyncio.wait_for(asyncpg.connect(info["dsn"]), 10)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Connexion à la base de test impossible : {exc}"}
    try:
        await conn.execute("SET statement_timeout = '20s'")
        try:
            stmt = await conn.prepare(sql)
        except Exception as exc:  # noqa: BLE001 — plusieurs commandes séparées par « ; » : exécution simple
            if "multiple commands" in str(exc):
                return {"status": await conn.execute(sql)}
            raise
        attrs = stmt.get_attributes()
        if attrs:
            rows = await stmt.fetch()
            cols = [a.name for a in attrs]
            data = [[_cell(v) for v in r.values()] for r in rows[:limit]]
            return {"columns": cols, "rows": data, "row_count": len(rows), "truncated": len(rows) > limit}
        status = await conn.execute(sql)
        return {"status": status}
    except Exception as exc:  # noqa: BLE001 — erreur SQL : renvoyée au modèle pour qu'il corrige
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        await conn.close()


def _cell(v):
    if v is None or isinstance(v, (int, float, bool, str)):
        return v
    return str(v)


async def tables(slug: str) -> dict:
    return await query(slug, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")


# ------------------------------------------------------------------ conteneur
def _workspace_mount(client) -> dict:
    """Comment le volume du workspace est monté dans CE conteneur (pour le remonter dans le conteneur jetable)."""
    if _mount_override is not None:
        return _mount_override
    forced = os.getenv("EVA_WORKSPACE_VOLUME", "").strip()
    if forced:
        return {"bind": forced} if forced.startswith("/") else {"volume": forced}
    me = client.containers.get(socket.gethostname())
    dest = str(Path(settings.workspace_root).resolve())
    for m in me.attrs.get("Mounts", []):
        if m.get("Destination") == dest:
            return {"volume": m["Name"]} if m.get("Type") == "volume" and m.get("Name") else {"bind": m["Source"]}
    raise RuntimeError("Volume du workspace introuvable parmi les montages du conteneur EVA.")


def _ensure_networks(client, need_db: bool, need_web: bool) -> None:
    def net(name, internal):
        try:
            return client.networks.get(name)
        except Exception:  # noqa: BLE001
            return client.networks.create(name, driver="bridge", internal=internal)
    if need_db:
        n = net(NET_DB, True)
        host = _dsn_parts()["host"]
        try:
            c = client.containers.get(host)
            if NET_DB not in c.attrs.get("NetworkSettings", {}).get("Networks", {}):
                n.connect(c, aliases=[host])
        except Exception:  # noqa: BLE001 — base introuvable : la connexion échouera avec un message clair
            pass
    if need_web:
        net(NET_WEB, False)


def _blocking_run(slug: str, command: str, timeout: int, network: str, env_extra: dict) -> dict:
    client = _docker()
    try:
        client.images.get(IMAGE)
    except Exception:  # noqa: BLE001
        try:
            client.images.pull(IMAGE)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Image du bac à sable introuvable ({IMAGE}) : {exc}"}
    m = _workspace_mount(client)
    vol = {m["volume"]: {"bind": "/ws", "mode": "rw"}} if "volume" in m else {m["bind"]: {"bind": "/ws", "mode": "rw"}}
    _ensure_networks(client, network == "db", network == "internet")
    work = f"/ws/projets/{slug}"
    env = {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
           "PIP_CACHE_DIR": "/tmp/pip", "PYTHONPATH": f"{work}/.deps:{work}", "PATH": f"{work}/.deps/bin:/usr/local/bin:/usr/bin:/bin", **env_extra}
    kwargs = dict(
        command=["sh", "-c", command], volumes=vol, working_dir=work, environment=env, user="1000:1000",
        mem_limit="1g", memswap_limit="1g", nano_cpus=2_000_000_000, pids_limit=256, read_only=True,
        tmpfs={"/tmp": "rw,size=512m,exec"}, cap_drop=["ALL"], security_opt=["no-new-privileges"],
    )
    if network == "none":
        kwargs["network_disabled"] = True
    else:
        kwargs["network"] = NET_DB if network == "db" else NET_WEB
    container = client.containers.create(IMAGE, **kwargs)
    timed_out = False
    try:
        container.start()
        try:
            exit_code = container.wait(timeout=timeout).get("StatusCode", -1)
        except Exception:  # noqa: BLE001
            timed_out, exit_code = True, -1
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass
        out = container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
    finally:
        try:
            container.remove(force=True)
        except Exception:  # noqa: BLE001
            pass
    cut = len(out) > MAX_OUTPUT
    if cut:
        out = out[:MAX_OUTPUT // 2] + "\n…(milieu tronqué)…\n" + out[-MAX_OUTPUT // 2:]
    res = {"exit_code": exit_code, "output": out, "network": network}
    if timed_out:
        res["error"] = f"Délai dépassé ({timeout} s) : exécution interrompue."
    return res


async def run(ws: Path, slug: str, command: str, timeout: int = DEFAULT_TIMEOUT, internet: bool = False) -> dict:
    from . import projects
    projects.project_dir(ws, slug)   # valide le projet
    if not command.strip():
        return {"error": "Commande vide."}
    try:
        timeout = min(max(int(timeout), 1), MAX_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    env_extra, network = {}, "none"
    if internet:
        network = "internet"
    elif await db_exists(slug):
        network = "db"
    if network == "db":
        async with get_pool().acquire() as conn:
            pw = await _password(conn)
        env_extra["DATABASE_URL"] = dsn_for(slug, pw)
        env_extra["SANDBOX_DATABASE_URL"] = env_extra["DATABASE_URL"]
    try:
        async with _sem:
            return await asyncio.to_thread(_blocking_run, slug, command, timeout, network, env_extra)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Bac à sable indisponible (Docker inaccessible ?) : {exc}"}


async def install(ws: Path, slug: str, packages: list[str]) -> dict:
    pk = [p.strip() for p in packages if p and p.strip()]
    if not pk:
        return {"error": "Aucun paquet indiqué."}
    for p in pk:
        if not PKG_RE.match(p):
            return {"error": f"Nom de paquet refusé : {p!r}"}
    cmd = "pip install --no-input --target .deps " + " ".join(f"'{p}'" for p in pk)
    return await run(ws, slug, cmd, timeout=MAX_TIMEOUT, internet=True)


async def status(ws: Path, slug: str) -> dict:
    from . import projects
    d = projects.project_dir(ws, slug)
    deps = d / ".deps"
    pk = sorted(p.name for p in deps.glob("*.dist-info"))[:60] if deps.is_dir() else []
    return {"database": db_name(slug), "db": await db_exists(slug), "deps": deps.is_dir(),
            "packages": [re.sub(r"\.dist-info$", "", n) for n in pk]}
