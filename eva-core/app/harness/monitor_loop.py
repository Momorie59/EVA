import asyncio
import logging

from ..connections import connection_manager
from ..memory import save_message
from .monitors.base import Monitor

logger = logging.getLogger("eva-core.monitor_loop")


async def _run_one(monitor: Monitor, session_id: str) -> None:
    while True:
        try:
            notification = await monitor.check()
        except Exception:  # noqa: BLE001 — un monitor qui plante ne doit pas arrêter les autres
            logger.exception("Erreur dans le monitor '%s'", monitor.name)
            notification = None

        if notification:
            logger.info("Notification proactive (%s) : %s", monitor.name, notification)
            await save_message(session_id, "assistant", notification)
            await connection_manager.broadcast(
                session_id,
                {"type": "proactive", "text": notification, "source": monitor.name},
            )

        await asyncio.sleep(monitor.interval_seconds)


def start_monitors(monitors: list[Monitor], session_id: str = "default") -> list[asyncio.Task]:
    """Lance chaque monitor dans sa propre tâche de fond, à son propre
    intervalle. Retourne les tâches pour pouvoir les annuler à l'arrêt."""
    return [asyncio.create_task(_run_one(m, session_id)) for m in monitors]
