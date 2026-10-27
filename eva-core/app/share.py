"""Partage réseau des projets (Windows / macOS / Linux) activable depuis la page Projets.

EVA démarre un petit serveur Samba (conteneur Docker « eva-share ») qui expose le dossier projets/ du workspace.
Un seul utilisateur (« eva »), mot de passe choisi dans la page ; les fichiers créés côté Windows appartiennent à l'utilisateur 1000,
le même qu'EVA : les deux côtés peuvent écrire. Les modifications sont visibles des deux côtés tout de suite."""
import asyncio
import json
import os
import re
from pathlib import Path

from .config import settings
from .db import get_pool

IMAGE = os.getenv("EVA_SHARE_IMAGE", "dperson/samba:latest")
CONTAINER = "eva-share"
SHARE_NAME = "projets"
USER = "eva"
DEFAULT_PORT = 445
PW_RE = re.compile(r"^[A-Za-z0-9._@#%+=!-]{6,64}$")

_client_factory = None   # injectable pour les tests


class ShareError(Exception):
    pass


def _docker():
    if _client_factory is not None:
        return _client_factory()
    import docker
    return docker.from_env()


async def load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='project_share'")
    data = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return {"enabled": bool(data.get("enabled")), "password": data.get("password", ""), "port": int(data.get("port") or DEFAULT_PORT)}


async def _save(cfg: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('project_share', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(cfg))


def _find(client):
    try:
        return client.containers.get(CONTAINER)
    except Exception:  # noqa: BLE001 — absent
        return None


def _state_blocking() -> dict:
    try:
        c = _find(_docker())
    except Exception as exc:  # noqa: BLE001
        return {"docker": False, "running": False, "error": f"Docker inaccessible : {exc}"}
    if c is None:
        return {"docker": True, "running": False}
    try:
        c.reload()
    except Exception:  # noqa: BLE001
        pass
    return {"docker": True, "running": getattr(c, "status", "") == "running"}


async def status() -> dict:
    cfg = await load()
    st = await asyncio.to_thread(_state_blocking)
    return {"enabled": cfg["enabled"], "password": cfg["password"], "port": cfg["port"], "user": USER, "share": SHARE_NAME,
            "running": st.get("running", False), "error": st.get("error", "")}


def _friendly(exc: Exception, port: int) -> str:
    msg = str(exc)
    low = msg.lower()
    if "already allocated" in low or "address already in use" in low or "port is already" in low:
        return (f"Le port {port} est déjà utilisé sur le NAS (probablement le service SMB d'OpenMediaVault). "
                "Désactive SMB dans OpenMediaVault, ou choisis un autre port (puis connecte-toi avec ce port).")
    if "permission" in low or "denied" in low:
        return f"Docker a refusé l'opération : {msg}"
    return f"Impossible de démarrer le partage : {msg}"


def _enable_blocking(ws: Path, password: str, port: int) -> None:
    from . import sandbox_proj
    client = _docker()
    (ws / "projets").mkdir(parents=True, exist_ok=True)
    old = _find(client)
    if old is not None:
        try:
            old.remove(force=True)
        except Exception:  # noqa: BLE001
            pass
    try:
        client.images.get(IMAGE)
    except Exception:  # noqa: BLE001
        client.images.pull(IMAGE)
    m = sandbox_proj._workspace_mount(client)
    vol = {m["volume"]: {"bind": "/share", "mode": "rw"}} if "volume" in m else {m["bind"]: {"bind": "/share", "mode": "rw"}}
    cmd = ["-u", f"{USER};{password};1000;{USER};1000", "-s", f"{SHARE_NAME};/share/projets;yes;no;no;{USER};{USER};{USER}", "-w", "WORKGROUP"]
    c = client.containers.create(IMAGE, command=cmd, name=CONTAINER, ports={"445/tcp": port}, volumes=vol, detach=True,
                                 restart_policy={"Name": "unless-stopped"}, labels={"eva.managed": "share"})
    try:
        c.start()
    except Exception:
        try:
            c.remove(force=True)
        except Exception:  # noqa: BLE001
            pass
        raise


def _disable_blocking() -> None:
    c = _find(_docker())
    if c is not None:
        c.remove(force=True)


async def apply(ws: Path, enabled: bool, password: str | None = None, port: int | None = None) -> dict:
    cfg = await load()
    if password is not None:
        cfg["password"] = password
    if port is not None:
        cfg["port"] = int(port)
    if not (1 <= cfg["port"] <= 65535):
        raise ShareError("Port invalide.")
    if enabled:
        if not PW_RE.match(cfg["password"] or ""):
            raise ShareError("Mot de passe : 6 à 64 caractères (lettres, chiffres, . _ @ # % + = ! -), sans espace ni point-virgule.")
        try:
            await asyncio.to_thread(_enable_blocking, ws, cfg["password"], cfg["port"])
        except Exception as exc:  # noqa: BLE001
            cfg["enabled"] = False
            await _save(cfg)
            raise ShareError(_friendly(exc, cfg["port"])) from exc
    else:
        try:
            await asyncio.to_thread(_disable_blocking)
        except Exception as exc:  # noqa: BLE001
            raise ShareError(f"Impossible d'arrêter le partage : {exc}") from exc
    cfg["enabled"] = enabled
    await _save(cfg)
    return await status()


async def ensure_running(ws: Path) -> None:
    """Au démarrage d'EVA : si le partage est activé mais que son conteneur a disparu, on le recrée."""
    cfg = await load()
    if not cfg["enabled"]:
        return
    st = await asyncio.to_thread(_state_blocking)
    if st.get("docker") and not st.get("running"):
        await asyncio.to_thread(_enable_blocking, ws, cfg["password"], cfg["port"])
