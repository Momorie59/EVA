"""Agendas iCal (comme Jarvis) : abonnements .ics de chaque personne — vacances scolaires, agenda Outlook ou iCloud partagé,
club de sport, collège… EVA les lit (lecture seule) pour répondre « qu'est-ce que j'ai cette semaine ? » et dans le briefing.

Chaque personne gère ses propres abonnements (Paramètres › Services connectés › Agendas) ; personne d'autre ne les voit."""
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import settings
from .db import get_pool

_cache: dict[str, tuple[float, bytes]] = {}
CACHE_S = 15 * 60


class AgendaError(RuntimeError):
    pass


def _cle(qui: str) -> str:
    return f"agendas:{(qui or '').lower()}"


async def lister(qui: str) -> list[dict]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", _cle(qui))
    return ((json.loads(raw) if isinstance(raw, str) else raw) or {}).get("agendas", [])


async def _ecrire(qui: str, agendas: list[dict]) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           _cle(qui), json.dumps({"agendas": agendas}))


def _url(u: str) -> str:
    u = (u or "").strip()
    if u.startswith("webcal://"):
        u = "https://" + u[len("webcal://"):]
    if not re.match(r"^https?://\S+$", u):
        raise AgendaError("Adresse d'agenda invalide (https://… ou webcal://…, se termine souvent par .ics).")
    return u


async def ajouter(qui: str, nom: str, url: str) -> list[dict]:
    url = _url(url)
    nom = " ".join(str(nom or "").split())[:40] or "Agenda"
    await _telecharger(url)                                  # vérifie tout de suite que c'est un agenda lisible
    lst = [a for a in await lister(qui) if a["url"] != url]
    lst.append({"nom": nom, "url": url})
    await _ecrire(qui, lst[:20])
    return lst


async def retirer(qui: str, url: str) -> list[dict]:
    lst = [a for a in await lister(qui) if a["url"] != url]
    await _ecrire(qui, lst)
    return lst


async def _http_get(url: str) -> bytes:
    """Seul accès réseau (remplaçable dans les tests). Même garde-fou que web_fetch : pas d'adresse du réseau local."""
    from .harness.tools.web import _check_url_safe
    if (err := _check_url_safe(url)):
        raise AgendaError(err)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "EVA-agenda/1.0"}) as cl:
            r = await cl.get(url)
    except httpx.HTTPError as exc:
        raise AgendaError(f"Agenda injoignable ({type(exc).__name__}).") from exc
    if r.status_code >= 300:
        raise AgendaError(f"Agenda refusé ({r.status_code}) : le lien est-il toujours public ?")
    return r.content[:8_000_000]


async def _telecharger(url: str) -> bytes:
    import time
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    data = await _http_get(url)
    if b"BEGIN:VCALENDAR" not in data[:2000]:
        raise AgendaError("Ce lien ne renvoie pas un agenda iCal (.ics).")
    _cache[url] = (time.time(), data)
    return data


def evenements_ics(data: bytes, debut: datetime, fin: datetime, nom: str, tz: ZoneInfo) -> list[dict]:
    import icalendar
    import recurring_ical_events
    cal = icalendar.Calendar.from_ical(data)
    out = []
    for ev in recurring_ical_events.of(cal).between(debut, fin):
        d0 = ev.get("DTSTART").dt if ev.get("DTSTART") else None
        d1 = ev.get("DTEND").dt if ev.get("DTEND") else None
        journee = isinstance(d0, date) and not isinstance(d0, datetime)
        if isinstance(d0, datetime):
            d0 = (d0 if d0.tzinfo else d0.replace(tzinfo=tz)).astimezone(tz)
        if isinstance(d1, datetime):
            d1 = (d1 if d1.tzinfo else d1.replace(tzinfo=tz)).astimezone(tz)
        out.append({"agenda": nom, "titre": str(ev.get("SUMMARY", "") or "(sans titre)")[:160], "lieu": str(ev.get("LOCATION", "") or "")[:120],
                    "journee": journee, "debut": d0.isoformat() if d0 else "", "fin": d1.isoformat() if d1 else "",
                    "_tri": d0.isoformat() if journee else (d0.isoformat() if d0 else "")})
    return out


async def a_venir(qui: str, jours: int = 7, agenda: str = "") -> dict:
    lst = await lister(qui)
    if agenda:
        lst = [a for a in lst if agenda.lower() in a["nom"].lower()]
    if not lst:
        raise AgendaError("Aucun agenda iCal abonné (Paramètres › Services connectés › Agendas).")
    tz = ZoneInfo(settings.timezone)
    debut = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = debut + timedelta(days=max(1, min(int(jours or 7), 62)))
    evs, erreurs = [], []
    for a in lst:
        try:
            evs += evenements_ics(await _telecharger(a["url"]), debut, fin, a["nom"], tz)
        except Exception as exc:  # noqa: BLE001 — un agenda en panne n'empêche pas les autres
            erreurs.append(f"{a['nom']} : {exc}"[:160])
    evs.sort(key=lambda e: e.pop("_tri"))
    return {"du": debut.date().isoformat(), "au": (fin - timedelta(days=1)).date().isoformat(), "evenements": evs[:150],
            **({"erreurs": erreurs} if erreurs else {})}
