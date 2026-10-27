"""Appareils de la maison, par pièce — « allume la lumière du salon », « éteins tout dans la chambre », scènes.

Pilotes : Tuya (en local avec l'adresse IP et la clé locale, sinon via le cloud Tuya), Shelly / Tasmota / WLED (HTTP local),
Wake-on-LAN, MQTT, Home Assistant (appareils déjà gérés par lui). Chaque appareil a un nom, une pièce, un type et un pilote.

Sécurité : serrures, alarmes et portails ne peuvent pas être enregistrés (à faire à la main). Volets, ordinateurs et tout appareil
marqué « demander confirmation » exigent l'accord de l'utilisateur ; au-delà de 6 appareils d'un coup, aussi."""
import asyncio
import json
import re
import socket
from typing import Any

import httpx

from . import homeassistant as ha
from . import lan_drivers
from .db import get_pool
from .lists import norm

TYPES = {"light": "lumière", "switch": "prise / interrupteur", "fan": "ventilateur", "climate": "chauffage / clim", "cover": "volet / store",
         "media": "TV / enceinte", "computer": "ordinateur", "other": "autre"}
TYPE_WORDS = {"light": "lumiere lampe eclairage ampoule", "switch": "prise interrupteur", "fan": "ventilateur ventilo", "climate": "chauffage clim climatisation thermostat",
              "cover": "volet store rideau", "media": "tele tv enceinte musique", "computer": "ordinateur pc serveur", "other": ""}
REFUSED_TYPES = {"lock": "serrure", "alarm": "alarme", "garage": "portail / garage", "door": "porte"}
CONFIRM_TYPES = {"cover", "computer"}
DRIVERS = ("tuya", "shelly", "tasmota", "wled", "yeelight", "wiz", "kasa", "wol", "mqtt", "ha", "hue", "cast")
SECRET_FIELDS = {"local_key", "password"}
MASK = "••••"
MAX_BULK = 6
ACTIONS = ("on", "off", "toggle", "brightness", "color", "temperature", "state")
COLORS = {"rouge": (255, 0, 0), "vert": (0, 200, 0), "bleu": (0, 0, 255), "jaune": (255, 210, 0), "orange": (255, 120, 0), "violet": (140, 0, 255),
          "rose": (255, 60, 150), "cyan": (0, 220, 220), "blanc": (255, 255, 255)}
STOP = {"le", "la", "les", "l", "du", "de", "des", "un", "une", "ma", "mon", "mes", "dans", "sur", "au", "aux", "d", "toute", "toutes", "tous", "tout"}


class DeviceError(RuntimeError):
    pass


_cache: list[dict] = []
_scene_cache: list[dict] = []


# ------------------------------------------------------------------ accès réseau (remplaçables dans les tests)
async def _http(method: str, url: str, **kw) -> tuple[int, Any]:
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            r = await c.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise DeviceError(f"Appareil injoignable : {exc}") from exc
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:300]


def _udp_send(data: bytes, host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(data, (host, port))


def _port_up(ip: str, ports=(22, 80, 443, 445, 3389, 8006, 5000)) -> bool:
    for p in ports:
        try:
            with socket.create_connection((ip, p), timeout=0.6):
                return True
        except ConnectionRefusedError:
            return True            # la machine répond : elle est allumée
        except OSError:
            continue
    return False


def _tuya_device(cfg: dict, dtype: str):
    import tinytuya
    cls = tinytuya.BulbDevice if dtype == "light" else tinytuya.OutletDevice
    d = cls(cfg["device_id"], cfg["ip"], cfg["local_key"], version=float(cfg.get("version") or 3.3))
    d.set_socketTimeout(5)
    d.set_socketRetryLimit(1)
    return d


def _tuya_cloud(creds: dict):
    import tinytuya
    return tinytuya.Cloud(apiRegion=creds["region"], apiKey=creds["key"], apiSecret=creds["secret"], apiDeviceID=creds.get("device_id", ""))


def _mqtt_client(cfg: dict):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], cfg.get("password") or None)
    return c


def _mqtt_publish(cfg: dict, topic: str, payload: str) -> None:
    c = _mqtt_client(cfg)
    c.connect(cfg["host"], int(cfg.get("port") or 1883), 10)
    c.loop_start()
    try:
        info = c.publish(topic, payload, qos=1)
        info.wait_for_publish(8)
    finally:
        c.loop_stop(); c.disconnect()


def _mqtt_read(cfg: dict, topic: str, timeout: float = 2.5) -> str | None:
    import threading
    got, ev = [], threading.Event()
    c = _mqtt_client(cfg)
    c.on_message = lambda cl, ud, m: (got.append(m.payload.decode(errors="replace")), ev.set())
    c.connect(cfg["host"], int(cfg.get("port") or 1883), 10)
    c.subscribe(topic)
    c.loop_start()
    try:
        ev.wait(timeout)
    finally:
        c.loop_stop(); c.disconnect()
    return got[0] if got else None


async def _tuya_creds() -> dict | None:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='tuya_cloud'")
    return (json.loads(raw) if isinstance(raw, str) else raw) if raw else None


# ------------------------------------------------------------------ registre
def _row(r) -> dict:
    cfg = r["config"]
    return {"id": r["id"], "name": r["name"], "room": r["room"], "type": r["type"], "driver": r["driver"],
            "config": json.loads(cfg) if isinstance(cfg, str) else cfg, "aliases": r["aliases"], "confirm": r["confirm"]}


async def reload() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, name, room, type, driver, config, aliases, confirm FROM devices ORDER BY room, name")
    _cache[:] = [_row(r) for r in rows]
    _scene_cache[:] = await list_scenes()
    return _cache


def public(d: dict) -> dict:
    cfg = {k: (MASK if k in SECRET_FIELDS and v else v) for k, v in d["config"].items()}
    return {**d, "config": cfg}


REQUIRED = {"tuya": ("device_id",), "shelly": ("ip",), "tasmota": ("ip",), "wled": ("ip",), "yeelight": ("ip",), "wiz": ("ip",), "kasa": ("ip",), "wol": ("mac",), "mqtt": ("host", "topic"), "ha": ("entity_id",), "hue": ("ip", "light"), "cast": ("ip",)}


def _validate(name: str, room: str, dtype: str, driver: str, cfg: dict) -> dict:
    name = " ".join((name or "").split())
    if not 2 <= len(name) <= 60:
        raise DeviceError("Nom : 2 à 60 caractères.")
    if dtype in REFUSED_TYPES:
        raise DeviceError(f"Pour ta sécurité, EVA ne pilote pas les {REFUSED_TYPES[dtype]}s : à faire à la main.")
    if dtype not in TYPES:
        raise DeviceError("Type inconnu.")
    if driver not in DRIVERS:
        raise DeviceError("Pilote inconnu.")
    cfg = {k: (v.strip() if isinstance(v, str) else v) for k, v in (cfg or {}).items() if v not in (None, "")}
    for k in REQUIRED[driver]:
        if not cfg.get(k):
            raise DeviceError(f"Champ « {k} » obligatoire pour ce pilote.")
    if driver == "tuya" and cfg.get("ip") and not cfg.get("local_key"):
        raise DeviceError("Pour le mode local il faut la clé locale (sinon laisse l'adresse IP vide : mode cloud).")
    if driver == "wol" and not re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", cfg["mac"]):
        raise DeviceError("Adresse MAC invalide (ex. AA:BB:CC:DD:EE:FF).")
    if driver == "ha":
        d, _, _ = cfg["entity_id"].partition(".")
        if d in ("lock", "alarm_control_panel"):
            raise DeviceError("Serrures et alarmes ne sont pas pilotables par EVA.")
    return cfg


async def save(dev_id: int | None, name: str, room: str, dtype: str, driver: str, cfg: dict, aliases: str = "", confirm: bool = False) -> dict:
    cfg = _validate(name, room, dtype, driver, cfg)
    async with get_pool().acquire() as conn:
        if dev_id:
            old = await conn.fetchval("SELECT config FROM devices WHERE id=$1", dev_id)
            if old is None:
                raise DeviceError("Appareil introuvable.")
            old = json.loads(old) if isinstance(old, str) else old
            for k in SECRET_FIELDS:                      # « •••• » = garder le secret existant
                if cfg.get(k) == MASK:
                    cfg[k] = old.get(k, "")
        try:
            if dev_id:
                await conn.execute("UPDATE devices SET name=$2, room=$3, type=$4, driver=$5, config=$6::jsonb, aliases=$7, confirm=$8 WHERE id=$1",
                                   dev_id, name.strip(), room.strip()[:40], dtype, driver, json.dumps(cfg), aliases.strip()[:200], bool(confirm))
            else:
                dev_id = await conn.fetchval("INSERT INTO devices (name, room, type, driver, config, aliases, confirm) VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7) RETURNING id",
                                             name.strip(), room.strip()[:40], dtype, driver, json.dumps(cfg), aliases.strip()[:200], bool(confirm))
        except Exception as exc:  # noqa: BLE001
            if "devices_name" in str(exc) or "unique" in str(exc).lower():
                raise DeviceError("Un appareil porte déjà ce nom.") from exc
            raise
    await reload()
    return public(next(d for d in _cache if d["id"] == dev_id))


async def delete(dev_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM devices WHERE id=$1", dev_id)
    await reload()


# ------------------------------------------------------------------ recherche
def _haystack(d: dict) -> str:
    return norm(f"{d['name']} {d['room']} {d['aliases'].replace(',', ' ')} {TYPE_WORDS.get(d['type'], '')}")


def _type_of(word: str) -> str | None:
    w = norm(word)
    if w in TYPES:
        return w
    for t, words in TYPE_WORDS.items():
        if w and w in words.split():
            return t
    return None


def find(query: str = "", room: str = "", dtype: str = "") -> list[dict]:
    out = list(_cache)
    if dtype:
        t = _type_of(dtype)
        if t is None:
            return []
        out = [d for d in out if d["type"] == t]
    if room:
        r = norm(room)
        out = [d for d in out if r and (r == norm(d["room"]) or r in norm(d["room"]))]
    if query:
        q = norm(query)
        exact = [d for d in out if q == norm(d["name"]) or q in [norm(a) for a in d["aliases"].split(",") if a.strip()]]
        if exact:
            return exact
        toks = [t for t in q.split() if t not in STOP]
        out = [d for d in out if toks and all(t in _haystack(d) or any(t.rstrip("s") == w.rstrip("s") for w in _haystack(d).split()) for t in toks)]
        if len(out) > 1:        # le nom propre exact gagne (« lampe » → « Lampe bureau » plutôt que toutes les lumières)
            named = [d for d in out if all(t in norm(d["name"]).split() for t in toks)]
            if len(named) == 1:
                return named
    return out


def needs_confirm(args: dict) -> bool:
    targets = find(str(args.get("device", "") or ""), str(args.get("room", "") or ""), str(args.get("type", "") or ""))
    if len(targets) > MAX_BULK:
        return True
    return any(d["confirm"] or d["type"] in CONFIRM_TYPES for d in targets)


# ------------------------------------------------------------------ pilotes
def _rgb(value) -> tuple[int, int, int]:
    v = norm(str(value))
    if v in COLORS:
        return COLORS[v]
    m = re.fullmatch(r"#?([0-9a-f]{6})", str(value).strip().lower())
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    raise DeviceError(f"Couleur inconnue : {value} (essaie {', '.join(COLORS)} ou #RRGGBB).")


def _pct(value) -> int:
    try:
        return max(0, min(100, int(float(str(value).replace("%", "")))))
    except ValueError as exc:
        raise DeviceError("Valeur attendue : un pourcentage (0 à 100).") from exc


_HA_OFF = {"off", "closed", "idle", "standby", "paused", "unavailable", "unknown", "none"}


async def _ha(d: dict, action: str, value) -> dict:
    eid = d["config"]["entity_id"]
    dom = eid.split(".")[0]
    if action == "state":
        s = await ha.get_state(eid)
        raw = s.get("etat")
        if raw in ("unavailable", "unknown"):
            raise DeviceError("Home Assistant indique que cet appareil est injoignable (« %s »)." % raw)
        out = {"on": raw not in _HA_OFF, "raw": raw}
        pct = (s.get("attributs") or {}).get("brightness")
        if isinstance(pct, (int, float)):
            out["brightness"] = round(pct * 100 / 255)
        return out
    if dom == "cover":                                           # open_cover / close_cover (turn_on n'existe pas pour un volet)
        svc = {"on": "open_cover", "off": "close_cover"}.get(action)
        if action == "toggle":
            cur = (await ha.get_state(eid)).get("etat")
            svc = "close_cover" if cur in ("open", "opening") else "open_cover"
        if not svc:
            raise DeviceError("Un volet s'ouvre (allumer) ou se ferme (éteindre).")
        await ha.call_cover(svc, eid)
        return {"ok": True}
    if dom == "scene":
        if action != "on":
            raise DeviceError("Une scène Home Assistant se lance seulement (allumer).")
        await ha.call_service("scene", "turn_on", eid, None)
        return {"ok": True}
    if action in ("on", "off", "toggle"):
        await ha.call_service(dom, {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[action], eid, None)
    elif action == "brightness":
        if dom == "media_player":
            await ha.call_service(dom, "volume_set", eid, {"volume_level": _pct(value) / 100})
        elif dom == "light":
            await ha.call_service(dom, "turn_on", eid, {"brightness_pct": _pct(value)})
        elif dom == "fan":
            await ha.call_service(dom, "set_percentage", eid, {"percentage": _pct(value)})
        else:
            raise DeviceError("Cet appareil n'a pas de réglage d'intensité.")
    elif action == "color":
        if dom != "light":
            raise DeviceError("Seules les lumières changent de couleur.")
        v = norm(str(value))
        if v in ("blanc chaud", "blanc froid"):
            await ha.call_service(dom, "turn_on", eid, {"color_temp_kelvin": 2700 if v == "blanc chaud" else 6500})
        else:
            await ha.call_service(dom, "turn_on", eid, {"rgb_color": list(_rgb(value))})
    elif action == "temperature" and dom == "light":
        # Lumière blanche réglable (vidéo Godox, ampoules…) : kelvins (« 5600 ») ou % (0 = chaud, 100 = froid).
        try:
            v = float(re.sub(r"[^\d.,]", "", str(value)).replace(",", ".") or "nan")
        except ValueError as exc:
            raise DeviceError("Valeur attendue : une température de couleur en kelvins (ex. 5600) ou un pourcentage.") from exc
        k = int(v) if v >= 1000 else int(2700 + max(0.0, min(100.0, v)) / 100 * (6500 - 2700))
        await ha.call_service(dom, "turn_on", eid, {"color_temp_kelvin": max(1500, min(10000, k))})
    elif action == "temperature":
        if dom != "climate":
            raise DeviceError("La température se règle sur un chauffage / une clim.")
        try:
            t = float(str(value).replace(",", ".").replace("°", ""))
        except ValueError as exc:
            raise DeviceError("Valeur attendue : une température en degrés.") from exc
        await ha.call_service("climate", "set_temperature", eid, {"temperature": t})
    return {"ok": True}


async def _tuya(d: dict, action: str, value) -> dict:
    cfg = d["config"]
    if cfg.get("ip"):
        dev = await asyncio.to_thread(_tuya_device, cfg, d["type"])
        dp = int(cfg.get("switch_dp") or 0) or (0 if d["type"] == "light" else 1)      # ampoule : tinytuya choisit lui-même le bon DP (20 ou 1) — forcer 1 n'allumait rien
        dps_try = ((str(dp),) if dp else ()) + ("20", "1")

        def work():
            if action == "state":
                st = dev.status()
                dps = (st or {}).get("dps") or {}
                if not dps:
                    raise DeviceError(f"Pas de réponse de l'appareil ({(st or {}).get('Error', 'inconnu')}).")
                on = next((bool(dps[k]) for k in dps_try if k in dps and isinstance(dps[k], bool)), None)
                return {"on": on, "raw": dps}
            if d["type"] == "light" and action not in ("state", "toggle"):
                pre = dev.status() or {}                     # une ampoule doit être lue d'abord : c'est là que tinytuya reconnaît son modèle (DP 20 ou 1, couleur…)
                if not pre.get("dps"):
                    raise DeviceError(f"Pas de réponse de l'appareil ({pre.get('Error', 'inconnu')}).")
            if action == "toggle":
                st = (dev.status() or {}).get("dps") or {}
                cur = next((bool(st[k]) for k in dps_try if k in st and isinstance(st[k], bool)), False)
                r = dev.turn_off(switch=dp) if cur else dev.turn_on(switch=dp)
            elif action == "on":
                r = dev.turn_on(switch=dp)
            elif action == "off":
                r = dev.turn_off(switch=dp)
            elif action == "brightness" and d["type"] == "light":
                r = dev.set_brightness_percentage(max(1, _pct(value)))
            elif action == "color" and d["type"] == "light":
                v = norm(str(value))
                r = dev.set_white_percentage(100, 0) if v == "blanc chaud" else dev.set_white_percentage(100, 100) if v == "blanc froid" else dev.set_colour(*_rgb(value))
            else:
                raise DeviceError(f"Action « {action} » non prise en charge par cet appareil.")
            if isinstance(r, dict) and r.get("Error"):
                raise DeviceError(f"Tuya : {r['Error']}")
            return {"ok": True}
        return await asyncio.to_thread(work)
    # mode cloud
    creds = await _tuya_creds()
    if not creds:
        raise DeviceError("Appareil Tuya sans adresse IP : enregistre ton compte Tuya cloud (Maison › Appareils › Importer depuis Tuya).")
    cloud = await asyncio.to_thread(_tuya_cloud, creds)
    code = cfg.get("switch_code") or ("switch_led" if d["type"] == "light" else "switch_1")

    def work_cloud():
        if action == "state":
            res = cloud.getstatus(cfg["device_id"]) or {}
            vals = {x["code"]: x["value"] for x in res.get("result", [])}
            return {"on": next((vals[k] for k in (code, "switch_led", "switch_1", "switch") if k in vals), None), "raw": vals}
        if action == "toggle":
            vals = {x["code"]: x["value"] for x in (cloud.getstatus(cfg["device_id"]) or {}).get("result", [])}
            cmds = [{"code": code, "value": not bool(vals.get(code))}]
        elif action in ("on", "off"):
            cmds = [{"code": code, "value": action == "on"}]
        elif action == "brightness" and d["type"] == "light":
            cmds = [{"code": cfg.get("bright_code") or "bright_value_v2", "value": max(10, _pct(value) * 10)}]
        else:
            raise DeviceError(f"Action « {action} » non disponible en mode cloud pour cet appareil.")
        r = cloud.sendcommand(cfg["device_id"], {"commands": cmds}) or {}
        if r.get("success") is False:
            raise DeviceError(f"Tuya cloud : {r.get('msg', 'refusé')}")
        return {"ok": True}
    return await asyncio.to_thread(work_cloud)


async def _shelly(d: dict, action: str, value) -> dict:
    ip, ch, gen = d["config"]["ip"], int(d["config"].get("channel") or 0), int(d["config"].get("gen") or 2)
    base = f"http://{ip}"
    if action == "state":
        if gen == 1:
            _, r = await _http("GET", f"{base}/relay/{ch}"); return {"on": bool(r.get("ison")), "raw": r}
        _, r = await _http("GET", f"{base}/rpc/Switch.GetStatus?id={ch}"); return {"on": bool(r.get("output")), "raw": r}
    if action not in ("on", "off", "toggle"):
        raise DeviceError("Shelly : seulement allumer / éteindre / basculer.")
    if gen == 1:
        st, _ = await _http("GET", f"{base}/relay/{ch}?turn={action}")
    elif action == "toggle":
        st, _ = await _http("GET", f"{base}/rpc/Switch.Toggle?id={ch}")
    else:
        st, _ = await _http("GET", f"{base}/rpc/Switch.Set?id={ch}&on={'true' if action == 'on' else 'false'}")
    if st >= 400:
        raise DeviceError(f"Shelly a répondu HTTP {st}.")
    return {"ok": True}


async def _tasmota(d: dict, action: str, value) -> dict:
    ip = d["config"]["ip"]
    cmd = {"state": "Power", "on": "Power On", "off": "Power Off", "toggle": "Power Toggle"}.get(action)
    if action == "brightness":
        cmd = f"Dimmer {_pct(value)}"
    if not cmd:
        raise DeviceError("Tasmota : action non prise en charge.")
    st, r = await _http("GET", f"http://{ip}/cm", params={"cmnd": cmd})
    if st >= 400 or not isinstance(r, dict):
        raise DeviceError(f"Tasmota a répondu HTTP {st}.")
    power = r.get("POWER") or r.get("POWER1")
    return {"on": (power == "ON") if power else None, "raw": r} if action == "state" else {"ok": True}


async def _wled(d: dict, action: str, value) -> dict:
    ip = d["config"]["ip"]
    if action == "state":
        _, r = await _http("GET", f"http://{ip}/json/state"); return {"on": bool(r.get("on")), "raw": {"bri": r.get("bri")}}
    body: dict
    if action in ("on", "off"):
        body = {"on": action == "on"}
    elif action == "toggle":
        body = {"on": "t"}
    elif action == "brightness":
        body = {"on": True, "bri": max(1, round(_pct(value) * 2.55))}
    elif action == "color":
        body = {"on": True, "seg": [{"col": [list(_rgb(value))]}]}
    else:
        raise DeviceError("WLED : action non prise en charge.")
    st, _ = await _http("POST", f"http://{ip}/json/state", json=body)
    if st >= 400:
        raise DeviceError(f"WLED a répondu HTTP {st}.")
    return {"ok": True}


async def _wol(d: dict, action: str, value) -> dict:
    cfg = d["config"]
    if action == "state":
        if not cfg.get("ip"):
            raise DeviceError("Ajoute l'adresse IP de la machine pour connaître son état.")
        return {"on": await asyncio.to_thread(_port_up, cfg["ip"]), "raw": None}
    if action != "on":
        raise DeviceError("Wake-on-LAN sait seulement allumer. Pour éteindre, utilise l'accès SSH (Réseau).")
    mac = bytes.fromhex(re.sub(r"[:-]", "", cfg["mac"]))
    await asyncio.to_thread(_udp_send, b"\xff" * 6 + mac * 16, cfg.get("broadcast") or "255.255.255.255", int(cfg.get("port") or 9))
    return {"ok": True, "note": "Paquet de réveil envoyé (la machine peut mettre une minute à démarrer)."}


async def _mqtt(d: dict, action: str, value) -> dict:
    cfg = d["config"]
    if action == "state":
        if not cfg.get("state_topic"):
            raise DeviceError("Pas de topic d'état configuré.")
        raw = await asyncio.to_thread(_mqtt_read, cfg, cfg["state_topic"])
        return {"on": (raw or "").strip().upper() in (str(cfg.get("payload_on") or "ON").upper(), "1", "TRUE") if raw is not None else None, "raw": raw}
    if action == "toggle" and cfg.get("payload_toggle"):
        await asyncio.to_thread(_mqtt_publish, cfg, cfg["topic"], cfg["payload_toggle"])
    elif action in ("on", "off"):
        await asyncio.to_thread(_mqtt_publish, cfg, cfg["topic"], cfg.get("payload_on") or "ON" if action == "on" else cfg.get("payload_off") or "OFF")
    elif action == "brightness" and cfg.get("brightness_topic"):
        await asyncio.to_thread(_mqtt_publish, cfg, cfg["brightness_topic"], str(_pct(value)))
    else:
        raise DeviceError("MQTT : action non configurée pour cet appareil.")
    return {"ok": True}


async def _hue(d: dict, action: str, value) -> dict:
    from . import hue
    try:
        return await hue.piloter(d["config"], action, value, rgb_de=_rgb, pct_de=_pct)
    except hue.HueError as exc:
        raise DeviceError(str(exc)) from exc


async def _cast(d: dict, action: str, value) -> dict:
    from . import cast
    try:
        return await cast.piloter(d["config"], action, value, pct_de=_pct)
    except cast.CastError as exc:
        raise DeviceError(str(exc)) from exc


_RUN = {"cast": _cast, "hue": _hue, "ha": _ha, "tuya": _tuya, "shelly": _shelly, "tasmota": _tasmota, "wled": _wled, "yeelight": lan_drivers.yeelight, "wiz": lan_drivers.wiz,
        "kasa": lan_drivers.kasa, "wol": _wol, "mqtt": _mqtt}


async def run(d: dict, action: str, value=None) -> dict:
    if action not in ACTIONS:
        raise DeviceError(f"Action inconnue (attendu : {', '.join(ACTIONS)}).")
    try:
        return await _RUN[d["driver"]](d, action, value)
    except DeviceError:
        raise
    except ha.HAError as exc:
        raise DeviceError(str(exc)) from exc
    except ImportError as exc:
        raise DeviceError(f"Bibliothèque manquante pour ce pilote ({exc.name}) : reconstruis l'image eva-core.") from exc
    except Exception as exc:  # noqa: BLE001 — appareil éteint, réseau, clé erronée…
        raise DeviceError(f"{type(exc).__name__}: {exc}") from exc


async def control(query: str = "", action: str = "state", value=None, room: str = "", dtype: str = "") -> dict:
    """Commande un ou plusieurs appareils. Plusieurs cibles seulement pour allumer / éteindre / lire l'état."""
    if not _cache:
        await reload()
    if not (query or room or dtype):
        raise DeviceError("Précise l'appareil, ou une pièce / un type.")
    targets = find(query, room, dtype)
    if not targets:
        names = ", ".join(f"{d['name']}{' (' + d['room'] + ')' if d['room'] else ''}" for d in _cache[:25]) or "aucun appareil enregistré"
        raise DeviceError(f"Aucun appareil ne correspond. Appareils connus : {names}.")
    if len(targets) > 1 and action not in ("on", "off", "state"):
        raise DeviceError("Plusieurs appareils correspondent : " + ", ".join(d["name"] for d in targets) + ". Précise lequel.")
    if len(targets) > 1 and query and not room and not dtype and action in ("on", "off"):
        raise DeviceError("Plusieurs appareils correspondent : " + ", ".join(d["name"] for d in targets) + ". Précise lequel (ou donne la pièce).")

    async def one(d):
        try:
            return {"device": d["name"], "room": d["room"], "ok": True, **await run(d, action, value)}
        except DeviceError as exc:
            return {"device": d["name"], "room": d["room"], "ok": False, "error": str(exc)}
    return {"results": await asyncio.gather(*(one(d) for d in targets))}


# ------------------------------------------------------------------ scènes
async def list_scenes() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, name, actions FROM scenes ORDER BY name")
    return [{"id": r["id"], "name": r["name"], "actions": json.loads(r["actions"]) if isinstance(r["actions"], str) else r["actions"]} for r in rows]


def _clean_actions(actions: list) -> list[dict]:
    out = []
    for a in actions or []:
        dev, act = str(a.get("device", "")).strip(), str(a.get("action", "")).strip()
        if not dev or act not in ACTIONS or act == "state":
            raise DeviceError("Chaque étape d'une scène : un appareil et une action (on, off, toggle, brightness, color, temperature).")
        out.append({"device": dev, "action": act, **({"value": a["value"]} if a.get("value") not in (None, "") else {})})
    if not out:
        raise DeviceError("Une scène a besoin d'au moins une étape.")
    return out[:40]


async def save_scene(scene_id: int | None, name: str, actions: list) -> dict:
    name = " ".join((name or "").split())[:60]
    if not name:
        raise DeviceError("Nom de scène vide.")
    acts = _clean_actions(actions)
    if not _cache:
        await reload()
    for a in acts:
        if not find(a["device"]):
            raise DeviceError(f"Appareil introuvable dans la scène : {a['device']}")
    async with get_pool().acquire() as conn:
        try:
            if scene_id:
                await conn.execute("UPDATE scenes SET name=$2, actions=$3::jsonb WHERE id=$1", scene_id, name, json.dumps(acts))
            else:
                scene_id = await conn.fetchval("INSERT INTO scenes (name, actions) VALUES ($1,$2::jsonb) RETURNING id", name, json.dumps(acts))
        except Exception as exc:  # noqa: BLE001
            if "unique" in str(exc).lower():
                raise DeviceError("Une scène porte déjà ce nom.") from exc
            raise
    _scene_cache[:] = await list_scenes()
    return {"id": scene_id, "name": name, "actions": acts}


async def delete_scene(scene_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM scenes WHERE id=$1", scene_id)
    _scene_cache[:] = await list_scenes()


async def find_scene(query: str) -> dict | None:
    q = norm(query)
    scenes = await list_scenes()
    for s in scenes:
        if norm(s["name"]) == q:
            return s
    hits = [s for s in scenes if q and (q in norm(s["name"]) or norm(s["name"]) in q)]
    return hits[0] if len(hits) == 1 else None


def scene_needs_confirm(name: str) -> bool:
    """Décision synchrone (cache) : une scène qui touche un appareil sensible demande l'accord."""
    q = norm(name)
    sc = next((s for s in _scene_cache if norm(s["name"]) == q), None) or next((s for s in _scene_cache if q and q in norm(s["name"])), None)
    return bool(sc) and any(needs_confirm({"device": a["device"]}) for a in sc["actions"])


async def run_scene(scene: dict) -> dict:
    if not _cache:
        await reload()
    res = []
    for a in scene["actions"]:                 # dans l'ordre : une scène peut compter sur la séquence
        try:
            targets = find(a["device"])
            if len(targets) != 1:
                raise DeviceError("appareil introuvable ou ambigu")
            await run(targets[0], a["action"], a.get("value"))
            res.append({"device": a["device"], "ok": True})
        except DeviceError as exc:
            res.append({"device": a["device"], "ok": False, "error": str(exc)})
    return {"scene": scene["name"], "results": res}


# ------------------------------------------------------------------ Tuya cloud : import
async def tuya_save_creds(region: str, key: str, secret: str, device_id: str) -> None:
    if region not in ("eu", "us", "cn", "in", "us-e", "eu-w"):
        raise DeviceError("Région Tuya : eu, us, cn, in, us-e ou eu-w.")
    if not (key and secret and device_id):
        raise DeviceError("Access ID, Access Secret et l'ID d'un de tes appareils sont nécessaires.")
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('tuya_cloud', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                           json.dumps({"region": region, "key": key.strip(), "secret": secret.strip(), "device_id": device_id.strip()}))


async def tuya_cloud_devices() -> list[dict]:
    creds = await _tuya_creds()
    if not creds:
        raise DeviceError("Enregistre d'abord ton compte Tuya cloud.")
    cloud = await asyncio.to_thread(_tuya_cloud, creds)
    res = await asyncio.to_thread(cloud.getdevices)
    if isinstance(res, dict) and res.get("Error"):
        raise DeviceError(f"Tuya cloud : {res['Error']}")
    known = {d["config"].get("device_id") for d in _cache}
    return [{"device_id": x.get("id"), "name": x.get("name"), "local_key": x.get("key", ""), "category": x.get("category", ""), "ip": "",   # l'adresse du cloud est publique (WAN), pas celle du réseau local
             
             "version": x.get("version", ""), "mac": x.get("mac", ""), "already": x.get("id") in known} for x in (res or []) if isinstance(x, dict) and x.get("id")]


def tuya_type(category: str) -> str:
    return {"dj": "light", "dd": "light", "xdd": "light", "fwd": "light", "tgq": "light", "cz": "switch", "kg": "switch", "pc": "switch", "fs": "fan",
            "wk": "climate", "kt": "climate", "cl": "cover", "clkg": "cover"}.get(category, "switch")


async def tuya_status() -> dict:
    c = await _tuya_creds()
    return {"configured": bool(c), "region": (c or {}).get("region", ""), "key": (c or {}).get("key", "")}


async def set_ip(dev_id: int, ip: str) -> None:
    """Renseigne l'adresse IP d'un appareil (passage du mode cloud au mode local pour Tuya)."""
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT config FROM devices WHERE id=$1", dev_id)
        if raw is None:
            raise DeviceError("Appareil introuvable.")
        cfg = json.loads(raw) if isinstance(raw, str) else raw
        cfg["ip"] = ip
        await conn.execute("UPDATE devices SET config=$2::jsonb WHERE id=$1", dev_id, json.dumps(cfg))
    await reload()
