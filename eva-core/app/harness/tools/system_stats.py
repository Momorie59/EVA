import asyncio
from typing import Any

import psutil

from ..permissions import Permission
from .base import Tool


class SystemStatsTool(Tool):
    name = "system_stats"
    description = (
        "Donne l'état de la machine qui héberge EVA CORE : usage CPU, "
        "mémoire, disque. Utile pour surveiller le NAS."
    )
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        def _collect():
            cpu_percent = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": cpu_percent,
                "memory": {
                    "percent": mem.percent,
                    "used_gb": round(mem.used / 1e9, 1),
                    "total_gb": round(mem.total / 1e9, 1),
                },
                "disk": {
                    "percent": disk.percent,
                    "used_gb": round(disk.used / 1e9, 1),
                    "total_gb": round(disk.total / 1e9, 1),
                },
            }

        return await asyncio.to_thread(_collect)
