from typing import Optional

import httpx

from .base import Monitor
from ...config import settings


class OllamaWatchMonitor(Monitor):
    """Prévient quand le serveur IA local (Ollama) ne répond plus, puis quand il revient.
    Il faut 2 échecs de suite pour alerter (une coupure d'une seconde pendant un redémarrage ne compte pas)."""

    name = "ollama_watch"
    interval_seconds = 45.0

    def __init__(self, fetch=None):
        self._fetch = fetch or self._ping
        self._fails = 0
        self._down = False
        self._primed = False

    @staticmethod
    async def _ping() -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                return (await c.get(f"{settings.ollama_host.rstrip('/')}/api/tags")).status_code == 200
        except httpx.HTTPError:
            return False

    async def check(self) -> Optional[str]:
        up = await self._fetch()
        if up:
            self._fails = 0
            back = self._down
            self._down, self._primed = False, True
            return "Le serveur IA local répond de nouveau : je repasse dessus." if back else None
        self._fails += 1
        if self._fails >= 2 and not self._down:
            self._down = True
            if not self._primed:
                self._primed = True        # déjà éteint au démarrage d'EVA : on le dit quand même, une fois
            tail = ""
            from ...router import repli_airllm
            if settings.airllm_url and await repli_airllm():
                tail = " Je réponds avec AirLLM en attendant (lent)."
            return f"Le serveur IA local ne répond plus ({settings.ollama_host}).{tail}"
        return None
