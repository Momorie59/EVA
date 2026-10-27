"""Détection et ajout des appareils de la maison — version « de A à Z ».

Principe : un petit service `eva-scanner` tourne en réseau hôte (un conteneur Docker en réseau « bridge » ne voit ni les adresses MAC, ni les
diffusions UDP, ni mDNS/SSDP). Il renvoie des PREUVES brutes (ARP, mDNS, SSDP, diffusions Tuya/WiZ/Yeelight/Kasa). Ce module :

1. récupère ces preuves (ou, à défaut, fait un balayage TCP depuis le conteneur — réduit, avec un avertissement clair) ;
2. complète par des empreintes HTTP (Shelly, WLED, Tasmota, Hue) et IPP (imprimantes) ;
3. fusionne tout en « candidats » (un par appareil physique) avec le pilote, le type et la configuration proposés ;
4. ajoute un candidat seulement après l'avoir TESTÉ, à partir de ce que le serveur a lui-même trouvé (jamais de ce que le navigateur envoie) ;
5. retrouve un appareil dont l'adresse IP a changé (même identité, autre IP) et met l'adresse à jour toute seule.

La classification (`build_candidates`) est une fonction pure : elle est testée avec des relevés enregistrés."""
import asyncio
import json
import re
import time
from typing import Any

import httpx

from . import devices, tuya_local
from .config import settings
from .db import get_pool

SCAN_TIMEOUT = 75.0
MAX_CANDIDATES = 200
_ESP = ("espressif", "tuya")

DEFAULTS = {"enabled": True, "interval_min": 30, "cidr": "", "last_run": 0.0}
_state: dict[str, Any] = {"running": False, "started": 0.0, "finished": 0.0, "step": "", "error": ""}
_task: asyncio.Task | None = None


class DiscoveryError(RuntimeError):
    pass


# ── Stockage ────────────────────────────────────────────────────────────────
async def _kv_get(key: str):
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def _kv_set(key: str, value) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", key, json.dumps(value))


def _mac(mac: str) -> str:
    m = re.sub(r"[^0-9a-f]", "", (mac or "").lower())
    return ":".join(m[i:i + 2] for i in range(0, 12, 2)).upper() if len(m) == 12 else ""


def _vendor(mac: str) -> str:
    from . import network
    return network.vendor(mac)


# ── Récupération des preuves ────────────────────────────────────────────────
def _scanner_headers() -> dict:
    tok = settings.scanner_token
    return {"Authorization": f"Bearer {tok}"} if tok else {}


async def scanner_health() -> dict:
    url = settings.scanner_url
    if not url:
        return {"configured": False, "up": False, "problem": "Aucun service de détection configuré (EVA_SCANNER_URL vide)."}
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(url.rstrip("/") + "/health")
            r.raise_for_status()
            return {"configured": True, "up": True, **r.json()}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "up": False, "problem": _scanner_problem(exc)}


def _scanner_problem(exc: Exception) -> str:
    return (f"Le service de détection eva-scanner ne répond pas ({type(exc).__name__}). Lance « docker compose up -d --build eva-scanner » ; "
            "si le pare-feu du NAS est actif : « sudo ufw allow from 172.16.0.0/12 to any port 8300 proto tcp ».")


async def fetch_scan(quick: bool = False, cidr: str = "") -> tuple[dict, str, str]:
    """→ (preuves, source, problème). source : « scanner » (complet) ou « conteneur » (réduit)."""
    if settings.scanner_url:
        try:
            body = {"quick": quick, "cidrs": [cidr] if cidr else None}
            async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as c:
                r = await c.post(settings.scanner_url.rstrip("/") + "/scan", json=body, headers=_scanner_headers())
            if r.status_code == 200:
                return r.json(), "scanner", ""
            problem = f"Le service eva-scanner a répondu {r.status_code}" + (" (jeton refusé : EVA_SCANNER_TOKEN doit être identique des deux côtés)." if r.status_code in (401, 403) else ".")
        except Exception as exc:  # noqa: BLE001
            problem = _scanner_problem(exc)
    else:
        problem = "Service eva-scanner non configuré."
    return await _fallback_scan(cidr), "conteneur", problem


async def _fallback_scan(cidr: str = "") -> dict:
    """Repli : balayage TCP depuis le conteneur. Pas d'adresses MAC ni de diffusion : la détection est donc réduite."""
    from . import network, printing
    c = cidr or printing.default_cidr()
    net = network.check_private(c)
    hosts = await network.sweep(net)
    return {"interfaces": [], "cidrs": [str(net)], "mdns": [], "ssdp": [], "tuya": [], "wiz": [], "yeelight": [], "kasa": [],
            "hosts": [{"ip": h["ip"], "mac": h.get("mac", ""), "hostname": h.get("hostname", ""), "ports": [p["port"] for p in h["ports"]]} for h in hosts],
            "errors": {}, "took": 0}


# ── Empreintes (HTTP / IPP) ─────────────────────────────────────────────────
async def _get_json(c: httpx.AsyncClient, url: str):
    try:
        r = await c.get(url)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return None


async def fingerprint(ip: str, ports: list[int]) -> dict:
    """Ce que l'appareil dit de lui-même en HTTP. Ne modifie rien."""
    fp: dict[str, Any] = {}
    ports = set(ports or [])
    if not ports or 80 in ports:
        async with httpx.AsyncClient(timeout=2.5) as c:
            j = await _get_json(c, f"http://{ip}/shelly")
            if isinstance(j, dict) and (j.get("type") or j.get("model") or j.get("app") or j.get("gen")):
                fp["shelly"] = {"gen": int(j.get("gen") or 1), "name": j.get("name") or "", "model": j.get("type") or j.get("model") or j.get("app") or "", "mac": j.get("mac", "")}
                return fp
            j = await _get_json(c, f"http://{ip}/json/info")
            if isinstance(j, dict) and str(j.get("brand", "")).lower() == "wled":
                fp["wled"] = {"name": j.get("name") or "WLED", "mac": j.get("mac", ""), "leds": (j.get("leds") or {}).get("count")}
                return fp
            j = await _get_json(c, f"http://{ip}/cm?cmnd=Status")
            if isinstance(j, dict) and isinstance(j.get("Status"), dict):
                fn = j["Status"].get("FriendlyName") or j["Status"].get("DeviceName") or []
                fp["tasmota"] = {"name": str((fn[0] if isinstance(fn, list) and fn else fn) or "")}
                return fp
            j = await _get_json(c, f"http://{ip}/api/config")
            if isinstance(j, dict) and (j.get("bridgeid") or str(j.get("modelid", "")).startswith(("BSB", "BSB002"))):
                fp["hue"] = {"name": j.get("name") or "Pont Hue", "mac": j.get("mac", ""), "bridgeid": j.get("bridgeid", "")}
                return fp
    return fp


async def printer_fp(ip: str) -> dict | None:
    from . import printing
    uri = f"ipp://{ip}:631/ipp/print"
    try:
        info = await asyncio.wait_for(printing.printer_info(uri), 6)
        return {"uri": uri, "model": info.get("model") or ""}
    except Exception:  # noqa: BLE001
        return None


# ── Classification (pure) ───────────────────────────────────────────────────
def _have(devs: list[dict]) -> dict:
    """Index des appareils déjà enregistrés pour reconnaître un doublon."""
    idx: dict[str, dict] = {"ip": {}, "mac": {}, "tuya": {}, "yee": {}}
    for d in devs:
        cfg = d.get("config") or {}
        for k in ("ip", "host"):
            if cfg.get(k):
                idx["ip"][cfg[k]] = d
        if _mac(cfg.get("mac", "")):
            idx["mac"][_mac(cfg["mac"])] = d
        if d.get("driver") == "tuya" and cfg.get("device_id"):
            idx["tuya"][cfg["device_id"]] = d
        if d.get("driver") == "yeelight" and cfg.get("id"):
            idx["yee"][cfg["id"]] = d
    return idx


def build_candidates(scan: dict, fps: dict[str, dict], devs: list[dict], printers: list[str] | None = None) -> dict:
    """Fusionne les preuves en candidats. → {candidates, others, healed}.

    scan : relevé du scanner ; fps : {ip: {"shelly":…, "printer":…}} ; devs : appareils enregistrés ; printers : IP d'imprimantes déjà ajoutées."""
    printers = printers or []
    by_ip: dict[str, dict] = {}

    def slot(ip: str) -> dict:
        return by_ip.setdefault(ip, {"ip": ip, "mac": "", "hostname": "", "ports": [], "ev": [], "found": {}})

    for h in scan.get("hosts") or []:
        s = slot(h["ip"])
        s["mac"] = _mac(h.get("mac", "")) or s["mac"]
        s["hostname"] = h.get("hostname", "") or s["hostname"]
        s["ports"] = sorted(set(s["ports"]) | set(h.get("ports") or []))
    for m in scan.get("mdns") or []:
        s = slot(m["ip"])
        s["found"].setdefault("mdns", []).append(m)
        s["hostname"] = s["hostname"] or m.get("server", "")
    for x in scan.get("ssdp") or []:
        slot(x["ip"])["found"]["ssdp"] = x
    for t in scan.get("tuya") or []:
        slot(t["ip"])["found"]["tuya"] = t
    for w in scan.get("wiz") or []:
        s = slot(w["ip"])
        s["found"]["wiz"] = w
        s["mac"] = _mac(w.get("mac", "")) or s["mac"]
    for y in scan.get("yeelight") or []:
        slot(y["ip"])["found"]["yeelight"] = y
    for k in scan.get("kasa") or []:
        s = slot(k["ip"])
        s["found"]["kasa"] = k
        s["mac"] = _mac(k.get("mac", "")) or s["mac"]
    for ip, fp in (fps or {}).items():
        s = slot(ip)
        for kind, v in fp.items():
            s["found"][kind] = v
            if isinstance(v, dict) and _mac(v.get("mac", "")) and not s["mac"]:
                s["mac"] = _mac(v["mac"])

    idx = _have(devs)
    cands, others, healed = [], [], []
    for ip, s in sorted(by_ip.items(), key=lambda kv: tuple(int(p) for p in kv[0].split("."))):
        f, mac = s["found"], s["mac"]
        vendor = _vendor(mac)
        c = classify(s, f, vendor)
        c.update(ip=ip, mac=mac, vendor=vendor, hostname=s["hostname"], ports=s["ports"])
        c["key"] = f"{c['kind']}:{mac or ip}"
        # appareil déjà enregistré ?
        dev = None
        if c["kind"] == "tuya":
            dev = idx["tuya"].get(f["tuya"]["gwId"])
            c["device_id"] = f["tuya"]["gwId"]
        elif c["kind"] == "yeelight":
            dev = idx["yee"].get(f["yeelight"].get("id", ""))
        dev = dev or (idx["mac"].get(mac) if mac else None) or idx["ip"].get(ip)
        if c["kind"] == "printer":
            c["already"] = ip in printers
        elif dev:
            c["already"] = dev["id"]
            c["device_name"] = dev["name"]
            old = (dev.get("config") or {}).get("ip")
            ident = dev["driver"] in ("tuya", "yeelight", "wiz", "kasa", "shelly", "wled", "tasmota", "wol")
            if ident and old and old != ip and c["kind"] == dev["driver"]:
                healed.append({"id": dev["id"], "name": dev["name"], "old": old, "new": ip})
            elif dev["driver"] == "tuya" and c["kind"] == "tuya" and not old:
                c["link_device"] = dev["id"]                       # appareil importé du cloud : il ne lui manque que l'adresse
                c["already"] = False
        else:
            c["already"] = False
        (cands if c["kind"] != "unknown" else others).append(c)
    return {"candidates": cands[:MAX_CANDIDATES], "others": others[:MAX_CANDIDATES], "healed": healed}


def classify(s: dict, f: dict, vendor: str) -> dict:
    """Une machine → ce que c'est, le pilote à utiliser, et ce qui prouve cette conclusion."""
    ip, ports = s["ip"], set(s["ports"])
    ev: list[str] = []
    suffix = ip.split(".")[-1]
    if "yeelight" in f:
        y = f["yeelight"]
        ev.append(f"Diffusion Yeelight reçue ({y.get('model') or 'ampoule'})")
        return dict(kind="yeelight", driver="yeelight", type="light", name=y.get("name") or f"Yeelight {suffix}", status="ready", evidence=ev,
                    config={"ip": ip, "port": y.get("port") or 55443, "id": y.get("id", "")}, confirm=False, label=f"Ampoule Yeelight {y.get('model', '')}".strip())
    if "wiz" in f:
        w = f["wiz"]
        ev.append("Réponse WiZ (UDP 38899)")
        mod = str(w.get("module", "")).upper()
        return dict(kind="wiz", driver="wiz", type="switch" if "SOCKET" in mod else "light", name=f"WiZ {suffix}", status="ready", evidence=ev,
                    config={"ip": ip}, confirm=False, label="Ampoule / prise WiZ")
    if "kasa" in f:
        k = f["kasa"]
        ev.append(f"Réponse TP-Link Kasa ({k.get('model') or '?'})")
        return dict(kind="kasa", driver="kasa", type="light" if k.get("kind") == "bulb" else "switch", name=k.get("alias") or f"Kasa {suffix}", status="ready", evidence=ev,
                    config={"ip": ip}, confirm=False, label=f"TP-Link Kasa {k.get('model', '')}".strip())
    if "shelly" in f:
        sh = f["shelly"]
        ev.append(f"/shelly répond (génération {sh['gen']})")
        return dict(kind="shelly", driver="shelly", type="switch", name=sh.get("name") or f"Shelly {suffix}", status="ready", evidence=ev,
                    config={"ip": ip, "gen": sh["gen"]}, confirm=True, label=f"Shelly {sh.get('model', '')}".strip())
    if "wled" in f:
        ev.append("/json/info : WLED")
        return dict(kind="wled", driver="wled", type="light", name=f["wled"].get("name") or f"WLED {suffix}", status="ready", evidence=ev,
                    config={"ip": ip}, confirm=False, label="Rubans LED WLED")
    if "tasmota" in f:
        ev.append("/cm?cmnd=Status : Tasmota")
        return dict(kind="tasmota", driver="tasmota", type="switch", name=f["tasmota"].get("name") or f"Tasmota {suffix}", status="ready", evidence=ev,
                    config={"ip": ip}, confirm=True, label="Appareil Tasmota")
    if "tuya" in f:
        t = f["tuya"]
        ev.append(f"Diffusion Tuya reçue (protocole {t.get('version') or '?'}, id {t['gwId']})")
        return dict(kind="tuya", driver="tuya", type="switch", name=f"Tuya {suffix}", status="needs_key", evidence=ev, confirm=False,
                    config={"ip": ip, "device_id": t["gwId"], "version": t.get("version") or ""}, label="Appareil Tuya / Smart Life",
                    hint="Il faut la clé locale de l'appareil (compte Tuya cloud) pour le piloter sans passer par Internet.")
    if "hue" in f:
        ev.append("API Hue (/api/config)")
        return dict(kind="hue", driver="ha", type="light", name=f["hue"].get("name") or "Pont Hue", status="via_ha", evidence=ev, config={}, confirm=False,
                    label="Pont Philips Hue", hint="Ajoute-le dans Home Assistant (intégration Hue) : ses lampes apparaissent ensuite dans l'onglet Home Assistant.")
    for m in f.get("mdns") or []:
        t = m.get("type", "")
        if t in ("_ipp._tcp", "_printer._tcp", "_pdl-datastream._tcp", "_ipps._tcp"):
            ev.append(f"mDNS {t} : « {m.get('name')} »")
            return dict(kind="printer", driver="", type="other", name=m.get("name") or f"Imprimante {suffix}", status="ready", evidence=ev, config={}, confirm=False,
                        label=f"Imprimante {m.get('name') or ip}", printer={"uri": f"ipp://{ip}:631/ipp/print"})
        if t == "_hue._tcp":
            ev.append("mDNS _hue._tcp")
            return dict(kind="hue", driver="ha", type="light", name=m.get("name") or "Pont Hue", status="via_ha", evidence=ev, config={}, confirm=False,
                        label="Pont Philips Hue", hint="Ajoute-le dans Home Assistant (intégration Hue).")
        if t == "_home-assistant._tcp":
            ev.append("mDNS Home Assistant")
            return dict(kind="homeassistant", driver="ha", type="other", name="Home Assistant", status="info", evidence=ev, config={}, confirm=False,
                        label="Serveur Home Assistant", hint=f"Renseigne http://{ip}:8123 dans l'onglet Home Assistant pour récupérer tous ses appareils.")
        if t == "_googlecast._tcp":                         # Google Home, Nest, Chromecast : pilotés en direct (comme Jarvis)
            ev.append("mDNS _googlecast._tcp")
            nom = (m.get("props") or {}).get("fn") or m.get("name") or f"Enceinte {suffix}"
            return dict(kind="media", driver="cast", type="media", name=nom, status="ready", evidence=ev, confirm=False,
                        label=f"Google Cast « {nom} »", config={"ip": ip, "port": int(m.get("port") or 8009)})
        if t in ("_googlecast._tcp", "_airplay._tcp", "_raop._tcp", "_spotify-connect._tcp"):
            ev.append(f"mDNS {t}")
            return dict(kind="media", driver="ha", type="media", name=(m.get("props") or {}).get("fn") or m.get("name") or f"Média {suffix}", status="via_ha", evidence=ev, config={}, confirm=False,
                        label="TV / enceinte connectée", hint="Pilotable via Home Assistant (Google Cast, AirPlay…).")
    if "printer" in f:
        ev.append("Réponse IPP")
        return dict(kind="printer", driver="", type="other", name=f["printer"].get("model") or f"Imprimante {suffix}", status="ready", evidence=ev, config={}, confirm=False,
                    label=f"Imprimante {f['printer'].get('model') or ip}", printer={"uri": f["printer"]["uri"]})
    if 631 in ports or 9100 in ports:
        ev.append(f"Port imprimante ouvert ({631 if 631 in ports else 9100})")
        return dict(kind="printer", driver="", type="other", name=f"Imprimante {suffix}", status="ready", evidence=ev, config={}, confirm=False,
                    label=f"Imprimante ({ip})", printer={"uri": f"ipp://{ip}:631/ipp/print"})
    if s["mac"] and ports & {22, 445, 3389, 5900} and not (ports & {80, 443} and not ports & {445, 3389}):
        ev.append("Ports ordinateur ouverts : " + ", ".join(str(p) for p in sorted(ports & {22, 445, 3389, 5900})))
        nm = (s["hostname"].split(".")[0] if s["hostname"] else f"PC {suffix}")
        return dict(kind="computer", driver="wol", type="computer", name=nm, status="ready", evidence=ev, confirm=True, label=f"Ordinateur {nm} (à réveiller)",
                    config={"mac": s["mac"], "ip": ip})
    if 6668 in ports:
        ev.append("Port 6668 ouvert (Tuya)")
        return dict(kind="unknown", status="info", evidence=ev, name=f"Tuya {suffix}", config={}, driver="", type="other", confirm=False, label="Probablement Tuya",
                    hint="Appareil Tuya silencieux : éteint-le/rallume-le puis relance la recherche (il diffuse son identité à l'allumage).")
    if any(w in vendor.lower() for w in _ESP):
        ev.append(f"Puce {vendor}")
        return dict(kind="unknown", status="info", evidence=ev, name=f"Objet connecté {suffix}", config={}, driver="", type="other", confirm=False, label=f"Objet connecté ({vendor})",
                    hint="Puce Espressif : probablement une ampoule/prise (Tuya, Shelly, Tasmota…) qui ne s'est pas annoncée. Relance la recherche.")
    return dict(kind="unknown", status="info", evidence=ev, name=s["hostname"] or ip, config={}, driver="", type="other", confirm=False, label=s["hostname"] or ip)


# ── Recherche (tâche de fond avec état) ─────────────────────────────────────
async def get_settings() -> dict:
    return {**DEFAULTS, **(await _kv_get("home_disc") or {})}


async def set_settings(enabled: bool, interval_min: int = 30, cidr: str = "") -> dict:
    if cidr:
        from . import network
        network.check_private(cidr)
    cfg = {**await get_settings(), "enabled": bool(enabled), "interval_min": max(5, min(1440, int(interval_min or 30))), "cidr": cidr.strip()}
    await _kv_set("home_disc", cfg)
    return cfg


async def run_scan(quick: bool = False) -> dict:
    """Une recherche complète. Met à jour l'état, le résultat mémorisé, les adresses IP changées ; prévient Telegram des nouveautés."""
    from . import printing
    cfg = await get_settings()
    _state.update(running=True, started=time.time(), step="Écoute du réseau…", error="")
    try:
        scan, source, problem = await fetch_scan(quick, cfg["cidr"])
        _state["step"] = "Identification des appareils…"
        await devices.reload()
        ips = [h["ip"] for h in scan.get("hosts") or []] + [t["ip"] for k in ("tuya", "wiz", "yeelight", "kasa", "mdns") for t in scan.get(k) or []]
        ports = {h["ip"]: h.get("ports") or [] for h in scan.get("hosts") or []}
        sem = asyncio.Semaphore(12)
        known_special = {t["ip"] for k in ("tuya", "wiz", "yeelight", "kasa") for t in scan.get(k) or []}

        async def one(ip):
            if ip in known_special:
                return ip, {}
            async with sem:
                try:
                    fp = await fingerprint(ip, ports.get(ip) or [])
                    if not fp and ({631, 9100} & set(ports.get(ip) or [])):
                        p = await printer_fp(ip)
                        if p:
                            fp["printer"] = p
                    return ip, fp
                except Exception:  # noqa: BLE001
                    return ip, {}
        fps = dict(await asyncio.gather(*(one(ip) for ip in dict.fromkeys(ips))))
        printers = []
        try:
            printers = [p["uri"].split("//")[1].split(":")[0].split("/")[0] for p in await printing.list_printers()]
        except Exception:  # noqa: BLE001
            pass
        res = build_candidates(scan, fps, devices._cache, printers)
        for h in res["healed"]:
            await devices.set_ip(h["id"], h["new"])
        ignored = set(await _kv_get("home_disc_ignored") or [])
        seen = set(await _kv_get("home_disc_seen") or [])
        fresh = [c for c in res["candidates"] if not c["already"] and c["status"] in ("ready", "needs_key") and c["key"] not in ignored and c["key"] not in seen]
        out = {"at": time.time(), "source": source, "problem": problem, "took": scan.get("took", 0), "interfaces": scan.get("interfaces") or [],
               "cidrs": scan.get("cidrs") or [], "errors": scan.get("errors") or {}, "hosts": len(scan.get("hosts") or []), "healed": res["healed"],
               "candidates": res["candidates"], "others": res["others"]}
        await _kv_set("home_disc_result", out)
        await _kv_set("home_disc", {**cfg, "last_run": time.time()})
        if fresh:
            await _kv_set("home_disc_seen", sorted(seen | {c["key"] for c in fresh}))
            try:
                from . import telegram
                await telegram.notify("🏠 EVA a trouvé %d nouvel(s) appareil(s) :\n%s\nOuvre Maison › Appareils › Ajouter un appareil." % (len(fresh), "\n".join("• " + c["label"] + f" ({c['ip']})" for c in fresh[:10])))
            except Exception:  # noqa: BLE001
                pass
        return {"new": len(fresh), "healed": len(res["healed"]), "source": source}
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _state.update(running=False, finished=time.time(), step="")


def start_scan(quick: bool = False) -> dict:
    """Lance la recherche en arrière-plan (elle peut durer une minute) et rend la main tout de suite."""
    global _task
    if _task and not _task.done():
        return status_now()

    async def go():
        try:
            await asyncio.wait_for(run_scan(quick), 300)
        except Exception as exc:  # noqa: BLE001
            _state["error"] = _state["error"] or f"{type(exc).__name__}: {exc}"
    _state.update(running=True, started=time.time(), step="Démarrage…", error="")
    _task = asyncio.create_task(go())
    return status_now()


def status_now() -> dict:
    return dict(_state)


async def periodic() -> None:
    cfg = await get_settings()
    if not cfg["enabled"] or (_task and not _task.done()) or time.time() - float(cfg.get("last_run") or 0) < cfg["interval_min"] * 60:
        return
    start_scan(quick=True)


async def overview() -> dict:
    res = await _kv_get("home_disc_result") or {"candidates": [], "others": [], "healed": [], "at": 0, "source": "", "problem": "", "errors": {}, "interfaces": []}
    ignored = set(await _kv_get("home_disc_ignored") or [])
    await devices.reload()
    res = dict(res)
    res["candidates"] = [c for c in res["candidates"] if c["key"] not in ignored]
    res["ignored"] = len(ignored)
    return {"state": status_now(), "settings": await get_settings(), "result": res, "scanner": await scanner_health()}


async def ignore(key: str, undo: bool = False) -> dict:
    ign = set(await _kv_get("home_disc_ignored") or [])
    (ign.discard if undo else ign.add)(key)
    await _kv_set("home_disc_ignored", sorted(ign))
    return {"ignored": len(ign)}


async def reset_ignored() -> dict:
    await _kv_set("home_disc_ignored", [])
    return {"ignored": 0}


# ── Test et ajout ───────────────────────────────────────────────────────────
async def _candidate(key: str) -> dict:
    res = await _kv_get("home_disc_result") or {}
    for c in (res.get("candidates") or []) + (res.get("others") or []):
        if c["key"] == key:
            return c
    raise DiscoveryError("Appareil introuvable dans la dernière recherche : relance la recherche.")


async def _tuya_key(cand: dict, manual: str) -> str:
    if manual:
        return manual.strip()
    for d in devices._cache:                                  # appareil déjà importé : on réutilise sa clé
        if d["driver"] == "tuya" and (d["config"] or {}).get("device_id") == cand.get("device_id") and d["config"].get("local_key"):
            return d["config"]["local_key"]
    try:
        for x in await devices.tuya_cloud_devices():
            if x["device_id"] == cand.get("device_id"):
                return x.get("local_key") or ""
    except devices.DeviceError:
        pass
    return ""


async def _tuya_probe(cand: dict, key: str) -> dict:
    cfg = cand["config"]
    return await asyncio.to_thread(tuya_local.probe_sync, cfg["device_id"], cand["ip"], key, cfg.get("version", ""))


async def test(key: str, local_key: str = "") -> dict:
    """Essaie vraiment l'appareil (lecture seule : on demande son état)."""
    cand = await _candidate(key)
    if cand["kind"] == "tuya":
        k = await _tuya_key(cand, local_key)
        if not k:
            return {"ok": False, "need_key": True, "error": "Clé locale inconnue : renseigne ton compte Tuya cloud (Maison › Appareils › Tuya) ou colle la clé de cet appareil."}
        r = await _tuya_probe(cand, k)
        return {"ok": r["ok"], "error": r.get("error", ""), "details": r.get("details"), "info": f"protocole {r.get('version')} · {r.get('type')} (DP {r.get('switch_dp')})" if r["ok"] else ""}
    if cand["kind"] == "printer":
        p = await printer_fp(cand["ip"])
        return {"ok": bool(p), "error": "" if p else "L'imprimante ne répond pas en IPP.", "info": (p or {}).get("model", "")}
    if not cand.get("driver") or cand["status"] != "ready":
        return {"ok": False, "error": "Cet appareil ne se pilote pas directement par EVA.", "info": cand.get("hint", "")}
    if cand["kind"] == "computer":
        return {"ok": True, "info": "Réveil par Wake-on-LAN (pas de test possible sans le réveiller)."}
    try:
        st = await devices.run({"driver": cand["driver"], "config": cand["config"], "name": cand["name"], "type": cand["type"]}, "state", None)
        return {"ok": True, "info": json.dumps(st, ensure_ascii=False)[:200]}
    except devices.DeviceError as exc:
        return {"ok": False, "error": str(exc)}


async def add(key: str, name: str = "", room: str = "", dtype: str = "", local_key: str = "", force: bool = False) -> dict:
    """Ajoute un candidat trouvé par le serveur, après test. `force` = ajouter même si le test échoue."""
    from . import printing
    cand = await _candidate(key)
    if cand["already"] and not cand.get("link_device"):
        raise DiscoveryError("Cet appareil est déjà dans EVA.")
    name = " ".join((name or cand["name"]).split())[:60]
    if cand["kind"] == "printer":
        added = await printing.add_printer(name, cand["printer"]["uri"])
        await _refresh_result(printer_key=key)
        return {"ok": True, "kind": "printer", "added": added}
    if cand["status"] not in ("ready", "needs_key") or not cand.get("driver"):
        raise DiscoveryError(cand.get("hint") or "Cet appareil ne s'ajoute pas directement.")
    cfg = dict(cand["config"])
    if cand["mac"]:
        cfg.setdefault("mac", cand["mac"])
    typ = dtype or cand["type"]
    info = ""
    if cand["kind"] == "tuya":
        k = await _tuya_key(cand, local_key)
        if not k:
            return {"ok": False, "need_key": True, "error": "Clé locale inconnue : renseigne ton compte Tuya cloud ou colle la clé de cet appareil."}
        r = await _tuya_probe(cand, k)
        if not r["ok"] and not force:
            return {"ok": False, "error": r["error"], "details": r.get("details"), "can_force": True}
        cfg["local_key"] = k
        if r["ok"]:
            cfg.update(version=r["version"], switch_dp=r["switch_dp"])
            typ = dtype or r["type"]
            info = f"protocole {r['version']}, DP {r['switch_dp']}"
        if cand.get("link_device"):
            dev = next((d for d in devices._cache if d["id"] == cand["link_device"]), None)
            if dev:
                merged = {**dev["config"], **cfg}
                saved = await devices.save(dev["id"], dev["name"], dev["room"], dev["type"], "tuya", merged, dev["aliases"], dev["confirm"])
                return {"ok": True, "kind": "tuya", "device": saved, "info": info + " — passé en mode local"}
    else:
        t = await test(key)
        if not t["ok"] and not force and cand["kind"] != "computer":
            return {"ok": False, "error": t.get("error") or "L'appareil ne répond pas.", "can_force": True}
    confirm = bool(cand.get("confirm")) or typ in devices.CONFIRM_TYPES
    nm = name
    taken = {d["name"].lower() for d in devices._cache}
    if nm.lower() in taken:
        nm = f"{nm} {cand['ip'].split('.')[-1]}"
    saved = await devices.save(None, nm, room, typ, cand["driver"], cfg, "", confirm)
    await _kv_set("home_disc_seen", sorted(set(await _kv_get("home_disc_seen") or []) | {key}))
    await _refresh_result()
    return {"ok": True, "kind": cand["kind"], "device": saved, "info": info}


async def _refresh_result(printer_key: str = "") -> None:
    """Marque comme « déjà ajoutés » les candidats qui le sont maintenant, sans relancer de recherche."""
    res = await _kv_get("home_disc_result")
    if not res:
        return
    await devices.reload()
    idx = _have(devices._cache)
    for c in res["candidates"]:
        if printer_key and c["key"] == printer_key:
            c["already"] = True
        dev = (idx["tuya"].get(c.get("device_id", "")) if c["kind"] == "tuya" else None) or (idx["mac"].get(c["mac"]) if c["mac"] else None) or idx["ip"].get(c["ip"])
        if dev and c["kind"] != "printer":
            c["already"], c["device_name"] = dev["id"], dev["name"]
            c.pop("link_device", None)
    await _kv_set("home_disc_result", res)


async def repair_ip(dev_id: int) -> dict:
    """Relance une recherche rapide et corrige l'adresse IP de cet appareil si elle a changé."""
    await devices.reload()
    dev = next((d for d in devices._cache if d["id"] == dev_id), None)
    if not dev:
        raise DiscoveryError("Appareil introuvable.")
    before = (dev["config"] or {}).get("ip", "")
    await run_scan(quick=True)
    await devices.reload()
    dev = next((d for d in devices._cache if d["id"] == dev_id), None)
    now = (dev["config"] or {}).get("ip", "")
    return {"changed": now != before, "old": before, "new": now}
