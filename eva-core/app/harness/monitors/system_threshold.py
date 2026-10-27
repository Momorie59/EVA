import os
from typing import Optional

from .base import Monitor
from ..tools.system_stats import SystemStatsTool


class SystemThresholdMonitor(Monitor):
    """Surveille CPU/RAM/disque et signale un dépassement de seuil — puis
    signale aussi le retour à la normale, sans re-notifier à chaque tour
    tant que ça reste au-dessus du seuil (pas de spam)."""

    name = "system_threshold"
    interval_seconds = 30.0

    def __init__(
        self,
        cpu_threshold: float | None = None,
        memory_threshold: float | None = None,
        disk_threshold: float | None = None,
    ):
        self.cpu_threshold = cpu_threshold if cpu_threshold is not None else float(
            os.getenv("EVA_CPU_THRESHOLD", "90")
        )
        self.memory_threshold = memory_threshold if memory_threshold is not None else float(
            os.getenv("EVA_MEMORY_THRESHOLD", "90")
        )
        self.disk_threshold = disk_threshold if disk_threshold is not None else float(
            os.getenv("EVA_DISK_THRESHOLD", "90")
        )
        self._tool = SystemStatsTool()
        self._exceeded: dict[str, bool] = {"cpu": False, "memory": False, "disk": False}

    async def check(self) -> Optional[str]:
        stats = await self._tool.execute()

        current = {
            "cpu": (stats["cpu_percent"], self.cpu_threshold, "processeur"),
            "memory": (stats["memory"]["percent"], self.memory_threshold, "mémoire"),
            "disk": (stats["disk"]["percent"], self.disk_threshold, "disque"),
        }

        messages = []
        for key, (value, threshold, label) in current.items():
            now_exceeded = value >= threshold
            was_exceeded = self._exceeded[key]

            if now_exceeded and not was_exceeded:
                messages.append(f"le {label} dépasse {threshold:.0f}% ({value:.0f}%)")
            elif was_exceeded and not now_exceeded:
                messages.append(f"le {label} est revenu sous {threshold:.0f}% ({value:.0f}%)")

            self._exceeded[key] = now_exceeded

        if not messages:
            return None

        return "Alerte système : " + " ; ".join(messages) + "."
