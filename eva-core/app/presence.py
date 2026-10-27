"""Présence à la maison : qui est là, d'après son téléphone connecté au wifi (comme Jarvis).

L'administrateur associe à chaque personne l'adresse MAC de son téléphone (Maison › Présence : liste des appareils vus).
Toutes les 2 minutes, le service eva-scanner (réseau de la maison) liste les appareils qui répondent ; un téléphone vu dans
les 15 dernières minutes = la personne est à la maison (un téléphone en veille répond moins souvent).
Astuce : sur le téléphone, garder la même adresse MAC pour le wifi de la maison (« adresse MAC de l'appareil » ou « non aléatoire »).
Rien ne sort du réseau ; seules les personnes inscrites par l'administrateur apparaissent."""
import json
import re
import time

import httpx

from .config import settings
from .db import get_pool

KV = "presence"
ABSENT_APRES_S = 15 * 60
_vus: dict[str, dict] = {}            # mac → {"ip", "ts"}
_etat: dict = {"dernier_scan": 0.0, "erreur": ""}
_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def mac_propre(m: str) -> str:
    m = (m or "").strip().upper().replace("-", ":")
    if not _MAC.match(m):
        raise ValueError(f"Adresse MAC invalide : {m or '(vide)'} (ex. AA:BB:CC:DD:EE:FF).")
    return m


async def reglages() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    auto = d.get("automatismes") or {}
    return {"personnes": d.get("personnes", {}), "automatismes": {"depart": auto.get("depart") or None, "arrivee": auto.get("arrivee") or None}}


async def enregistrer(personnes: dict, automatismes: dict | None = None) -> dict:
    propres = {}
    for nom, conf in (personnes or {}).items():
        nom = " ".join(str(nom).split())[:40]
        macs = [mac_propre(m) for m in (conf or {}).get("macs", []) if str(m).strip()][:4]
        if nom and macs:
            propres[nom] = {"macs": macs}
    auto = (await reglages())["automatismes"] if automatismes is None else {
        "depart": (automatismes or {}).get("depart") or None, "arrivee": (automatismes or {}).get("arrivee") or None}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps({"personnes": propres, "automatismes": auto}))
    return await reglages()


async def scanner() -> list[dict]:
    """Interroge eva-scanner. Met à jour les appareils vus."""
    if not settings.scanner_url:
        _etat["erreur"] = "Service eva-scanner non configuré (EVA_SCANNER_URL) : la présence en a besoin pour voir les téléphones."
        return []
    from .lan_discovery import _scanner_headers
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(settings.scanner_url.rstrip("/") + "/presence", headers=_scanner_headers())
        r.raise_for_status()
        appareils = r.json().get("appareils", [])
    except Exception as exc:  # noqa: BLE001
        _etat["erreur"] = f"eva-scanner injoignable ({type(exc).__name__}) : reconstruis-le (docker compose up -d --build eva-scanner)."
        return []
    now = time.time()
    for a in appareils:
        _vus[a["mac"].upper()] = {"ip": a.get("ip", ""), "ts": now}
    _etat.update(dernier_scan=now, erreur="")
    return appareils


async def periodique() -> None:
    if (await reglages())["personnes"]:
        await scanner()
        await automatismes()


async def automatismes() -> str | None:
    """Comme Jarvis : quand la dernière personne part, ou quand la première rentre, EVA lance la scène choisie."""
    r = await reglages()
    if _etat["erreur"] or not r["personnes"]:
        return None
    presents = {p["nom"] for p in (await etat())["personnes"] if p["present"]}
    avant = _etat.get("presents")
    _etat["presents"] = presents
    if avant is None:                                   # premier balayage depuis le démarrage : on observe seulement
        return None
    if avant and not presents:
        quand, sid, phrase = "depart", r["automatismes"]["depart"], "Tout le monde est parti"
    elif not avant and presents:
        quand, sid, phrase = "arrivee", r["automatismes"]["arrivee"], f"{', '.join(sorted(presents))} vient de rentrer"
    else:
        return None
    if not sid:
        return None
    from . import devices
    scene = next((x for x in await devices.list_scenes() if str(x["id"]) == str(sid)), None)
    if scene is None:
        return None
    if any(devices.needs_confirm({"device": a["device"]}) for a in scene["actions"]):
        texte = f"🏠 {phrase} : la scène « {scene['name']} » touche un appareil sensible, je ne la lance pas toute seule."
    else:
        try:
            await devices.run_scene(scene)
            texte = f"🏠 {phrase} : scène « {scene['name']} » lancée."
        except Exception as exc:  # noqa: BLE001
            texte = f"🏠 {phrase}, mais la scène « {scene['name']} » a échoué : {exc}"[:300]
    _etat["dernier_automatisme"] = {"quand": quand, "texte": texte, "ts": time.time()}
    try:
        from .connections import connection_manager
        await connection_manager._hooks({"type": "proactive", "text": texte})
    except Exception:  # noqa: BLE001
        pass
    return texte


async def etat() -> dict:
    now = time.time()
    out = []
    for nom, conf in (await reglages())["personnes"].items():
        ts = max((_vus.get(m, {}).get("ts", 0) for m in conf["macs"]), default=0)
        out.append({"nom": nom, "present": bool(ts) and now - ts < ABSENT_APRES_S,
                    "vu_il_y_a_min": round((now - ts) / 60) if ts else None})
    return {"personnes": out, "dernier_scan": _etat["dernier_scan"] or None, "erreur": _etat["erreur"]}


def appareils_vus() -> list[dict]:
    now = time.time()
    return sorted(({"mac": m, "ip": v["ip"], "vu_il_y_a_min": round((now - v["ts"]) / 60)} for m, v in _vus.items()),
                  key=lambda x: tuple(int(p) for p in x["ip"].split(".")) if re.fullmatch(r"(\d+\.){3}\d+", x["ip"]) else (999,))


def phrase(e: dict) -> str:
    if not e["personnes"]:
        return "Personne n'est encore inscrit pour la présence (Maison › Présence)."
    la = [p["nom"] for p in e["personnes"] if p["present"]]
    pas = [p["nom"] for p in e["personnes"] if not p["present"]]
    if not la:
        return "Personne n'est à la maison en ce moment (aucun téléphone inscrit n'est sur le wifi)."
    t = ("À la maison : " + ", ".join(la) + ".")
    return t + (f" Absent : {', '.join(pas)}." if pas else "")
