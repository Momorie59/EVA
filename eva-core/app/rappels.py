"""Rappels et minuteurs : « rappelle-moi d'appeler le garage à 17 h », « minuteur 10 minutes », « rappelle-moi tous les jours
à 8 h de prendre mon café ».

Le rappel sonne là où on l'a demandé : dans l'interface (message d'EVA, lu à voix haute si on parlait), sur le satellite
de la pièce (à voix haute), et sur Telegram si c'est réglé. Une heure passée tombe le lendemain ; « dans 10 minutes »,
« demain matin », « lundi à 9 h », « le 3 novembre à 14 h »… sont compris sans le modèle."""
import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import get_pool

logger = logging.getLogger("eva-core.rappels")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rappels (
    id SERIAL PRIMARY KEY,
    qui TEXT NOT NULL DEFAULT '',
    texte TEXT NOT NULL,
    quand TIMESTAMPTZ NOT NULL,
    recurrence TEXT NOT NULL DEFAULT '',
    session TEXT NOT NULL DEFAULT '',
    piece TEXT NOT NULL DEFAULT '',
    fait BOOLEAN NOT NULL DEFAULT FALSE,
    cree TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rappels_a_venir ON rappels(quand) WHERE NOT fait;
"""
RECURRENCES = {"": None, "jour": timedelta(days=1), "semaine": timedelta(days=7), "heure": timedelta(hours=1)}
MAX_PAR_PERSONNE = 200


class RappelError(ValueError):
    pass


def _plat(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower().replace("’", "'"))
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").split())


_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
            "onze": 11, "douze": 12, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40, "quarante-cinq": 45, "cinquante": 50,
            "soixante": 60, "quelques": 3}
_JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
_MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
         "octobre": 10, "novembre": 11, "decembre": 12}
_MOMENTS = {"matin": (8, 0), "midi": (12, 0), "apres-midi": (15, 0), "apres midi": (15, 0), "soir": (19, 0), "ce soir": (19, 0),
            "nuit": (22, 0), "minuit": (0, 0)}


def _nb(mot: str) -> float | None:
    mot = mot.replace(",", ".")
    try:
        return float(mot)
    except ValueError:
        return _NOMBRES.get(mot)


def comprendre(texte: str, maintenant: datetime | None = None) -> datetime:
    """Heure d'un rappel à partir d'une phrase française (ou d'une date ISO). Lève RappelError si rien n'est compris."""
    tz = ZoneInfo(settings.timezone)
    now = (maintenant or datetime.now(tz)).astimezone(tz)
    t = _plat(texte)
    if not t:
        raise RappelError("Quand ? (« dans 10 minutes », « à 17 h », « demain matin »…)")
    try:                                                   # ISO : 2026-10-28T08:00
        d = datetime.fromisoformat(texte.strip())
        return (d if d.tzinfo else d.replace(tzinfo=tz)).astimezone(timezone.utc)
    except ValueError:
        pass
    # « dans 10 minutes », « dans 1 h 30 », « dans une heure et demie », « dans 2 jours »
    m = re.search(r"\bdans\s+(.+)$", t)
    if m:
        reste, delta = m.group(1), timedelta()
        for qte, unite in re.findall(r"([\d.,]+|[a-z-]+)\s*(secondes?|s\b|minutes?|mins?|mn|heures?|h\b|jours?|semaines?)", reste):
            n = _nb(qte)
            if n is None:
                continue
            u = unite[0] if not unite.startswith("se") else ("s" if unite.startswith("sec") else "w")
            delta += {"s": timedelta(seconds=n), "m": timedelta(minutes=n), "h": timedelta(hours=n), "j": timedelta(days=n),
                      "w": timedelta(weeks=n)}[u]
        hm = re.search(r"(\d+)\s*h\s*(\d{1,2})\b", reste)              # « dans 1h30 »
        if hm and not re.search(r"\d+\s*h\s*\d{1,2}\s*(minutes?|mn)", reste):
            delta = timedelta(hours=int(hm.group(1)), minutes=int(hm.group(2)))
        if "et demie" in reste:
            delta += timedelta(minutes=30) if re.search(r"heures?\s+et demie", reste) else timedelta()
        if re.search(r"\b(une )?demi[- ]heure\b", reste) and not delta:
            delta = timedelta(minutes=30)
        if delta <= timedelta():
            raise RappelError(f"Je n'ai pas compris la durée « {texte} ».")
        return (now + delta).astimezone(timezone.utc)
    # jour visé
    jour = now.date()
    explicite = False
    if re.search(r"\bapres[- ]demain\b", t):
        jour, explicite = jour + timedelta(days=2), True
    elif re.search(r"\bdemain\b", t):
        jour, explicite = jour + timedelta(days=1), True
    else:
        for nom, n in _JOURS.items():
            if re.search(rf"\b{nom}\b", t):
                ecart = (n - now.weekday()) % 7 or 7
                jour, explicite = jour + timedelta(days=ecart), True
                break
        dm = re.search(r"\b(?:le\s+)?(\d{1,2})(?:er)?\s+(" + "|".join(_MOIS) + r")(?:\s+(\d{4}))?\b", t)
        dn = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
        if dm or dn:
            j, mo, an = (int(dm.group(1)), _MOIS[dm.group(2)], dm.group(3)) if dm else (int(dn.group(1)), int(dn.group(2)), dn.group(3))
            an = int(an) + (2000 if an and len(an) == 2 else 0) if an else now.year
            try:
                jour = datetime(an, mo, j).date()
            except ValueError as exc:
                raise RappelError(f"Date impossible : « {texte} ».") from exc
            if jour < now.date() and not (dm and dm.group(3)) and not (dn and dn.group(3)):
                jour = jour.replace(year=now.year + 1)
            explicite = True
    # heure visée
    h = mi = None
    hm = re.search(r"\b(\d{1,2})\s*(?:h|:|heures?)\s*(\d{2})?\b", t)
    if hm and int(hm.group(1)) < 24:
        h, mi = int(hm.group(1)), int(hm.group(2) or 0)
        if re.search(r"\b(du soir|de l'apres[- ]midi|pm)\b", t) and h < 12:
            h += 12
    else:
        for mot, (hh, mm) in _MOMENTS.items():
            if re.search(rf"\b{mot}\b", t):
                h, mi = hh, mm
                break
    if h is None:
        if not explicite:
            raise RappelError(f"Je n'ai pas compris quand : « {texte} » (ex. « à 17 h », « demain à 8 h », « dans 20 minutes »).")
        h, mi = 9, 0                                       # « lundi » sans heure : 9 h
    d = datetime(jour.year, jour.month, jour.day, h, mi, tzinfo=tz)
    if d <= now and not explicite:
        d += timedelta(days=1)                             # « à 7 h » alors qu'il est 8 h : demain
    if d <= now:
        raise RappelError("Cette heure est déjà passée.")
    return d.astimezone(timezone.utc)


def _ligne(r) -> dict:
    tz = ZoneInfo(settings.timezone)
    q = r["quand"].astimezone(tz)
    return {"id": r["id"], "texte": r["texte"], "quand": q.isoformat(), "quand_lisible": lisible(q), "recurrence": r["recurrence"],
            "piece": r["piece"], "fait": r["fait"]}


def lisible(d: datetime) -> str:
    tz = ZoneInfo(settings.timezone)
    d = d.astimezone(tz)
    auj = datetime.now(tz).date()
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    heure = f"{d.hour} h {d.minute:02d}" if d.minute else f"{d.hour} h"
    if d.date() == auj:
        return f"aujourd'hui à {heure}"
    if d.date() == auj + timedelta(days=1):
        return f"demain à {heure}"
    if (d.date() - auj).days < 7:
        return f"{jours[d.weekday()]} à {heure}"
    return f"le {d.day:02d}/{d.month:02d} à {heure}"


async def creer(qui: str, texte: str, quand: str, recurrence: str = "", session: str = "", piece: str = "") -> dict:
    texte = " ".join(str(texte or "").split())[:300]
    if not texte:
        raise RappelError("Rappeler quoi ?")
    if recurrence not in RECURRENCES:
        raise RappelError("Récurrence : vide, « jour », « semaine » ou « heure ».")
    moment = comprendre(quand)
    async with get_pool().acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM rappels WHERE qui=$1 AND NOT fait", qui)
        if n >= MAX_PAR_PERSONNE:
            raise RappelError("Trop de rappels en attente : supprime-en quelques-uns.")
        r = await conn.fetchrow("INSERT INTO rappels (qui, texte, quand, recurrence, session, piece) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
                                qui, texte, moment, recurrence, session[:80], str(piece or "")[:40])
    return _ligne(r)


async def lister(qui: str) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM rappels WHERE qui=$1 AND NOT fait ORDER BY quand LIMIT 100", qui)
    return [_ligne(r) for r in rows]


async def annuler(qui: str, rid: int | None = None, texte: str = "") -> list[dict]:
    """Annule un rappel par numéro, ou ceux dont le texte contient `texte` ; renvoie ceux annulés."""
    async with get_pool().acquire() as conn:
        if rid:
            rows = await conn.fetch("UPDATE rappels SET fait=TRUE WHERE id=$1 AND qui=$2 AND NOT fait RETURNING *", int(rid), qui)
        elif texte.strip():
            rows = await conn.fetch("UPDATE rappels SET fait=TRUE WHERE qui=$1 AND NOT fait AND texte ILIKE $2 RETURNING *", qui, f"%{texte.strip()}%")
        else:
            raise RappelError("Lequel ? (numéro ou mots du rappel)")
    return [_ligne(r) for r in rows]


# ---------------------------------------------------------------- sonnerie

async def _sessions_de(qui: str) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id FROM sessions WHERE owner=$1 OR ($1='' AND owner='')", qui)
    return [r["id"] for r in rows]


async def sonner(r) -> None:
    from . import satellites
    from .connections import connection_manager
    message = f"⏰ Rappel : {r['texte']}"
    msg = {"type": "proactive", "text": message, "monitor": "rappel"}
    for sid in await _sessions_de(r["qui"]):
        await connection_manager._deliver(sid, msg)
    await connection_manager._hooks(msg)                   # Telegram, s'il est réglé
    cibles = []
    if r["session"].startswith("satellite-"):
        cibles.append(r["session"][len("satellite-"):])
    if r["piece"]:
        cibles += [sid for sid, _s in await satellites.trouver(r["piece"])]
    for sid in dict.fromkeys(cibles):
        try:
            await satellites.ordonner(sid, {"type": "dire", "texte": f"Rappel : {r['texte']}"}, delai=10)
        except Exception:  # noqa: BLE001
            pass


async def verifier() -> int:
    """Fait sonner les rappels arrivés à échéance ; renvoie combien."""
    async with get_pool().acquire() as conn:
        dus = await conn.fetch("SELECT * FROM rappels WHERE NOT fait AND quand <= now() ORDER BY quand LIMIT 50")
        for r in dus:
            pas = RECURRENCES.get(r["recurrence"])
            if pas:
                prochain = r["quand"] + pas
                while prochain <= datetime.now(timezone.utc):
                    prochain += pas
                await conn.execute("UPDATE rappels SET quand=$2 WHERE id=$1", r["id"], prochain)
            else:
                await conn.execute("UPDATE rappels SET fait=TRUE WHERE id=$1", r["id"])
    for r in dus:
        try:
            await sonner(r)
        except Exception:  # noqa: BLE001
            logger.warning("Rappel %s non délivré", r["id"], exc_info=True)
    return len(dus)


async def boucle() -> None:
    while True:
        try:
            await verifier()
        except Exception:  # noqa: BLE001 — base indisponible un instant : on réessaie
            logger.debug("Vérification des rappels en échec", exc_info=True)
        await asyncio.sleep(5)


async def effacer_de(qui: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM rappels WHERE qui=$1", qui)
