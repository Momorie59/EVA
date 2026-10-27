"""Philips Hue en direct, sans Home Assistant : le pont Hue est piloté par son API locale (réseau de la maison).

Appairage : on appuie sur le gros bouton du pont, puis « Appairer » dans EVA (30 secondes) : le pont donne une clé à EVA.
Les lampes s'ajoutent ensuite comme des appareils de la page Maison (pilote « hue ») : allumer, éteindre, luminosité,
couleur, blanc chaud/froid. Les scènes du pont (créées dans l'appli Hue) se lancent aussi depuis EVA."""
import json
import re

import httpx

from .db import get_pool

KV = "hue"


class HueError(RuntimeError):
    pass


def _ip_ok(ip: str) -> str:
    ip = (ip or "").strip()
    if not re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", ip):
        raise HueError("Adresse IP du pont invalide (ex. 192.168.1.20).")
    return ip


async def _req(method: str, url: str, body=None, timeout: float = 6.0):
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.request(method, url, json=body)
        return r.json()
    except httpx.HTTPError as exc:
        raise HueError(f"Le pont Hue ne répond pas ({type(exc).__name__}) : vérifie son adresse et qu'il est allumé.") from exc
    except ValueError as exc:
        raise HueError("Réponse inattendue : ce n'est peut-être pas un pont Hue.") from exc


def _erreur(rep) -> str | None:
    if isinstance(rep, list) and rep and isinstance(rep[0], dict) and "error" in rep[0]:
        e = rep[0]["error"]
        if e.get("type") == 101:
            return "Appuie d'abord sur le bouton rond du pont Hue, puis clique sur « Appairer » dans les 30 secondes."
        if e.get("type") == 1:
            return "Clé refusée par le pont : refais l'appairage."
        return e.get("description") or "Erreur du pont Hue."
    return None


async def ponts() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return ((json.loads(raw) if isinstance(raw, str) else raw) or {}).get("ponts", {})


async def _sauver(p: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps({"ponts": p}))


async def appairer(ip: str) -> dict:
    ip = _ip_ok(ip)
    rep = await _req("POST", f"http://{ip}/api", {"devicetype": "eva#nas"})
    if (err := _erreur(rep)):
        raise HueError(err)
    try:
        cle = rep[0]["success"]["username"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HueError("Réponse inattendue du pont Hue.") from exc
    conf = await _req("GET", f"http://{ip}/api/{cle}/config")
    p = await ponts()
    p[ip] = {"ip": ip, "cle": cle, "nom": (conf or {}).get("name", "Pont Hue") if isinstance(conf, dict) else "Pont Hue"}
    await _sauver(p)
    return {"ip": ip, "nom": p[ip]["nom"]}


async def oublier(ip: str) -> None:
    p = await ponts()
    p.pop(ip, None)
    await _sauver(p)


async def _cle(ip: str) -> str:
    p = (await ponts()).get(ip)
    if not p:
        raise HueError("Pont Hue pas encore appairé (Maison › Philips Hue).")
    return p["cle"]


async def lampes(ip: str) -> list[dict]:
    cle = await _cle(ip)
    rep = await _req("GET", f"http://{ip}/api/{cle}/lights")
    if (err := _erreur(rep)):
        raise HueError(err)
    out = []
    for lid, l in (rep or {}).items():
        st = l.get("state", {})
        out.append({"id": lid, "nom": l.get("name", f"Lampe {lid}"), "type": l.get("type", ""), "allumee": bool(st.get("on")),
                    "luminosite": round((st.get("bri") or 0) / 254 * 100), "joignable": bool(st.get("reachable", True)),
                    "couleur": "xy" in st, "blanc": "ct" in st})
    return sorted(out, key=lambda x: x["nom"].lower())


async def scenes(ip: str) -> list[dict]:
    cle = await _cle(ip)
    rep = await _req("GET", f"http://{ip}/api/{cle}/scenes")
    groupes = await _req("GET", f"http://{ip}/api/{cle}/groups")
    if (err := _erreur(rep)) or (err := _erreur(groupes)):
        raise HueError(err)
    noms = {gid: g.get("name", "") for gid, g in (groupes or {}).items()}
    return sorted(({"id": sid, "nom": s.get("name", ""), "piece": noms.get(s.get("group", ""), ""), "groupe": s.get("group", "")}
                   for sid, s in (rep or {}).items() if s.get("type") == "GroupScene"), key=lambda x: (x["piece"], x["nom"]))


async def lancer_scene(ip: str, scene_id: str, groupe: str) -> dict:
    cle = await _cle(ip)
    rep = await _req("PUT", f"http://{ip}/api/{cle}/groups/{groupe}/action", {"scene": scene_id})
    if (err := _erreur(rep)):
        raise HueError(err)
    return {"ok": True}


def _xy(rgb: tuple[int, int, int]) -> list[float]:
    """RVB → coordonnées xy (formule Philips, gamut large)."""
    def lin(c):
        c /= 255
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92
    r, g, b = (lin(c) for c in rgb)
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    s = x + y + z
    return [round(x / s, 4), round(y / s, 4)] if s else [0.3227, 0.329]


async def piloter(cfg: dict, action: str, value, rgb_de=None, pct_de=None) -> dict:
    """Pilote « hue » de devices.py : cfg = {ip, light}."""
    ip, lid = cfg["ip"], str(cfg["light"])
    cle = await _cle(ip)
    base = f"http://{ip}/api/{cle}/lights/{lid}"
    if action == "state":
        rep = await _req("GET", base)
        if (err := _erreur(rep)):
            raise HueError(err)
        st = (rep or {}).get("state", {})
        return {"on": bool(st.get("on")), "brightness": round((st.get("bri") or 0) / 254 * 100), "reachable": st.get("reachable", True)}
    if action == "toggle":
        etat = await piloter(cfg, "state", None)
        action = "off" if etat["on"] else "on"
    corps: dict = {}
    if action in ("on", "off"):
        corps = {"on": action == "on"}
    elif action == "brightness":
        p = pct_de(value)
        corps = {"on": p > 0, "bri": max(1, round(p / 100 * 254))} if p else {"on": False}
    elif action == "color":
        corps = {"on": True, "xy": _xy(rgb_de(value))}
    elif action == "temperature":
        p = pct_de(value)                                 # 0 % = blanc chaud (500 mireds), 100 % = blanc froid (153)
        corps = {"on": True, "ct": round(500 - p / 100 * (500 - 153))}
    rep = await _req("PUT", f"{base}/state", corps)
    if (err := _erreur(rep)):
        raise HueError(err)
    return {"ok": True}
