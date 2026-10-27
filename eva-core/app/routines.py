"""Routines de la maison : « tous les soirs à 22 h, lance la scène Bonne nuit », « en semaine à 7 h, allume la cuisine »,
« si la température du salon dépasse 26 °C, allume le ventilateur », « quand la porte du garage s'ouvre, préviens-moi ».

Déclencheur : une heure (jours choisis) ou un capteur de Home Assistant (température, mouvement, porte, sun.sun…) qui
passe une condition. Actions : scène, appareil, annonce dans une pièce, message (conversation + Telegram).
Un capteur ne redéclenche qu'après être repassé « faux » (et au plus une fois toutes les 10 minutes).
Une action sensible (volet, ordinateur, scène qui en contient) n'est jamais lancée seule : EVA prévient à la place.
Stockage : kv « routines »."""
import asyncio
import json
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .db import get_pool

KV = "routines"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
CONDITIONS = (">", "<", ">=", "<=", "=", "!=")
REARMEMENT_S = 600
_capteurs: dict[str, bool] = {}            # dernier état (condition vraie ?) par routine
_derniers_tir: dict[str, float] = {}


class RoutineError(ValueError):
    pass


async def _charger() -> list[dict]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return list((d or {}).get("routines") or [])


async def _ecrire(lst: list[dict]) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps({"routines": lst}))


def jours_de(texte) -> list[int]:
    """« tous les jours », « en semaine », « le week-end », « lundi, mercredi », [0, 2]… → numéros (0 = lundi)."""
    if isinstance(texte, list) and all(isinstance(x, int) for x in texte):
        return sorted({x for x in texte if 0 <= x <= 6}) or list(range(7))
    t = str(texte or "").lower()
    if not t.strip() or re.search(r"tous|chaque jour|quotidien|tout le temps", t):
        return list(range(7))
    if re.search(r"semaine|ouvr", t) and "week" not in t:
        return [0, 1, 2, 3, 4]
    if re.search(r"week|samedi et dimanche", t):
        return [5, 6]
    js = [i for i, j in enumerate(JOURS) if j in t or j[:3] + " " in t + " "]
    if not js:
        raise RoutineError(f"Jours non compris : « {texte} » (ex. tous les jours, en semaine, le week-end, lundi et jeudi).")
    return js


def heure_de(texte: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:h|:|heures?)\s*(\d{2})?\s*", str(texte or "").lower())
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        raise RoutineError(f"Heure non comprise : « {texte} » (ex. 22:00, 7h30).")
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def _valider(r: dict) -> dict:
    nom = " ".join(str(r.get("nom") or "").split())[:80]
    if not nom:
        raise RoutineError("Donne un nom à la routine.")
    d = r.get("declencheur") or {}
    if d.get("type") == "heure":
        d = {"type": "heure", "heure": heure_de(d.get("heure", "")), "jours": jours_de(d.get("jours", ""))}
    elif d.get("type") == "capteur":
        ent = str(d.get("entite") or "").strip()
        if not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", ent):
            raise RoutineError("Capteur : donne l'entité Home Assistant (ex. sensor.salon_temperature, binary_sensor.porte_garage).")
        cond = str(d.get("condition") or "=").strip()
        if cond not in CONDITIONS:
            raise RoutineError(f"Condition : {', '.join(CONDITIONS)}.")
        d = {"type": "capteur", "entite": ent, "condition": cond, "valeur": str(d.get("valeur", "on")).strip()[:40]}
    else:
        raise RoutineError("Déclencheur : une heure (type=heure) ou un capteur (type=capteur).")
    actions = []
    for a in r.get("actions") or []:
        t = a.get("type")
        if t == "scene" and str(a.get("scene") or "").strip():
            actions.append({"type": "scene", "scene": str(a["scene"]).strip()[:80]})
        elif t == "appareil" and str(a.get("appareil") or "").strip():
            act = str(a.get("action") or "on").strip().lower()
            if act not in ("on", "off", "toggle", "brightness", "color", "temperature"):
                raise RoutineError("Action d'appareil : on, off, toggle, brightness, color, temperature.")
            actions.append({"type": "appareil", "appareil": str(a["appareil"]).strip()[:80], "action": act,
                            **({"valeur": str(a.get("valeur"))[:30]} if a.get("valeur") not in (None, "") else {})})
        elif t == "annonce" and str(a.get("texte") or "").strip():
            actions.append({"type": "annonce", "texte": str(a["texte"]).strip()[:300], "piece": str(a.get("piece") or "").strip()[:40]})
        elif t == "notifier" and str(a.get("texte") or "").strip():
            actions.append({"type": "notifier", "texte": str(a["texte"]).strip()[:300]})
    if not actions:
        raise RoutineError("Ajoute au moins une action : scène, appareil, annonce ou message.")
    return {"nom": nom, "declencheur": d, "actions": actions[:6], "actif": bool(r.get("actif", True))}


async def lister() -> list[dict]:
    return await _charger()


async def creer(r: dict, qui: str = "") -> dict:
    propre = _valider(r)
    lst = await _charger()
    if len(lst) >= 100:
        raise RoutineError("100 routines au plus.")
    nouvelle = {"id": secrets.token_hex(4), **propre, "qui": qui, "cree": int(time.time()), "dernier": None}
    lst.append(nouvelle)
    await _ecrire(lst)
    return nouvelle


async def modifier(rid: str, changements: dict) -> dict:
    lst = await _charger()
    for i, r in enumerate(lst):
        if r["id"] == rid:
            fusion = {**r, **{k: v for k, v in changements.items() if k in ("nom", "declencheur", "actions", "actif")}}
            lst[i] = {**r, **_valider(fusion)}
            await _ecrire(lst)
            return lst[i]
    raise RoutineError("Routine introuvable.")


async def supprimer(rid: str) -> bool:
    lst = await _charger()
    reste = [r for r in lst if r["id"] != rid]
    await _ecrire(reste)
    _capteurs.pop(rid, None)
    return len(reste) < len(lst)


def decrire(r: dict) -> str:
    d = r["declencheur"]
    if d["type"] == "heure":
        j = d["jours"]
        quand = ("tous les jours" if len(j) == 7 else "en semaine" if j == [0, 1, 2, 3, 4] else "le week-end" if j == [5, 6]
                 else ", ".join(JOURS[x] for x in j))
        quand = f"{quand} à {d['heure'].replace(':', ' h ')}".replace(" h 00", " h")
    else:
        quand = f"quand {d['entite']} {d['condition']} {d['valeur']}"
    acts = []
    for a in r["actions"]:
        acts.append({"scene": lambda: f"scène « {a['scene']} »", "appareil": lambda: f"{a['action']} {a['appareil']}",
                     "annonce": lambda: f"annonce « {a['texte'][:40]} »", "notifier": lambda: f"message « {a['texte'][:40]} »"}[a["type"]]())
    return f"{quand} → {', '.join(acts)}"


def _vrai(etat: str, cond: str, valeur: str) -> bool:
    try:
        x, y = float(str(etat).replace(",", ".")), float(str(valeur).replace(",", "."))
        return {">": x > y, "<": x < y, ">=": x >= y, "<=": x <= y, "=": x == y, "!=": x != y}[cond]
    except ValueError:
        e, v = str(etat).strip().lower(), str(valeur).strip().lower()
        alias = {"ouvert": "on", "ouverte": "on", "ferme": "off", "fermé": "off", "fermée": "off", "detecte": "on", "détecté": "on",
                 "allume": "on", "allumé": "on", "eteint": "off", "éteint": "off", "nuit": "below_horizon", "jour": "above_horizon"}
        v = alias.get(v, v)
        return (e == v) if cond == "=" else (e != v) if cond == "!=" else False


async def _notifier(texte: str) -> None:
    try:
        from .connections import connection_manager
        await connection_manager._hooks({"type": "proactive", "text": texte})
    except Exception:  # noqa: BLE001
        pass


async def executer(r: dict, raison: str = "") -> list[str]:
    from . import devices
    compte, soucis = [], []

    def note(texte: str, ok: bool = True) -> None:
        compte.append(texte)
        if not ok:
            soucis.append(texte)
    await devices.reload()
    for a in r["actions"]:
        try:
            if a["type"] == "scene":
                s = await devices.find_scene(a["scene"])
                if not s:
                    note(f"scène « {a['scene']} » introuvable", False)
                elif devices.scene_needs_confirm(s["name"]):
                    note(f"scène « {s['name']} » sensible : pas lancée toute seule", False)
                else:
                    await devices.run_scene(s)
                    note(f"scène « {s['name']} » lancée")
            elif a["type"] == "appareil":
                if devices.needs_confirm({"device": a["appareil"]}):
                    note(f"« {a['appareil']} » est sensible : pas piloté tout seul", False)
                else:
                    await devices.control(a["appareil"], a["action"], a.get("valeur"))
                    note(f"{a['appareil']} : {a['action']}")
            elif a["type"] == "annonce":
                from .harness.tools.satellite_tools import AnnonceTool
                res = await AnnonceTool().execute(texte=a["texte"], piece=a.get("piece", ""))
                note("annonce faite") if res.get("ok") else note(f"annonce : {res.get('error')}", False)
            elif a["type"] == "notifier":
                await _notifier(f"🔔 {a['texte']}")
                note("message envoyé")
        except Exception as exc:  # noqa: BLE001 — une action ratée n'empêche pas les autres
            note(f"{a['type']} : {exc}"[:160], False)
    from . import journal
    await journal.noter("routine", f"Routine « {r.get('nom', r['id'])} »{f' ({raison})' if raison else ''} : " + ("; ".join(compte[:6]) or "rien à faire"))
    lst = await _charger()
    for x in lst:
        if x["id"] == r["id"]:
            x["dernier"] = {"ts": int(time.time()), "compte": compte[:6], "raison": raison}
    await _ecrire(lst)
    if soucis:
        await _notifier(f"🏠 Routine « {r['nom']} » : " + " ; ".join(soucis))
    return compte


async def verifier(maintenant: datetime | None = None) -> int:
    """Un passage : routines horaires de cette minute, puis capteurs. Renvoie le nombre de routines lancées."""
    from .config import settings
    now = maintenant or datetime.now(ZoneInfo(settings.timezone))
    cle_minute = now.strftime("%Y-%m-%d %H:%M")
    n = 0
    for r in [x for x in await _charger() if x.get("actif")]:
        d = r["declencheur"]
        if d["type"] == "heure":
            if d["heure"] == now.strftime("%H:%M") and now.weekday() in d["jours"] and _derniers_tir.get(r["id"]) != cle_minute:
                _derniers_tir[r["id"]] = cle_minute
                await executer(r, "heure")
                n += 1
        else:
            try:
                from . import homeassistant
                etat = (await homeassistant.get_state(d["entite"])).get("state")
            except Exception:  # noqa: BLE001 — Home Assistant absent ou capteur inconnu
                continue
            vrai = _vrai(etat, d["condition"], d["valeur"])
            avant = _capteurs.get(r["id"])
            _capteurs[r["id"]] = vrai
            if avant is False and vrai and time.time() - _derniers_tir.get(r["id"] + ":c", 0) > REARMEMENT_S:
                _derniers_tir[r["id"] + ":c"] = time.time()
                await executer(r, f"{d['entite']} = {etat}")
                n += 1
    return n


async def boucle() -> None:
    while True:
        try:
            await verifier()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(30 - (time.time() % 30) + 0.5)
