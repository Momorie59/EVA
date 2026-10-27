"""Planificateur : lance les agents dont l'heure est venue et les tâches périodiques."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from . import agents
from .db import get_pool

logger = logging.getLogger("eva-core.scheduler")

TICK_SECONDS = 20

_periodic: list[tuple[str, Callable[[], Awaitable[None]], int, list[float]]] = []


def register_periodic(name: str, fn: Callable[[], Awaitable[None]], every_seconds: int) -> None:
    _periodic.append((name, fn, every_seconds, [0.0]))


async def recover_interrupted() -> None:
    """Au démarrage : une exécution restée « running » a été coupée par un redémarrage."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            """UPDATE agent_runs SET status='error', finished_at=now(),
                   output='Erreur : exécution interrompue par un redémarrage d''EVA.'
               WHERE status='running'"""
        )


async def tick() -> int:
    """Un passage du planificateur. Retourne le nombre d'agents lancés."""
    launched = 0
    async with get_pool().acquire() as conn:
        due = await conn.fetch(
            """SELECT id, schedule_type, schedule_value FROM agents
               WHERE enabled AND schedule_type <> 'manual' AND next_run_at IS NOT NULL
                 AND next_run_at <= now()"""
        )
    for a in due:
        # On avance l'échéance AVANT de lancer, pour ne pas relancer en boucle un agent long.
        nxt = agents.compute_next(a["schedule_type"], a["schedule_value"], datetime.now(timezone.utc))
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE agents SET next_run_at=$2 WHERE id=$1", a["id"], nxt)
        try:
            await agents.start_run(a["id"], manual=False)
            launched += 1
        except agents.AlreadyRunning:
            logger.info("Agent %s déjà en cours, exécution sautée", a["id"])
    return launched


async def run_forever() -> None:
    await recover_interrupted()
    loop = asyncio.get_running_loop()
    while True:
        try:
            await tick()
            now = loop.time()
            for name, fn, every, last in _periodic:
                if now - last[0] >= every:
                    last[0] = now
                    try:
                        await fn()
                    except Exception:  # noqa: BLE001
                        logger.exception("Tâche périodique '%s' en erreur", name)
        except Exception:  # noqa: BLE001
            logger.exception("Erreur du planificateur")
        await asyncio.sleep(TICK_SECONDS)
