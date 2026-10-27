import asyncio
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from ..permissions import Permission
from .base import Tool


def _get_client() -> docker.DockerClient:
    # Lève DockerException si le socket n'est pas monté/accessible — le
    # conteneur eva-core doit avoir /var/run/docker.sock monté (lecture
    # seule suffit pour ces outils) pour que ça fonctionne.
    return docker.from_env()


class DockerPsTool(Tool):
    name = "docker_ps"
    description = (
        "Liste les conteneurs Docker du NAS (nom, image, statut, ports). "
        "Par défaut ne montre que les conteneurs en cours d'exécution."
    )
    parameters = {
        "type": "object",
        "properties": {
            "all": {
                "type": "boolean",
                "description": "Inclure aussi les conteneurs arrêtés (défaut: false)",
            },
        },
    }
    permission = Permission.AUTO

    async def execute(self, all: bool = False, **_: Any) -> dict:  # noqa: A002
        def _list():
            client = _get_client()
            try:
                containers = client.containers.list(all=all)
                return [
                    {
                        "name": c.name,
                        "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                        "status": c.status,
                        "ports": _format_ports(c.attrs.get("NetworkSettings", {}).get("Ports", {})),
                    }
                    for c in containers
                ]
            finally:
                client.close()

        try:
            containers = await asyncio.to_thread(_list)
        except DockerException as exc:
            return {"error": f"Docker injoignable : {exc}"}

        return {"containers": containers}


class DockerLogsTool(Tool):
    name = "docker_logs"
    description = "Affiche les dernières lignes de logs d'un conteneur Docker (lecture seule)."
    parameters = {
        "type": "object",
        "properties": {
            "container": {"type": "string", "description": "Nom du conteneur"},
            "lines": {"type": "integer", "description": "Nombre de lignes à récupérer (défaut 50, max 500)"},
        },
        "required": ["container"],
    }
    permission = Permission.AUTO

    async def execute(self, container: str, lines: int = 50, **_: Any) -> dict:
        lines = max(1, min(lines, 500))

        def _logs():
            client = _get_client()
            try:
                c = client.containers.get(container)
                raw = c.logs(tail=lines).decode("utf-8", errors="replace")
                return raw
            finally:
                client.close()

        try:
            raw_logs = await asyncio.to_thread(_logs)
        except NotFound:
            return {"error": f"Conteneur introuvable : {container}"}
        except DockerException as exc:
            return {"error": f"Docker injoignable : {exc}"}

        return {"container": container, "logs": raw_logs}


def _format_ports(ports: dict) -> list[str]:
    formatted = []
    for container_port, bindings in (ports or {}).items():
        if not bindings:
            continue
        for b in bindings:
            formatted.append(f"{b.get('HostPort')}->{container_port}")
    return formatted


def _container_action(container: str, action: str):
    """Exécute une action (restart/stop/start) sur un conteneur, dans un thread."""

    def _run():
        client = _get_client()
        try:
            c = client.containers.get(container)
            getattr(c, action)()
            c.reload()
            return c.status
        finally:
            client.close()

    return _run


class DockerRestartTool(Tool):
    name = "docker_restart"
    description = "Redémarre un conteneur Docker. Action sensible : demande toujours confirmation."
    parameters = {
        "type": "object",
        "properties": {"container": {"type": "string", "description": "Nom du conteneur"}},
        "required": ["container"],
    }
    permission = Permission.CONFIRM

    async def execute(self, container: str, **_: Any) -> dict:
        try:
            status = await asyncio.to_thread(_container_action(container, "restart"))
        except NotFound:
            return {"error": f"Conteneur introuvable : {container}"}
        except DockerException as exc:
            return {"error": f"Docker injoignable : {exc}"}
        return {"container": container, "status": status}


class DockerStopTool(Tool):
    name = "docker_stop"
    description = "Arrête un conteneur Docker. Action sensible : demande toujours confirmation."
    parameters = {
        "type": "object",
        "properties": {"container": {"type": "string", "description": "Nom du conteneur"}},
        "required": ["container"],
    }
    permission = Permission.CONFIRM

    async def execute(self, container: str, **_: Any) -> dict:
        try:
            status = await asyncio.to_thread(_container_action(container, "stop"))
        except NotFound:
            return {"error": f"Conteneur introuvable : {container}"}
        except DockerException as exc:
            return {"error": f"Docker injoignable : {exc}"}
        return {"container": container, "status": status}


class DockerStartTool(Tool):
    name = "docker_start"
    description = "Démarre un conteneur Docker arrêté. Action sensible : demande toujours confirmation."
    parameters = {
        "type": "object",
        "properties": {"container": {"type": "string", "description": "Nom du conteneur"}},
        "required": ["container"],
    }
    permission = Permission.CONFIRM

    async def execute(self, container: str, **_: Any) -> dict:
        try:
            status = await asyncio.to_thread(_container_action(container, "start"))
        except NotFound:
            return {"error": f"Conteneur introuvable : {container}"}
        except DockerException as exc:
            return {"error": f"Docker injoignable : {exc}"}
        return {"container": container, "status": status}
