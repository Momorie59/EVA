"""Infos pratiques du foyer : poubelles, vacances scolaires et jours fériés, prix des carburants, éphéméride,
titres de l'actualité. Réglages dans Paramètres › Services connectés › Infos pratiques.

Portage en Python, pour EVA, de modules de cornelius-modules (lecture des calendriers de ramassage « en toutes
lettres », sources de données publiques) :
    Copyright (c) 2026 Les Frères Poulain and the cornelius-modules contributors
    (https://github.com/lfpoulain/cornelius-modules) — licence MIT, texte complet dans THIRD_PARTY_NOTICES.md."""
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import settings
from .db import get_pool

KV = "pratique"
UA = {"User-Agent": "EVA-assistant/1.0 (https://github.com/Momorie59/EVA)"}
DEFAUT = {
    "zone": "B", "region": "metropole",
    "carburant": {"lieu": "", "type": "gazole"},
    "poubelles": {"bacs": [], "veille": True, "heure_veille": 19},
    "actu": {"url": "https://www.franceinfo.fr/titres.rss", "nombre": 5},
}


class PratiqueError(ValueError):
    pass


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def aujourdhui() -> date:
    return datetime.now(_tz()).date()


async def reglages() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    out = json.loads(json.dumps(DEFAUT))
    for k, v in (d or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update({kk: vv for kk, vv in v.items() if kk in out[k]})
        elif k in out:
            out[k] = v
    return out


async def regler(chg: dict) -> dict:
    d = await reglages()
    for k, v in (chg or {}).items():
        if k not in DEFAUT:
            continue
        if isinstance(DEFAUT[k], dict) and isinstance(v, dict):
            d[k].update({kk: vv for kk, vv in v.items() if kk in DEFAUT[k]})
        else:
            d[k] = v
    if d["zone"] not in ("A", "B", "C", "Corse"):
        raise PratiqueError("Zone de vacances : A, B, C ou Corse.")
    if d["region"] not in ("metropole", "alsace-moselle"):
        raise PratiqueError("Jours fériés : metropole ou alsace-moselle.")
    if d["carburant"]["type"] not in CARBURANTS:
        raise PratiqueError("Carburant : " + ", ".join(CARBURANTS) + ".")
    bacs = []
    for b in d["poubelles"]["bacs"][:8]:
        if b.get("bac") not in BACS:
            raise PratiqueError(f"Bac inconnu : {b.get('bac')}.")
        lire_regle(b.get("jours", ""))                   # refuse une règle incomprise (message explicite)
        bacs.append({"bac": b["bac"], "jours": str(b["jours"]).strip()[:80]})
    d["poubelles"]["bacs"] = bacs
    d["poubelles"]["heure_veille"] = max(15, min(23, int(d["poubelles"].get("heure_veille") or 19)))
    url = str(d["actu"].get("url") or "").strip()
    if url and not url.startswith(("https://", "http://")):
        raise PratiqueError("Adresse du flux d'actualité : commence par https://")
    d["actu"]["nombre"] = max(1, min(10, int(d["actu"].get("nombre") or 5)))
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    return d


async def _get(url: str, params: dict | None = None, accept: str = "application/json", limite: int = 512 * 1024) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={**UA, "Accept": accept}) as c:
        r = await c.get(url, params=params)
    if r.status_code == 429:
        raise PratiqueError("Le service limite les demandes : réessaie dans un moment.")
    if r.status_code >= 500:
        raise PratiqueError("Le service ne répond pas pour l'instant.")
    if r.status_code != 200:
        raise PratiqueError(f"Réponse inattendue du service ({r.status_code}).")
    if len(r.content) > limite:
        raise PratiqueError("Réponse trop grande.")
    return r


_cache: dict[str, tuple[float, object]] = {}


async def _memo(cle: str, duree: float, fabriquer):
    hit = _cache.get(cle)
    if hit and time.monotonic() - hit[0] < duree:
        return hit[1]
    v = await fabriquer()
    _cache[cle] = (time.monotonic(), v)
    return v


# ---------------------------------------------------------------- jours en français
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def jour_long(d: date) -> str:
    return f"{JOURS[d.weekday()]} {'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]}"


def quand(d: date, ref: date) -> str:
    n = (d - ref).days
    return "aujourd'hui" if n == 0 else "demain" if n == 1 else f"{jour_long(d)} (dans {n} jours)"


# ---------------------------------------------------------------- poubelles
BACS = {"menager": "les ordures ménagères", "emballages": "les emballages", "verre": "le verre",
        "biodechets": "les biodéchets", "vegetaux": "les déchets verts", "encombrants": "les encombrants"}
_JOURS_MOTS = {j: i for i, j in enumerate(JOURS)}
_ORDINAUX = {"1er": 1, "1re": 1, "premier": 1, "premiere": 1, "2e": 2, "2eme": 2, "deuxieme": 2, "second": 2, "seconde": 2,
             "3e": 3, "3eme": 3, "troisieme": 3, "4e": 4, "4eme": 4, "quatrieme": 4, "5e": 5, "5eme": 5, "cinquieme": 5,
             "dernier": -1, "derniere": -1}
_LIAISONS = {"le", "les", "la", "et", "du", "de", "des", "au", "moi", "mois", "semaine", "chaque", "tou", "tous", "toute", "toutes",
             "tout", "matin"}


def _mots(texte: str) -> list[str]:
    t = unicodedata.normalize("NFD", (texte or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[,;/+]", " ", t)
    return [m[:-1] if m.endswith("s") and len(m) > 2 else m for m in t.split()]


def lire_regle(texte: str) -> dict:
    """« lundi et jeudi », « mardi semaines paires », « 1er et 3e mercredi du mois », « dernier vendredi du mois »."""
    jours, ordinaux, parite = set(), set(), "toutes"
    for m in _mots(texte):
        if m in _JOURS_MOTS:
            jours.add(_JOURS_MOTS[m])
        elif m in _ORDINAUX:
            ordinaux.add(_ORDINAUX[m])
        elif m in ("pair", "paire"):
            parite = "paires"
        elif m in ("impair", "impaire"):
            parite = "impaires"
        elif m not in _LIAISONS:
            raise PratiqueError(f"Jours de ramassage « {texte} » : « {m} » n'est pas compris "
                                "(exemples : « lundi et jeudi », « mercredi semaines paires », « 1er vendredi du mois »).")
    if not jours:
        raise PratiqueError(f"Jours de ramassage « {texte} » : aucun jour de la semaine.")
    if ordinaux and parite != "toutes":
        raise PratiqueError("Choisis entre « semaines paires » et « du mois ».")
    return {"jours": sorted(jours), "ordinaux": sorted(ordinaux), "parite": parite}


def _correspond(r: dict, d: date) -> bool:
    if d.weekday() not in r["jours"]:
        return False
    if r["parite"] != "toutes" and (d.isocalendar()[1] % 2 == 0) != (r["parite"] == "paires"):
        return False
    if not r["ordinaux"]:
        return True
    rang = (d.day - 1) // 7 + 1
    dernier = (d + timedelta(days=7)).month != d.month
    return rang in r["ordinaux"] or (dernier and -1 in r["ordinaux"])


def prochains_ramassages(bacs: list[dict], maintenant: datetime) -> list[dict]:
    """Prochaine date de chaque bac (le ramassage du jour compte jusqu'à midi), triées."""
    debut = maintenant.date() if maintenant.hour < 12 else maintenant.date() + timedelta(days=1)
    out = {}
    for b in bacs:
        r = lire_regle(b["jours"])
        for i in range(70):
            d = debut + timedelta(days=i)
            if _correspond(r, d):
                if b["bac"] not in out or d < out[b["bac"]]:
                    out[b["bac"]] = d
                break
    return sorted(({"bac": k, "date": v} for k, v in out.items()), key=lambda x: (x["date"], list(BACS).index(x["bac"])))


def _liste(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " et " + items[-1]


async def poubelles(maintenant: datetime | None = None) -> dict:
    p = (await reglages())["poubelles"]
    if not p["bacs"]:
        return {"error": "Les jours de ramassage ne sont pas encore réglés : Paramètres › Services connectés › Infos pratiques."}
    maintenant = maintenant or datetime.now(_tz())
    prochains = prochains_ramassages(p["bacs"], maintenant)
    if not prochains:
        return {"error": "Aucun ramassage trouvé dans les 10 prochaines semaines."}
    premier = prochains[0]["date"]
    lot = [BACS[x["bac"]] for x in prochains if x["date"] == premier]
    ref = maintenant.date()
    ce_soir = p["veille"] and (premier - ref).days == 1 and maintenant.hour >= 17
    phrase = (f"Ce soir, sors {_liste(lot)} (ramassage demain)." if ce_soir
              else f"Prochain ramassage {quand(premier, ref)} : {_liste(lot)}.")
    return {"phrase": phrase, "ce_soir": ce_soir,
            "prochains": [{"bac": BACS[x["bac"]], "quand": quand(x["date"], ref), "date": x["date"].isoformat()} for x in prochains]}


# ---------------------------------------------------------------- vacances scolaires et jours fériés
URL_CALENDRIER = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/records"
URL_FERIES = "https://calendrier.api.gouv.fr/jours-feries"


def _nom_vacances(desc: str) -> str:
    return re.sub(r"(d'|d’|de )(Hiver|Printemps|Été|Février|Mai|Novembre|Septembre|Carnaval)",
                  lambda m: m.group(1) + m.group(2).lower(), desc.strip())[:80]


def vacances_depuis(resultats: list[dict], jour: date) -> list[dict]:
    tz, vus, out = _tz(), set(), []
    for r in resultats:
        if not str(r.get("description", "")).strip().startswith("Vacances"):
            continue
        if r.get("population") not in (None, "-", "Élèves"):
            continue
        debut = datetime.fromisoformat(r["start_date"]).astimezone(tz).date()
        fin = datetime.fromisoformat(r["end_date"]).astimezone(tz).date()       # jour de la reprise
        if fin <= debut or fin <= jour or (debut, fin) in vus:
            continue
        vus.add((debut, fin))
        out.append({"nom": _nom_vacances(r["description"]), "debut": debut, "reprise": fin})
    return sorted(out, key=lambda v: v["debut"])[:6]


def feries_depuis(donnees: dict, jour: date) -> list[dict]:
    return [{"date": date.fromisoformat(d), "nom": str(n).strip()[:80]} for d, n in sorted(donnees.items()) if d >= jour.isoformat()][:6]


async def vacances(zone: str | None = None) -> dict:
    reg = await reglages()
    zone = (zone or reg["zone"]).replace("Zone ", "").replace("zone ", "").strip().upper().replace("CORSE", "Corse")
    if zone not in ("A", "B", "C", "Corse"):
        raise PratiqueError("Zone : A, B, C ou Corse.")
    jour = aujourdhui()

    async def cal():
        r = await _get(URL_CALENDRIER, {"select": "description,population,start_date,end_date",
                                        "where": f'zones="{"Corse" if zone == "Corse" else "Zone " + zone}" and end_date>="{jour.isoformat()}"',
                                        "group_by": "description,population,start_date,end_date", "order_by": "start_date", "limit": "20"})
        return r.json().get("results", [])

    async def fer():
        return (await _get(f"{URL_FERIES}/{reg['region']}.json")).json()
    resultats = await _memo(f"cal:{zone}:{jour}", 6 * 3600, cal)
    feries_bruts = await _memo(f"fer:{reg['region']}", 24 * 3600, fer)
    vac = vacances_depuis(resultats, jour)
    fer_ = feries_depuis(feries_bruts, jour)
    en_cours = next((v for v in vac if v["debut"] <= jour < v["reprise"]), None)
    prochaines = [v for v in vac if v["debut"] > jour]
    lignes = []
    if en_cours:
        lignes.append(f"En ce moment : {en_cours['nom']} (zone {zone}), reprise {quand(en_cours['reprise'], jour)}.")
    if prochaines:
        v = prochaines[0]
        lignes.append(f"Prochaines vacances : {v['nom']}, du {jour_long(v['debut'])} au {jour_long(v['reprise'] - timedelta(days=1))} "
                      f"(dans {(v['debut'] - jour).days} jours).")
    if fer_:
        lignes.append(f"Prochain jour férié : {fer_[0]['nom']}, {quand(fer_[0]['date'], jour)}.")
    return {"zone": zone, "phrase": " ".join(lignes) or "Aucune information pour l'instant.",
            "vacances": [{"nom": v["nom"], "debut": v["debut"].isoformat(), "reprise": v["reprise"].isoformat()} for v in vac],
            "feries": [{"nom": f["nom"], "date": f["date"].isoformat()} for f in fer_]}


# ---------------------------------------------------------------- carburants
URL_CARBURANTS = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
CARBURANTS = {"gazole": "Gazole", "e10": "SP95-E10", "sp95": "SP95", "sp98": "SP98", "e85": "E85", "gplc": "GPL"}


def stations_depuis(resultats: list[dict], carburant: str) -> list[dict]:
    out = []
    for s in resultats:
        prix = s.get(f"{carburant}_prix")
        if not isinstance(prix, (int, float)) or not 0 < prix < 20:
            continue
        maj = s.get(f"{carburant}_maj")
        out.append({"adresse": " ".join(str(s.get("adresse") or "").split()) or "adresse inconnue",
                    "ville": " ".join(str(s.get("ville") or "").split()).title(), "cp": s.get("cp") or "",
                    "prix": round(float(prix), 3), "maj": str(maj)[:10] if isinstance(maj, str) else ""})
    return sorted(out, key=lambda x: x["prix"])


async def carburants(lieu: str = "", carburant: str = "") -> dict:
    reg = (await reglages())["carburant"]
    lieu = (lieu or reg["lieu"]).strip()
    carburant = (carburant or reg["type"]).lower().replace("diesel", "gazole").replace("gpl", "gplc").replace("gplcc", "gplc")
    carburant = {"sp95-e10": "e10", "sans plomb 95": "sp95", "sans plomb 98": "sp98", "essence": "e10"}.get(carburant, carburant)
    if carburant not in CARBURANTS:
        raise PratiqueError("Carburant : gazole, e10, sp95, sp98, e85 ou gplc.")
    if not lieu:
        raise PratiqueError("Dis-moi la commune ou le code postal (ou règle-le dans Paramètres › Infos pratiques).")
    champs = ["id", "adresse", "ville", "cp", f"{carburant}_prix", f"{carburant}_maj"]
    lieu_sur = lieu.replace('"', "")
    where = f'cp="{lieu_sur}"' if re.fullmatch(r"\d{5}", lieu_sur) else f'search(ville, "{lieu_sur}")'
    r = await _get(URL_CARBURANTS, {"select": ",".join(champs), "where": where + f" and {carburant}_prix is not null",
                                    "order_by": f"{carburant}_prix", "limit": "20"})
    st = stations_depuis(r.json().get("results", []), carburant)
    if not st:
        return {"error": f"Aucune station trouvée à « {lieu} » avec du {CARBURANTS[carburant]}."}
    m = st[0]
    return {"carburant": CARBURANTS[carburant], "lieu": lieu,
            "phrase": f"{CARBURANTS[carburant]} le moins cher à {m['ville'] or lieu} : {str(m['prix']).replace('.', ',')} € le litre, {m['adresse']}.",
            "stations": st[:5]}


# ---------------------------------------------------------------- éphéméride
URL_EPHEMERIDE = "https://fr.wikipedia.org/api/rest_v1/feed/onthisday/selected"


def _rondeur(ans: int) -> int:
    for pas, score in ((1000, 6), (500, 5), (100, 4), (50, 3), (25, 2), (10, 1)):
        if ans % pas == 0:
            return score
    return 0


def evenements_depuis(selected: list[dict], annee: int) -> list[dict]:
    ev = []
    for e in selected:
        try:
            y = int(e.get("year"))
        except (TypeError, ValueError):
            continue
        t = " ".join(str(e.get("text") or "").split())
        if t and annee - y >= 1:
            ev.append({"annee": y, "il_y_a": annee - y, "texte": t[:300]})
    return sorted(ev, key=lambda x: (-_rondeur(x["il_y_a"]), x["il_y_a"]))


async def ephemeride(jour: str = "") -> dict:
    d = aujourdhui()
    if jour:
        try:
            d = date.fromisoformat(jour)
        except ValueError as exc:
            raise PratiqueError("Date attendue au format AAAA-MM-JJ.") from exc

    async def charger():
        return (await _get(f"{URL_EPHEMERIDE}/{d.month:02d}/{d.day:02d}")).json().get("selected", [])
    ev = evenements_depuis(await _memo(f"eph:{d.month}-{d.day}", 24 * 3600, charger), d.year)
    if not ev:
        return {"error": "Rien trouvé pour ce jour."}
    e = ev[0]
    return {"jour": jour_long(d), "phrase": f"Il y a {e['il_y_a']} ans, le {d.day if d.day > 1 else '1er'} {MOIS[d.month - 1]} {e['annee']} : {e['texte']}",
            "evenements": ev[:5], "source": "Wikipédia"}


# ---------------------------------------------------------------- titres de l'actualité (RSS / Atom)
def titres_depuis(xml: bytes, nombre: int) -> tuple[str, list[dict]]:
    try:
        racine = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PratiqueError("Cette adresse ne donne pas un flux RSS ou Atom.") from exc
    atom = "{http://www.w3.org/2005/Atom}"
    titre = (racine.findtext("channel/title") or racine.findtext(f"{atom}title") or "").strip()
    items = racine.findall("channel/item") or racine.findall(f"{atom}entry")
    out = []
    for it in items[:nombre]:
        t = " ".join((it.findtext("title") or it.findtext(f"{atom}title") or "").split())
        lien = (it.findtext("link") or "").strip()
        if not lien:
            el = it.find(f"{atom}link")
            lien = el.get("href", "") if el is not None else ""
        if t:
            out.append({"titre": t[:200], "lien": lien[:300],
                        "date": (it.findtext("pubDate") or it.findtext(f"{atom}updated") or "").strip()[:40]})
    nom = re.split(r"\s+[-–|:]\s+", titre)[0].strip() if titre else ""
    return nom, out


async def actu(url: str = "", nombre: int = 0) -> dict:
    reg = (await reglages())["actu"]
    url = (url or reg["url"]).strip()
    nombre = max(1, min(10, int(nombre or reg["nombre"])))

    async def charger():
        r = await _get(url, accept="application/rss+xml, application/atom+xml, application/xml, text/xml")
        return titres_depuis(r.content, 10)
    nom, items = await _memo(f"actu:{url}", 600, charger)
    if not items:
        return {"error": "Ce flux ne contient aucun titre."}
    nom = nom or httpx.URL(url).host
    return {"journal": nom, "titres": [i["titre"] for i in items[:nombre]],
            "resultats": [{"title": i["titre"], "url": i.get("lien", ""), "snippet": ""} for i in items[:nombre]],
            "phrase": f"Les titres de {nom} : " + " ".join(t if t.endswith((".", "!", "?", "»")) else t + "." for t in [i["titre"] for i in items[:nombre]])}


# ---------------------------------------------------------------- rappel de la veille au soir
_dernier_rappel: dict = {"jour": None}


async def veille_poubelles() -> str:
    """Planificateur : à l'heure réglée, la veille d'un ramassage, EVA prévient (écran, Telegram, satellites)."""
    p = (await reglages())["poubelles"]
    maintenant = datetime.now(_tz())
    if not p["bacs"] or not p["veille"] or maintenant.hour != p["heure_veille"] or _dernier_rappel["jour"] == maintenant.date():
        return "rien"
    r = await poubelles(maintenant)
    if not r.get("ce_soir"):
        return "rien"
    _dernier_rappel["jour"] = maintenant.date()
    from . import journal, satellites
    from .connections import connection_manager
    texte = f"🗑️ {r['phrase']}"
    await connection_manager.broadcast_all({"type": "proactive", "text": texte, "monitor": "rappel"})
    for sid, _s in await satellites.trouver(""):
        try:
            await satellites.ordonner(sid, {"type": "dire", "texte": r["phrase"]}, delai=10)
        except Exception:  # noqa: BLE001
            pass
    await journal.noter("routine", f"Rappel poubelles : {r['phrase']}")
    return "prevenu"


async def resultats_actu(nombre: int = 6) -> list[dict] | None:
    """Gros titres pour le briefing et « quoi de neuf ? » : flux RSS réglé, sinon None (la recherche web prend le relais)."""
    try:
        r = await actu("", nombre)
    except Exception:  # noqa: BLE001
        return None
    return r.get("resultats") or None
