import logging
from pathlib import Path
from typing import Optional

from .base import Monitor

logger = logging.getLogger("eva-core.monitor.workspace")
IGNORED_TOP = {"uploads", "generated", ".eva-history"}


class WorkspaceWatchMonitor(Monitor):
    """Surveille le workspace d'EVA et signale les fichiers apparus,
    modifiés ou disparus depuis la dernière vérification.

    C'est le premier "agent continu" façon Jarvis : elle remarque un
    changement dans son environnement et le signale sans qu'on lui
    demande — plutôt qu'un outil qu'on invoque sur demande.
    """

    name = "workspace_watch"
    interval_seconds = 10.0

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._last_snapshot: dict[str, float] | None = None

    def _snapshot(self) -> dict[str, float]:
        snapshot = {}
        if not self.workspace_root.exists():
            return snapshot
        for path in self.workspace_root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self.workspace_root))
                if rel.split("/", 1)[0] in IGNORED_TOP:   # fichiers déposés / images créées : pas de bruit, ni de parcours coûteux
                    continue
                snapshot[rel] = path.stat().st_mtime
        return snapshot

    async def check(self) -> Optional[str]:
        current = self._snapshot()

        if self._last_snapshot is None:
            # Premier passage : on mémorise l'état sans rien signaler,
            # sinon EVA "découvrirait" tout le workspace existant au démarrage.
            self._last_snapshot = current
            return None

        previous = self._last_snapshot
        self._last_snapshot = current

        added = [p for p in current if p not in previous]
        removed = [p for p in previous if p not in current]
        modified = [p for p in current if p in previous and current[p] != previous[p]]

        if not (added or removed or modified):
            return None

        parts = []
        if added:
            parts.append("créé " + ", ".join(added))
        if modified:
            parts.append("modifié " + ", ".join(modified))
        if removed:
            parts.append("supprimé " + ", ".join(removed))

        return "J'ai remarqué dans le workspace : " + " ; ".join(parts) + "."
