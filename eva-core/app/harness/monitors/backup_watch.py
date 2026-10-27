from datetime import datetime, timedelta
from typing import Optional

from .base import Monitor
from ... import backup


class BackupWatchMonitor(Monitor):
    """Prévient (une fois par jour au plus) si la dernière sauvegarde automatique date de plus de `max_age_days` jours,
    ou si aucune n'existe après la première journée de fonctionnement."""

    name = "backup_watch"
    interval_seconds = 6 * 3600.0

    def __init__(self, max_age_days: int = 8, listing=None, now=None):
        self.max_age = timedelta(days=max_age_days)
        self._listing = listing or backup.listing
        self._now = now or datetime.now
        self._started = self._now()
        self._last_alert: datetime | None = None

    async def check(self) -> Optional[str]:
        now = self._now()
        if self._last_alert and now - self._last_alert < timedelta(hours=23):
            return None
        items = self._listing()
        if not items:
            if now - self._started < timedelta(days=1):
                return None
            msg = "Aucune sauvegarde d'EVA n'existe encore (Paramètres › Sauvegarde)."
        else:
            newest = max(datetime.fromisoformat(i["created"]) for i in items)
            if now - newest <= self.max_age:
                return None
            msg = f"La dernière sauvegarde d'EVA date du {newest:%d/%m/%Y} ({(now - newest).days} jours) : vérifie la sauvegarde automatique."
        self._last_alert = now
        return msg
