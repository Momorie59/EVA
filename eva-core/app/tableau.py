"""Tableau de bord « au repos » de la fenêtre flottante du PC (comme le HUD de Jarvis façon Echo Show).

Quand personne ne parle à EVA, la petite fenêtre du satellite affiche des tuiles en lecture seule : météo, prochains
rendez-vous, colis en route, musique en cours, post-its. Chaque tuile respecte les droits du compte du satellite (agenda
et colis : fonction Google ; musique : fonction Musique) ; une source en panne n'empêche pas les autres. Mis en cache
quelques minutes : la fenêtre redemande toutes les 5 minutes, sans charge pour le NAS."""
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import features
from .config import settings

CACHE_S = 240
_cache: dict[str, tuple[float, dict]] = {}


async def _meteo() -> dict | None:
    from .harness.tools.weather import WeatherTool
    r = await WeatherTool().execute(city=settings.default_city, days=1)
    if r.get("error"):
        return None
    cur = r.get("current") or {}
    j = (r.get("forecast") or [{}])[0]
    temp = cur.get("temperature_c")
    return {"titre": "Météo", "icone": "☀", "lignes": [
        f"{r.get('city') or settings.default_city} : {round(temp) if isinstance(temp, (int, float)) else '?'} °C, {cur.get('condition', '')}",
        f"Aujourd'hui {j.get('temp_min', '?')}–{j.get('temp_max', '?')} °C"
        + (f", pluie {j['precipitation_probability_max']} %" if j.get("precipitation_probability_max") else "")]}


def _heure(iso: str, tz: ZoneInfo) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if len(iso) <= 10:
        return d.strftime("%d/%m")
    d = d.astimezone(tz)
    auj = datetime.now(tz).date()
    jour = "" if d.date() == auj else ("demain " if (d.date() - auj).days == 1 else d.strftime("%d/%m "))
    return f"{jour}{d.strftime('%H:%M')}"


async def _agenda(user: str) -> dict | None:
    from . import agendas, google
    tz = ZoneInfo(settings.timezone)
    evs = []
    try:
        if (await google.status()).get("connected"):
            evs += [{"titre": e["titre"], "debut": e["debut"] or ""} for e in (await google.calendar_list(3, 6)).get("evenements", [])]
    except Exception:  # noqa: BLE001
        pass
    try:
        evs += [{"titre": e["titre"], "debut": e["debut"]} for e in (await agendas.a_venir(user, 3)).get("evenements", [])]
    except Exception:  # noqa: BLE001
        pass
    maintenant = datetime.now(tz).isoformat()
    evs = sorted((e for e in evs if e["debut"] and (len(e["debut"]) <= 10 or e["debut"] >= maintenant[:16])), key=lambda e: e["debut"])[:3]
    if not evs:
        return None
    return {"titre": "Agenda", "icone": "📅", "lignes": [f"{_heure(e['debut'], tz)}  {e['titre']}"[:60] for e in evs]}


async def _colis() -> dict | None:
    from . import colis, google
    if not (await google.status()).get("connected"):
        return None
    c = (await colis.en_cours(7)).get("colis", [])
    if not c:
        return None
    return {"titre": "Colis", "icone": "📦", "lignes": [f"{x['marchand']} : {x['statut']}"[:60] for x in c[:3]]}


async def _musique() -> dict | None:
    from . import spotify
    r = await spotify.en_cours()
    if not r.get("lecture"):
        return None
    return {"titre": "En écoute", "icone": "🎵", "lignes": [f"{r.get('titre', '')}"[:60], f"{r.get('artiste', '')}"[:60]]}


async def _postits() -> dict | None:
    from . import notes
    n = [x for x in await notes.list_notes(include_done=False)][:3]
    if not n:
        return None
    return {"titre": "Post-it", "icone": "📝", "lignes": [x["text"][:60] for x in n]}


async def composer(cle: str, role: str, user: str) -> dict:
    hit = _cache.get(cle)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    feats = await features.effective(role, user)
    sources = [_meteo()]
    if "google" in feats:
        sources += [_agenda(user), _colis()]
    if "musique" in feats:
        sources.append(_musique())
    sources.append(_postits())

    async def sur(c):
        try:
            return await asyncio.wait_for(c, 20)
        except Exception:  # noqa: BLE001 — une tuile en panne ne bloque pas les autres
            return None
    tuiles = [t for t in await asyncio.gather(*(sur(c) for c in sources)) if t]
    out = {"tuiles": tuiles, "maj": int(time.time())}
    _cache[cle] = (time.monotonic(), out)
    return out
