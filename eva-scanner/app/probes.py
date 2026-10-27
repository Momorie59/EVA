"""Sondes réseau de l'éclaireur : tout ce qui demande de VOIR le réseau local (diffusions, ARP, multicast).
Chaque sonde est indépendante : si l'une échoue, les autres répondent quand même (l'erreur est rapportée)."""
import asyncio
import ipaddress
import json
import re
import socket
import struct
import time
from urllib.parse import urlparse

import httpx
import psutil

SKIP_IFACE = re.compile(r"^(lo|docker|br-|veth|virbr|tun|tap|wg|zt|tailscale|vmnet|cni|flannel|kube)", re.I)


# ------------------------------------------------------------------ interfaces et ARP
def interfaces() -> list[dict]:
    """Réseaux privés directement joints (jamais plus grands qu'un /24 : on ne balaie pas 65 000 adresses)."""
    out = []
    for name, addrs in psutil.net_if_addrs().items():
        if SKIP_IFACE.match(name):
            continue
        for a in addrs:
            if a.family != socket.AF_INET or not a.netmask:
                continue
            try:
                ip = ipaddress.ip_address(a.address)
                if not ip.is_private or ip.is_loopback or ip.is_link_local:
                    continue
                net = ipaddress.ip_network(f"{a.address}/{a.netmask}", strict=False)
                if net.prefixlen < 24:
                    net = ipaddress.ip_network(f"{a.address}/24", strict=False)
                out.append({"iface": name, "ip": a.address, "cidr": str(net)})
            except ValueError:
                continue
    return out


def parse_arp(text: str) -> dict[str, dict]:
    """Contenu de /proc/net/arp -> {ip: {mac, iface}} (entrées complètes uniquement)."""
    res = {}
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) >= 6 and p[3] != "00:00:00:00:00:00" and int(p[2], 16) & 0x2:
            res[p[0]] = {"mac": p[3].upper(), "iface": p[5]}
    return res


async def arp_sweep(cidr: str, settle: float = 1.5) -> list[dict]:
    """Réveille chaque adresse (un datagramme UDP force la résolution ARP du noyau) puis lit la table ARP : MAC réelles."""
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = [str(h) for h in net.hosts()][:1024]
    loop = asyncio.get_running_loop()

    def poke():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setblocking(False)
        for ip in hosts:
            try:
                s.sendto(b"\x00", (ip, 9))
            except OSError:
                pass
        s.close()
    await loop.run_in_executor(None, poke)
    await asyncio.sleep(settle)
    try:
        table = parse_arp(open("/proc/net/arp").read())
    except OSError:
        table = {}
    inside = {ip for ip in hosts}
    return [{"ip": ip, "mac": v["mac"], "iface": v["iface"]} for ip, v in table.items() if ip in inside]


# ------------------------------------------------------------------ mDNS (Bonjour)
MDNS_TYPES = ["_http._tcp.local.", "_hap._tcp.local.", "_shelly._tcp.local.", "_hue._tcp.local.", "_googlecast._tcp.local.",
              "_ipp._tcp.local.", "_printer._tcp.local.", "_home-assistant._tcp.local.", "_esphomelib._tcp.local.",
              "_wled._tcp.local.", "_ewelink._tcp.local.", "_matter._tcp.local.", "_matterc._udp.local.", "_airplay._tcp.local.",
              "_raop._tcp.local.", "_spotify-connect._tcp.local.", "_arduino._tcp.local.", "_miio._udp.local.", "_tasmota._tcp.local.",
              "_workstation._tcp.local.", "_smb._tcp.local.", "_ssh._tcp.local.", "_services._dns-sd._udp.local."]


async def mdns(timeout: float = 5.0) -> list[dict]:
    """Annonces Bonjour/mDNS : type de service, nom, adresse, port, propriétés (modèle, identifiant…)."""
    from zeroconf import ServiceBrowser, ServiceStateChange
    from zeroconf.asyncio import AsyncZeroconf
    found: dict[str, dict] = {}
    browsers: list = []
    seen_types: set[str] = set(MDNS_TYPES)
    aiozc = AsyncZeroconf()
    zc = aiozc.zeroconf

    def handler(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Removed:
            return
        if service_type == "_services._dns-sd._udp.local.":
            if name not in seen_types:                              # type de service inconnu de notre liste : on l'écoute aussi
                seen_types.add(name)
                browsers.append(ServiceBrowser(zc, name, handlers=[handler]))
            return
        found[name] = {"name": name, "type": service_type}

    try:
        for t in MDNS_TYPES:
            browsers.append(ServiceBrowser(zc, t, handlers=[handler]))
        await asyncio.sleep(timeout)
        out = []
        for name, info in list(found.items()):
            try:
                si = await aiozc.async_get_service_info(info["type"], name, timeout=1500)
            except Exception:  # noqa: BLE001
                si = None
            if not si:
                continue
            props = {}
            for k, v in (si.properties or {}).items():
                try:
                    props[k.decode()] = v.decode(errors="replace") if isinstance(v, bytes) else v
                except Exception:  # noqa: BLE001
                    pass
            for addr in si.parsed_addresses():
                if ":" in addr:
                    continue
                out.append({"ip": addr, "name": name.split("._")[0], "type": info["type"].replace(".local.", "").strip("."),
                            "port": si.port, "server": (si.server or "").rstrip("."), "props": dict(list(props.items())[:25])})
        return out
    finally:
        for b in browsers:
            try:
                b.cancel()
            except Exception:  # noqa: BLE001
                pass
        await aiozc.async_close()


# ------------------------------------------------------------------ SSDP / UPnP
def parse_ssdp(data: bytes) -> dict:
    head = data.decode("utf-8", errors="replace").split("\r\n")
    h = {}
    for line in head[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            h[k.strip().lower()] = v.strip()
    return h


async def _udp_collect(payload: bytes, targets: list[tuple[str, int]], timeout: float, bind_ip: str = "", port: int = 0, ttl: int = 2) -> list[tuple[bytes, tuple[str, int]]]:
    """Envoie `payload` à chaque cible (diffusion/multicast compris) et recueille toutes les réponses pendant `timeout`."""
    loop = asyncio.get_running_loop()
    got: list[tuple[bytes, tuple[str, int]]] = []

    class P(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr): got.append((data, addr))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    sock.bind((bind_ip, port))
    sock.setblocking(False)
    transport, _ = await loop.create_datagram_endpoint(P, sock=sock)
    try:
        for t in targets:
            try:
                transport.sendto(payload, t)
            except OSError:
                pass
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return got


async def ssdp(ifaces: list[dict], timeout: float = 3.0, describe: bool = True) -> list[dict]:
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    res: dict[str, dict] = {}
    for itf in ifaces or [{"ip": ""}]:
        for data, (ip, _) in await _udp_collect(msg, [("239.255.255.250", 1900)], timeout, bind_ip=itf["ip"]):
            h = parse_ssdp(data)
            e = res.setdefault(ip, {"ip": ip, "st": set(), "server": h.get("server", ""), "location": h.get("location", "")})
            if h.get("st") or h.get("nt"):
                e["st"].add(h.get("st") or h.get("nt"))
            e["location"] = e["location"] or h.get("location", "")
    out = []
    async with httpx.AsyncClient(timeout=2.0) as c:
        async def desc(e):
            e["st"] = sorted(e["st"])[:12]
            if describe and e["location"].startswith("http"):
                try:
                    host = urlparse(e["location"]).hostname
                    if host == e["ip"]:                                    # on ne suit jamais un lien vers une autre machine
                        x = (await c.get(e["location"])).text[:60000]
                        for tag in ("friendlyName", "manufacturer", "modelName", "modelNumber", "deviceType"):
                            m = re.search(rf"<{tag}>([^<]*)</{tag}>", x)
                            if m:
                                e[tag] = m.group(1).strip()[:80]
                except Exception:  # noqa: BLE001
                    pass
            return e
        out = await asyncio.gather(*(desc(e) for e in res.values()))
    return list(out)


# ------------------------------------------------------------------ Tuya (diffusions UDP 6666/6667/7000)
def decode_tuya(data: bytes, addr_ip: str) -> dict | None:
    try:
        from tinytuya.core import decrypt_udp
        txt = decrypt_udp(data)
        j = json.loads(txt)
    except Exception:  # noqa: BLE001
        m = re.search(rb"\{.*\}", data, re.S)
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
        except ValueError:
            return None
    if not isinstance(j, dict) or not (j.get("gwId") or j.get("id")):
        return None
    return {"ip": j.get("ip") or addr_ip, "gwId": j.get("gwId") or j.get("id"), "version": str(j.get("version") or ""),
            "productKey": j.get("productKey", ""), "active": j.get("active"), "encrypt": j.get("encrypt")}


async def tuya(timeout: float = 8.0, ports=(6666, 6667)) -> list[dict]:
    loop = asyncio.get_running_loop()
    found: dict[str, dict] = {}
    transports = []

    class P(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            d = decode_tuya(data, addr[0])
            if d:
                found[d["gwId"]] = d

    errs = []
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(("", port)); s.setblocking(False)
            tr, _ = await loop.create_datagram_endpoint(P, sock=s)
            transports.append(tr)
        except OSError as exc:
            s.close(); errs.append(f"port {port} : {exc}")
    try:
        await asyncio.sleep(timeout)
    finally:
        for t in transports:
            t.close()
    if errs and not transports:
        raise OSError("; ".join(errs))
    return list(found.values())


# ------------------------------------------------------------------ WiZ
async def wiz(timeout: float = 2.0, broadcast: list[str] | None = None, port: int = 38899) -> list[dict]:
    msg = json.dumps({"method": "getPilot", "params": {}}).encode()
    out = {}
    for data, (ip, _) in await _udp_collect(msg, [(b, port) for b in (broadcast or ["255.255.255.255"])], timeout):
        try:
            r = json.loads(data).get("result") or {}
            out[ip] = {"ip": ip, "mac": (r.get("mac") or "").upper(), "state": r.get("state"), "dimming": r.get("dimming"), "module": r.get("moduleName", "")}
        except ValueError:
            pass
    return list(out.values())


# ------------------------------------------------------------------ Yeelight
def parse_yeelight(data: bytes, addr_ip: str) -> dict | None:
    h = parse_ssdp(data)
    loc = h.get("location", "")
    if not loc.startswith("yeelight://"):
        return None
    u = urlparse(loc)
    return {"ip": u.hostname or addr_ip, "port": u.port or 55443, "id": h.get("id", ""), "model": h.get("model", ""), "name": h.get("name", ""),
            "power": h.get("power", ""), "support": h.get("support", "")}


async def yeelight(timeout: float = 2.5, targets=None) -> list[dict]:
    msg = b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1982\r\nMAN: \"ssdp:discover\"\r\nST: wifi_bulb\r\n\r\n"
    out = {}
    for data, (ip, _) in await _udp_collect(msg, targets or [("239.255.255.250", 1982)], timeout):
        d = parse_yeelight(data, ip)
        if d:
            out[d["ip"]] = d
    return list(out.values())


# ------------------------------------------------------------------ TP-Link Kasa (ancien protocole)
def kasa_encrypt(text: str) -> bytes:
    key, out = 171, bytearray()
    for ch in text.encode():
        key = key ^ ch
        out.append(key)
    return bytes(out)


def kasa_decrypt(data: bytes) -> str:
    key, out = 171, bytearray()
    for b in data:
        out.append(key ^ b)
        key = b
    return out.decode(errors="replace")


async def kasa(timeout: float = 2.0, broadcast: list[str] | None = None, port: int = 9999) -> list[dict]:
    msg = kasa_encrypt('{"system":{"get_sysinfo":{}}}')
    out = {}
    for data, (ip, _) in await _udp_collect(msg, [(b, port) for b in (broadcast or ["255.255.255.255"])], timeout):
        try:
            si = json.loads(kasa_decrypt(data))["system"]["get_sysinfo"]
            out[ip] = {"ip": ip, "alias": si.get("alias", ""), "model": si.get("model", ""), "mac": (si.get("mac") or si.get("mic_mac") or "").upper().replace("-", ":"),
                       "kind": "bulb" if "light_state" in si or "KL" in str(si.get("model", "")) else "plug", "relay_state": si.get("relay_state"),
                       "children": len(si.get("children") or [])}
        except (ValueError, KeyError):
            pass
    return list(out.values())


# ------------------------------------------------------------------ orchestration
async def run_all(cidrs: list[str] | None = None, quick: bool = False) -> dict:
    t0 = time.time()
    ifs = interfaces()
    targets = cidrs or [i["cidr"] for i in ifs]
    errors: dict[str, str] = {}
    wait = 3.0 if quick else 8.0

    async def safe(name, coro):
        try:
            return await asyncio.wait_for(coro, 40)
        except Exception as exc:  # noqa: BLE001
            errors[name] = f"{type(exc).__name__}: {exc}"
            return []

    async def arp_all():
        res = []
        for c in dict.fromkeys(targets):
            res += await arp_sweep(c)
        return res
    hosts, md, ss, tu, wz, ye, ka = await asyncio.gather(
        safe("arp", arp_all()), safe("mdns", mdns(3.0 if quick else 5.0)), safe("ssdp", ssdp(ifs, 3.0)),
        safe("tuya", tuya(wait)), safe("wiz", wiz()), safe("yeelight", yeelight()), safe("kasa", kasa()))
    return {"interfaces": ifs, "cidrs": targets, "hosts": hosts, "mdns": md, "ssdp": ss, "tuya": tu, "wiz": wz, "yeelight": ye, "kasa": ka,
            "errors": errors, "took": round(time.time() - t0, 1)}
