"""Exécution de code Python dans un conteneur Docker jetable et isolé.

Chaque appel crée un conteneur neuf, sans réseau, sans aucun volume monté, système de
fichiers en lecture seule (sauf /tmp en mémoire), toutes les capacités Linux retirées,
utilisateur non privilégié, mémoire/CPU/processus plafonnés, durée limitée, puis le
supprime. Le code ne voit ni le workspace, ni le réseau, ni les données d'EVA."""
import asyncio
import os
from typing import Any

from ..permissions import Permission
from .base import Tool

IMAGE = os.getenv("EVA_SANDBOX_IMAGE", "python:3.12-slim")
MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 4_000
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

_client_factory = None  # injectable pour les tests


def _docker():
    if _client_factory is not None:
        return _client_factory()
    import docker
    return docker.from_env()


def _run_blocking(code: str, timeout: int) -> dict:
    client = _docker()
    try:
        client.images.get(IMAGE)
    except Exception:  # noqa: BLE001 — image absente : on la télécharge une fois
        try:
            client.images.pull(IMAGE)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Image du bac à sable introuvable ({IMAGE}) : {exc}"}
    container = client.containers.create(
        IMAGE,
        ["python", "-I", "-c", code],
        network_disabled=True,
        mem_limit="256m",
        memswap_limit="256m",
        nano_cpus=1_000_000_000,
        pids_limit=64,
        read_only=True,
        tmpfs={"/tmp": "rw,size=32m,noexec"},
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        user="65534:65534",
        working_dir="/tmp",
        environment={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
    )
    try:
        container.start()
        timed_out = False
        try:
            res = container.wait(timeout=timeout)
            exit_code = res.get("StatusCode", -1)
        except Exception:  # noqa: BLE001 — délai dépassé
            timed_out = True
            exit_code = -1
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
    truncated = len(out) > MAX_OUTPUT_CHARS
    result = {"exit_code": exit_code, "output": out[:MAX_OUTPUT_CHARS] + ("\n…(tronqué)" if truncated else "")}
    if timed_out:
        result["error"] = f"Délai dépassé ({timeout} s) : exécution interrompue."
    return result


class CodeRunTool(Tool):
    name = "code_run"
    description = (
        "Exécute du code Python 3 dans un bac à sable isolé (sans réseau, sans accès aux fichiers d'EVA, "
        "bibliothèque standard uniquement, 30 s max). Affiche les résultats avec print(). "
        "Sert aux calculs, au traitement de données et aux vérifications."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Programme Python complet, qui affiche son résultat avec print()"},
            "timeout": {"type": "integer", "description": "Durée maximale en secondes (défaut 30, max 120)"},
        },
        "required": ["code"],
    }
    # En conversation, l'utilisateur relit le code avant exécution ; un agent autonome
    # peut l'utiliser seul car le bac à sable est isolé (agent_safe).
    permission = Permission.CONFIRM
    agent_safe = True

    async def execute(self, code: str = "", timeout: int = DEFAULT_TIMEOUT, **_: Any) -> dict:
        if not code.strip():
            return {"error": "Code vide."}
        if len(code) > MAX_CODE_CHARS:
            return {"error": f"Code trop long ({MAX_CODE_CHARS} caractères maximum)."}
        try:
            timeout = min(max(int(timeout), 1), MAX_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        try:
            return await asyncio.to_thread(_run_blocking, code, timeout)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Bac à sable indisponible (Docker inaccessible ?) : {exc}"}
