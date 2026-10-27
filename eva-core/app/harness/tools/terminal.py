import asyncio
import os
import resource
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

from ..permissions import Permission
from .base import Tool

MAX_OUTPUT_CHARS = 5000
DEFAULT_TIMEOUT = 20
MAX_TIMEOUT = 120
MAX_MEMORY_BYTES = 512 * 1024 * 1024  # 512 Mo
MAX_PROCESSES = 32  # limite les fork bombs sans bloquer un usage normal
# Note : RLIMIT_NPROC n'a AUCUN effet quand le processus tourne en root
# (CAP_SYS_RESOURCE en exempte, voir man setrlimit) — ce qui est le cas
# par défaut dans l'image Docker actuelle. Gardé pour un futur déploiement
# en utilisateur non-root, mais ne pas compter dessus tel quel.


def _apply_resource_limits(timeout_seconds: int) -> None:
    """Exécuté dans l'enfant juste avant exec() — pose des limites dures
    (mémoire, nombre de process, temps CPU) pour réduire les dégâts d'une
    commande qui dérape, et détache le process dans son propre groupe
    pour qu'on puisse tuer tous ses enfants d'un coup au timeout.
    L'isolation (disque en lecture seule, sans réseau) est ajoutée par _isolated_argv quand le noyau le permet."""
    os.setsid()
    resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
    cpu_limit = timeout_seconds + 5
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))


# --- Isolation (espaces de noms Linux, sans droit root réel) -----------------------------------------
# Dans l'isolation : le système de fichiers est en LECTURE SEULE sauf le workspace (et /tmp), le réseau est coupé,
# les autres processus sont invisibles, le socket Docker est masqué. Elle exige que le noyau/Docker autorise les
# « user namespaces » (le profil seccomp par défaut de Docker les refuse : voir docker-compose.sandbox.yml).
# Sinon on retombe sur les seules limites de ressources, et le résultat l'indique ("isolation": "limitée").
_SCRIPT = r"""
mount --make-rprivate / 2>/dev/null
WS="$1"; shift
mount --bind "$WS" "$WS" || exit 125
for s in /var/run/docker.sock /run/docker.sock; do [ -S "$s" ] && mount --bind /dev/null "$s" 2>/dev/null; done
case "$WS" in /tmp/*) ;; *) mount -t tmpfs -o size=64m tmpfs /tmp 2>/dev/null ;; esac
mount -o remount,ro,bind / || exit 125
cd "$WS" || exit 125
exec sh -c "$1"
"""
_ISO: dict = {"checked": False, "ok": False, "why": ""}


def isolation_mode() -> str:
    return os.getenv("EVA_TERMINAL_ISOLATION", "auto").lower()


def isolation_available() -> bool:
    """Teste une fois si les espaces de noms sont permis ici. Mis en cache."""
    if _ISO["checked"]:
        return _ISO["ok"]
    _ISO["checked"] = True
    if isolation_mode() == "off":
        _ISO["why"] = "désactivée (EVA_TERMINAL_ISOLATION=off)"
        return False
    if not shutil.which("unshare"):
        _ISO["why"] = "commande unshare absente"
        return False
    try:
        r = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork", "--", "sh", "-c", "mount --make-rprivate / && true"],
                           capture_output=True, timeout=10)
        _ISO["ok"] = r.returncode == 0
        if not _ISO["ok"]:
            _ISO["why"] = "le noyau ou Docker refuse les espaces de noms utilisateur (voir docker-compose.sandbox.yml)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        _ISO["why"] = f"test impossible : {exc}"
    return _ISO["ok"]


def isolation_status() -> dict:
    ok = isolation_available()
    return {"isolated": ok, "reason": "" if ok else _ISO["why"]}


def _isolated_argv(workspace: str, command: str, network: bool) -> list[str]:
    argv = ["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork", "--kill-child"]
    if not network:
        argv.append("--net")
    return argv + ["--", "sh", "-c", _SCRIPT, "sh", workspace, command]


class TerminalTool(Tool):
    name = "terminal_run"
    description = (
        "Exécute une commande shell dans le workspace d'EVA. Utile pour "
        "diagnostiquer un problème (ex: pourquoi un conteneur Docker ne "
        "démarre plus) ou lancer un script. Action sensible : demande "
        "toujours confirmation, même en lecture seule. Mémoire et temps "
        "CPU sont bornés, et la commande tourne isolée : disque en lecture seule "
        "sauf le workspace, sans réseau (mets network=true seulement si la "
        "commande en a vraiment besoin : git clone, pip install, curl…)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "La commande shell à exécuter"},
            "timeout_seconds": {
                "type": "integer",
                "description": f"Délai maximum en secondes (défaut {DEFAULT_TIMEOUT}, max {MAX_TIMEOUT})",
            },
            "network": {"type": "boolean", "description": "Autoriser le réseau pour cette commande (défaut : non)"},
        },
        "required": ["command"],
    }
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def execute(self, command: str, timeout_seconds: int = DEFAULT_TIMEOUT, network: bool = False, **_: Any) -> dict:
        timeout_seconds = max(1, min(timeout_seconds, MAX_TIMEOUT))

        isolated = await asyncio.to_thread(isolation_available)
        try:
            kw = dict(cwd=str(self.workspace_root), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                      preexec_fn=lambda: _apply_resource_limits(timeout_seconds))
            if isolated:
                proc = await asyncio.create_subprocess_exec(*_isolated_argv(str(self.workspace_root.resolve()), command, bool(network)), **kw)
            else:
                proc = await asyncio.create_subprocess_shell(command, **kw)
        except OSError as exc:
            return {"error": f"Impossible de lancer la commande : {exc}"}

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            # proc.kill() ne tuerait que le shell, pas ses enfants — comme la
            # commande tourne dans son propre groupe de process (os.setsid
            # ci-dessus), on tue le groupe entier.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
            return {"error": f"Commande interrompue après {timeout_seconds}s (timeout)."}

        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
            "stderr": stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
            "isolation": "complète (disque en lecture seule, " + ("réseau autorisé)" if network else "sans réseau)") if isolated
                         else "limitée (seulement mémoire/CPU : " + _ISO["why"] + ")",
        }
