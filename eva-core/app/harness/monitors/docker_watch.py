from typing import Optional

from .base import Monitor
from ..tools.docker_tools import DockerPsTool


class DockerWatchMonitor(Monitor):
    """Signale un conteneur qui s'arrête ou redémarre en boucle, puis son retour à la normale.
    Silencieux si Docker n'est pas accessible (pas d'alerte répétée)."""

    name = "docker_watch"
    interval_seconds = 60.0
    BAD = {"exited", "dead", "restarting"}

    def __init__(self, tool: DockerPsTool | None = None):
        self._tool = tool or DockerPsTool()
        self._bad: set[str] = set()
        self._primed = False

    async def check(self) -> Optional[str]:
        res = await self._tool.execute(all=True)
        items = res.get("containers") if isinstance(res, dict) else None
        if not items:
            return None
        bad = {c["name"] for c in items if c.get("status") in self.BAD}
        if not self._primed:               # premier passage : on mémorise l'état sans alerter (conteneurs volontairement arrêtés)
            self._primed = True
            self._bad = bad
            return None
        down, back = sorted(bad - self._bad), sorted(self._bad - bad)
        self._bad = bad
        msgs = []
        if down:
            msgs.append("conteneur arrêté : " + ", ".join(down))
        if back:
            msgs.append("de nouveau en marche : " + ", ".join(back))
        return ("Alerte Docker : " + " ; ".join(msgs) + ".") if msgs else None
