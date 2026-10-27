from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .base import Monitor
from ... import papiers
from ...config import settings


class PapiersWatchMonitor(Monitor):
    """Point « papiers » du matin : une fois par jour, après EVA_PAPIERS_HEURE, EVA annonce les échéances qui
    viennent de franchir un seuil (J-30, J-7, J-1, jour J, retard). Le majordome mémorise ce qui a déjà été
    annoncé : un redémarrage d'EVA ne répète rien. Le lundi, EVA ajoute le résumé du mois."""

    name = "papiers_watch"
    interval_seconds = 15 * 60.0

    def __init__(self, now=None, hour: int | None = None):
        self._now = now or (lambda: datetime.now(ZoneInfo(settings.timezone)))
        self.hour = settings.papiers_hour if hour is None else hour
        self._last_day: str | None = None
        self._failed_day: str | None = None

    async def check(self) -> Optional[str]:
        now = self._now()
        day = now.date().isoformat()
        if now.hour < self.hour or self._last_day == day or not papiers.active():
            return None
        try:
            alertes = await papiers.alertes_du_jour()
            resume = await papiers.resume(30) if now.weekday() == 0 else ""
        except papiers.PapiersError as exc:
            if self._failed_day == day:          # on ne prévient qu'une fois par jour d'une panne
                return None
            self._failed_day = day
            return f"Je n'arrive pas à joindre le majordome pour le point papiers : {exc}"
        self._last_day = day
        return composer(alertes, resume)


def composer(alertes: list[dict], resume: str = "") -> Optional[str]:
    lignes = [a.get("message") or a.get("titre", "") for a in alertes if a.get("message") or a.get("titre")]
    if not lignes and not resume:
        return None
    if len(lignes) == 1:
        txt = f"Point papiers : {lignes[0]}"
    elif lignes:
        txt = "Point papiers :\n" + "\n".join(f"- {l}" for l in lignes)
    else:
        txt = ""
    if resume:
        txt = (txt + "\n\n" if txt else "") + f"Le point de la semaine : {resume}"
    return txt
