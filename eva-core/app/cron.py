"""Expressions cron à 5 champs (minute heure jour mois jour-de-semaine).

Supporte : *, listes (1,15), plages (1-5), pas (*/10, 1-30/5). Le jour de
semaine va de 0 à 6 (0 = dimanche, 7 accepté pour dimanche). Si le jour du
mois ET le jour de semaine sont restreints, l'un OU l'autre suffit (comportement
cron standard). Évaluée dans le fuseau EVA_TIMEZONE.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


class CronError(ValueError):
    pass


def _parse_field(text: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        if not part:
            raise CronError("champ vide")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            if not step_s.isdigit() or int(step_s) < 1:
                raise CronError(f"pas invalide : {step_s}")
            step = int(step_s)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronError(f"plage invalide : {part}")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = int(part)
            end = hi if step > 1 else start
        else:
            raise CronError(f"valeur invalide : {part}")
        if start < lo or end > hi or start > end:
            raise CronError(f"valeur hors limites ({lo}-{hi}) : {part}")
        values.update(range(start, end + 1, step))
    return values


def parse(expr: str):
    fields = expr.split()
    if len(fields) != 5:
        raise CronError("5 champs attendus : minute heure jour mois jour-de-semaine")
    sets = [_parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _RANGES)]
    sets[4] = {0 if d == 7 else d for d in sets[4]}
    restricted_dom = fields[2] != "*"
    restricted_dow = fields[4] != "*"
    return sets, restricted_dom, restricted_dow


def next_run(expr: str, after: datetime, tz_name: str = "Europe/Paris") -> datetime:
    """Prochaine exécution strictement après `after` (datetime aware), renvoyée en UTC."""
    (minutes, hours, doms, months, dows), r_dom, r_dow = parse(expr)
    tz = ZoneInfo(tz_name)
    t = after.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = t + timedelta(days=366 * 5)
    while t < limit:
        if t.month not in months:
            t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        cron_dow = (t.weekday() + 1) % 7  # lundi=0 en Python -> dimanche=0 en cron
        if r_dom and r_dow:
            day_ok = t.day in doms or cron_dow in dows
        else:
            day_ok = t.day in doms and cron_dow in dows
        if not day_ok:
            t = t.replace(hour=0, minute=0) + timedelta(days=1)
            continue
        if t.hour not in hours:
            t = t.replace(minute=0) + timedelta(hours=1)
            continue
        if t.minute not in minutes:
            t += timedelta(minutes=1)
            continue
        return t.astimezone(ZoneInfo("UTC"))
    raise CronError("aucune exécution trouvée dans les 5 prochaines années")
