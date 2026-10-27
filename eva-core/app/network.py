"""Analyse du réseau local et accès aux machines — pour l'administration de TON réseau.

- Détection : balayage TCP des adresses privées (ports courants), noms, constructeur ; mode « approfondi » avec nmap
  (conteneur Docker en réseau hôte : adresses MAC et constructeurs).
- Machines enregistrées : accès SSH (souvent en root) avec les identifiants que tu fournis. L'empreinte de la machine est mémorisée
  à la première connexion ; si elle change, EVA refuse (protection contre l'usurpation).
- Garde-fous : seulement des adresses privées (jamais Internet, jamais 169.254.x), 1024 adresses au plus par analyse, aucune
  tentative de deviner des mots de passe, chaque commande SSH est tracée dans le journal d'accès."""
import asyncio
import ipaddress
import json
import re
import socket
import time
import xml.etree.ElementTree as ET

import httpx

from .db import get_pool
from .lists import norm

PORTS = {22: "ssh", 23: "telnet", 53: "dns", 80: "http", 139: "netbios", 443: "https", 445: "smb", 515: "lpd", 554: "rtsp", 631: "ipp", 1883: "mqtt",
         3389: "rdp", 5000: "http-alt", 5900: "vnc", 6668: "tuya", 8000: "http-alt", 8080: "http-alt", 8123: "home-assistant", 8443: "https-alt",
         9100: "imprimante", 32400: "plex", 62078: "apple"}
MAX_HOSTS = 1024
OUT_MAX = 8000
INSPECT = [
    ("Système", "uname -a; cat /etc/os-release 2>/dev/null | head -3; uptime"),
    ("Disques", "df -h 2>/dev/null | head -20"),
    ("Mémoire", "free -m 2>/dev/null"),
    ("Réseau", "ip -br addr 2>/dev/null || ifconfig 2>/dev/null | head -30"),
    ("Ports à l'écoute", "ss -tulpn 2>/dev/null | head -40 || netstat -tulpn 2>/dev/null | head -40"),
    ("Processus gourmands", "ps aux --sort=-%mem 2>/dev/null | head -8"),
    ("Dernières connexions", "last -n 8 2>/dev/null"),
    ("Services en échec", "systemctl --failed --no-legend 2>/dev/null | head -10"),
    ("Docker", "docker ps --format '{{.Names}}  {{.Status}}' 2>/dev/null | head -20"),
]
# Préfixes MAC (OUI) courants — liste volontairement courte ; nmap fournit la liste complète en mode approfondi.
OUI = {"B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi", "E4:5F:01": "Raspberry Pi", "D8:3A:DD": "Raspberry Pi", "00:11:32": "Synology", "00:50:43": "Marvell",
       "24:0A:C4": "Espressif (Tuya/Shelly/ESP)", "30:AE:A4": "Espressif (Tuya/Shelly/ESP)", "84:CC:A8": "Espressif (Tuya/Shelly/ESP)", "A4:CF:12": "Espressif (Tuya/Shelly/ESP)",
       "BC:DD:C2": "Espressif (Tuya/Shelly/ESP)", "68:C6:3A": "Espressif (Tuya/Shelly/ESP)", "10:D5:61": "Tuya", "D8:1F:12": "Tuya", "7C:F6:66": "Tuya",
       "F0:18:98": "Apple", "3C:22:FB": "Apple", "A4:83:E7": "Apple", "FC:FC:48": "Apple", "00:17:88": "Philips Hue", "EC:B5:FA": "Philips Hue",
       "18:B4:30": "Google Nest", "F4:F5:D8": "Google", "44:07:0B": "Google", "74:C2:46": "Amazon", "F0:F0:A4": "Amazon", "FC:65:DE": "Amazon", "50:DC:E7": "Amazon",
       "00:1A:11": "Google", "AC:84:C6": "TP-Link", "50:C7:BF": "TP-Link", "98:DA:C4": "TP-Link", "FC:EC:DA": "Ubiquiti", "24:5A:4C": "Ubiquiti", "00:24:E4": "Withings",
       "5C:CF:7F": "Espressif", "18:FE:34": "Espressif", "00:0C:29": "VMware", "52:54:00": "QEMU/KVM", "02:42:AC": "Docker", "B0:BE:76": "TP-Link", "28:6C:07": "Xiaomi",
       "64:09:80": "Xiaomi", "78:11:DC": "Xiaomi", "F8:A2:D6": "Samsung", "CC:07:AB": "Samsung", "00:E0:4C": "Realtek", "00:15:5D": "Hyper-V", "00:1E:C0": "Microchip"}


class NetError(RuntimeError):
    pass


def check_private(addr: str) -> ipaddress._BaseAddress | ipaddress._BaseNetwork:
    """Adresse ou plage privée uniquement (réseau local)."""
    try:
        net = ipaddress.ip_network(addr.strip(), strict=False)
    except ValueError as exc:
        raise NetError(f"Adresse invalide : {addr}") from exc
    if not (net.is_private or net.is_loopback) or net.is_link_local or net.is_multicast:
        raise NetError("Seules les adresses du réseau local (privées) sont autorisées.")
    if net.num_addresses > MAX_HOSTS:
        raise NetError(f"Plage trop large ({net.num_addresses} adresses, {MAX_HOSTS} maximum : un /22).")
    return net


async def resolve_host(host: str) -> str:
    """Nom ou IP → IP privée."""
    try:
        ip = str(ipaddress.ip_address(host.strip()))
    except ValueError:
        try:
            ip = (await asyncio.get_running_loop().getaddrinfo(host.strip(), None, family=socket.AF_INET))[0][4][0]
        except OSError as exc:
            raise NetError(f"Nom introuvable : {host}") from exc
    check_private(ip)
    return ip


# ------------------------------------------------------------------ analyse
async def _probe(ip: str, ports, timeout: float = 0.5) -> list[int] | None:
    """Ports ouverts ([] = répond sans port ouvert ; None = pas de réponse)."""
    alive, opened = False, []
    for p in ports:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(ip, p), timeout)
            w.close(); opened.append(p); alive = True
        except ConnectionRefusedError:
            alive = True
        except Exception:  # noqa: BLE001
            pass
    return opened if alive else None


from concurrent.futures import ThreadPoolExecutor
_RDNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eva-rdns")   # à part : une résolution inverse lente ne doit jamais bloquer le reste d'EVA


async def _rdns(ip: str) -> str:
    try:
        return (await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(_RDNS_POOL, socket.gethostbyaddr, ip), 1.0))[0]
    except Exception:  # noqa: BLE001
        return ""


def _arp_table() -> dict[str, str]:
    try:
        rows = open("/proc/net/arp").read().splitlines()[1:]
    except OSError:
        return {}
    return {r.split()[0]: r.split()[3].upper() for r in rows if len(r.split()) >= 4 and r.split()[3] != "00:00:00:00:00:00"}


def vendor(mac: str) -> str:
    return OUI.get((mac or "").upper()[:8], "")


async def sweep(net) -> list[dict]:
    ips = [str(h) for h in (net.hosts() if net.num_addresses > 2 else net)]
    sem = asyncio.Semaphore(64)

    async def one(ip):
        async with sem:
            ports = await _probe(ip, sorted(PORTS))
            if ports is None:
                return None
            return {"ip": ip, "ports": [{"port": p, "service": PORTS[p]} for p in ports], "hostname": await _rdns(ip)}
    found = [h for h in await asyncio.gather(*(one(i) for i in ips)) if h]
    arp = _arp_table()
    for h in found:
        h["mac"] = arp.get(h["ip"], "")
        h["vendor"] = vendor(h["mac"])
    return found


def parse_nmap(xml_text: str) -> list[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for h in root.findall("host"):
        if (h.find("status") is not None) and h.find("status").get("state") != "up":
            continue
        ip = mac = ven = ""
        for a in h.findall("address"):
            if a.get("addrtype") == "ipv4":
                ip = a.get("addr", "")
            elif a.get("addrtype") == "mac":
                mac, ven = a.get("addr", "").upper(), a.get("vendor", "")
        name = next((n.get("name", "") for n in h.findall("hostnames/hostname")), "")
        ports = [{"port": int(p.get("portid")), "service": (p.find("service").get("name") if p.find("service") is not None else PORTS.get(int(p.get("portid")), ""))}
                 for p in h.findall("ports/port") if p.find("state") is not None and p.find("state").get("state") == "open"]
        osm = next((m.get("name", "") for m in h.findall("os/osmatch")), "")
        if ip:
            out.append({"ip": ip, "mac": mac, "vendor": ven or vendor(mac), "hostname": name, "ports": ports, "os": osm})
    return out


def _nmap_docker(cidr: str) -> str:
    import docker
    cl = docker.from_env()
    try:
        cl.images.get("instrumentisto/nmap")
    except Exception:  # noqa: BLE001
        raise NetError("Analyse approfondie : l'image « instrumentisto/nmap » n'est pas installée. Sur le NAS : docker pull instrumentisto/nmap") from None
    out = cl.containers.run("instrumentisto/nmap", ["-T4", "-F", "--open", "-O", "--osscan-limit", "-oX", "-", cidr], network_mode="host",
                            cap_add=["NET_RAW", "NET_ADMIN"], remove=True, stdout=True, stderr=False, mem_limit="256m")
    return out.decode("utf-8", errors="replace")


async def scan(cidr: str, deep: bool = False) -> dict:
    net = check_private(cidr)
    if net.num_addresses == 1:
        net = ipaddress.ip_network(f"{net.network_address}/32")
    if deep:
        xml_text = await asyncio.to_thread(_nmap_docker, str(net))
        hosts = parse_nmap(xml_text)
    else:
        hosts = await sweep(net)
    hosts = await _annotate(hosts)
    res = {"cidr": str(net), "deep": deep, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "hosts": hosts}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('net_scan', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(res))
    return res


async def _annotate(hosts: list[dict]) -> list[dict]:
    """Ajoute le nom connu (machine SSH enregistrée, appareil de la maison) à chaque adresse."""
    from . import devices
    known: dict[str, str] = {}
    for h in await list_hosts():
        known[h["address"]] = f"{h['name']} (SSH)"
    for d in devices._cache:
        ip = d["config"].get("ip")
        if ip:
            known.setdefault(ip, f"{d['name']} ({d['room'] or 'maison'})")
    for h in hosts:
        h["known_as"] = known.get(h["ip"], "")
    return sorted(hosts, key=lambda h: ipaddress.ip_address(h["ip"]))


async def last_scan() -> dict | None:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='net_scan'")
    return (json.loads(raw) if isinstance(raw, str) else raw) if raw else None


async def probe_ports(host: str, ports: list[int]) -> dict:
    ip = await resolve_host(host)
    ports = sorted({int(p) for p in ports if 0 < int(p) < 65536})[:30] or sorted(PORTS)
    opened = await _probe(ip, ports, 0.8)
    return {"ip": ip, "up": opened is not None, "open": [{"port": p, "service": PORTS.get(p, "")} for p in (opened or [])]}


# ------------------------------------------------------------------ HTTP local
async def lan_http(method: str, url: str, body: str = "") -> dict:
    """Parle à l'API HTTP d'un appareil du réseau local (adresses privées seulement, pas de redirection)."""
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise NetError("URL invalide.")
    await resolve_host(p.hostname)
    method = method.upper()
    if method not in ("GET", "POST", "PUT"):
        raise NetError("Méthodes autorisées : GET, POST, PUT.")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, verify=False) as c:
            r = await c.request(method, url, content=body.encode() if body else None)
    except httpx.HTTPError as exc:
        raise NetError(f"Appareil injoignable : {exc}") from exc
    return {"status": r.status_code, "content_type": r.headers.get("content-type", ""), "body": r.text[:OUT_MAX]}


# ------------------------------------------------------------------ machines SSH enregistrées
def _pub(r) -> dict:
    return {"id": r["id"], "name": r["name"], "address": r["address"], "port": r["port"], "username": r["username"], "auth": r["auth"],
            "has_secret": bool(r["secret"]), "host_key": r["host_key"], "notes": r["notes"]}


async def list_hosts() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, name, address, port, username, auth, secret, host_key, notes FROM net_hosts ORDER BY name")
    return [_pub(r) for r in rows]


async def save_host(host_id: int | None, name: str, address: str, port: int, username: str, auth: str, secret: str, notes: str = "") -> dict:
    name = " ".join((name or "").split())[:60]
    if not name:
        raise NetError("Donne un nom à la machine.")
    ip = await resolve_host(address)
    if auth not in ("password", "key"):
        raise NetError("Authentification : mot de passe ou clé privée.")
    if not (0 < int(port) < 65536):
        raise NetError("Port invalide.")
    username = (username or "root").strip()[:40]
    async with get_pool().acquire() as conn:
        try:
            if host_id:
                old = await conn.fetchrow("SELECT secret, address, host_key FROM net_hosts WHERE id=$1", host_id)
                if old is None:
                    raise NetError("Machine introuvable.")
                sec = old["secret"] if secret in ("", "••••") else secret
                hk = old["host_key"] if old["address"] == address.strip() else ""     # nouvelle adresse = nouvelle empreinte
                await conn.execute("UPDATE net_hosts SET name=$2,address=$3,port=$4,username=$5,auth=$6,secret=$7,host_key=$8,notes=$9 WHERE id=$1",
                                   host_id, name, address.strip(), int(port), username, auth, sec, hk, notes[:300])
            else:
                if not secret:
                    raise NetError("Mot de passe ou clé privée obligatoire.")
                host_id = await conn.fetchval("INSERT INTO net_hosts (name,address,port,username,auth,secret,notes) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
                                              name, address.strip(), int(port), username, auth, secret, notes[:300])
        except NetError:
            raise
        except Exception as exc:  # noqa: BLE001
            if "unique" in str(exc).lower():
                raise NetError("Une machine porte déjà ce nom.") from exc
            raise
    return next(h for h in await list_hosts() if h["id"] == host_id)


async def delete_host(host_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM net_hosts WHERE id=$1", host_id)


async def forget_key(host_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE net_hosts SET host_key='' WHERE id=$1", host_id)


async def _get_host(name: str) -> dict:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM net_hosts")
    q = norm(name)
    hits = [r for r in rows if norm(r["name"]) == q] or [r for r in rows if q and (q in norm(r["name"]) or q == norm(r["address"]))]
    if len(hits) != 1:
        raise NetError(f"Machine « {name} » introuvable ou ambiguë. Enregistrées : {', '.join(r['name'] for r in rows) or 'aucune'}.")
    return dict(hits[0])


async def _ssh_exec(h: dict, command: str, timeout: int) -> tuple[int, str, str, str]:
    """Seul point d'accès SSH (remplaçable dans les tests). → (code retour, sortie, erreurs, empreinte)."""
    import asyncssh
    kw: dict = {"known_hosts": None, "connect_timeout": 10, "username": h["username"], "port": h["port"]}
    if h["auth"] == "key":
        try:
            kw["client_keys"] = [asyncssh.import_private_key(h["secret"])]
        except (asyncssh.KeyImportError, ValueError) as exc:
            raise NetError("Clé privée illisible (format OpenSSH/PEM sans phrase secrète).") from exc
    else:
        kw["password"] = h["secret"]
        kw["client_keys"] = None
    try:
        async with asyncssh.connect(h["address"], **kw) as conn:
            fp = conn.get_server_host_key().get_fingerprint()
            if h["host_key"] and h["host_key"] != fp:
                raise NetError("L'empreinte SSH de la machine a CHANGÉ (réinstallation ou usurpation ?). Connexion refusée ; "
                               "si c'est normal, oublie l'empreinte dans Maison › Réseau.")
            r = await asyncio.wait_for(conn.run(command, check=False), timeout)
            return r.exit_status or 0, str(r.stdout or ""), str(r.stderr or ""), fp
    except asyncssh.PermissionDenied as exc:
        raise NetError("Accès refusé (identifiant ou mot de passe/clé incorrect).") from exc
    except asyncio.TimeoutError as exc:
        raise NetError(f"Commande trop longue (plus de {timeout} s).") from exc
    except (OSError, asyncssh.Error) as exc:
        raise NetError(f"Connexion SSH impossible : {exc}") from exc


async def ssh_run(name: str, command: str, timeout: int = 60) -> dict:
    from . import auth
    if not (command or "").strip():
        raise NetError("Commande vide.")
    h = await _get_host(name)
    await resolve_host(h["address"])
    await auth.audit("ssh", "eva", h["address"], f"SSH {h['username']}@{h['name']}", command[:300], 0)
    code, out, err, fp = await _ssh_exec(h, command, max(1, min(int(timeout), 120)))
    if not h["host_key"]:
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE net_hosts SET host_key=$2 WHERE id=$1", h["id"], fp)
    return {"host": h["name"], "exit": code, "stdout": out[:OUT_MAX], "stderr": err[:2000], "truncated": len(out) > OUT_MAX}


async def inspect(name: str) -> dict:
    """Inspection en lecture seule : une série de commandes d'état."""
    script = "; ".join(f"echo '=== {t} ==='; {c}" for t, c in INSPECT)
    r = await ssh_run(name, script, 60)
    sections, cur = {}, None
    for line in r["stdout"].splitlines():
        m = re.fullmatch(r"=== (.+) ===", line)
        if m:
            cur = m.group(1); sections[cur] = []
        elif cur:
            sections[cur].append(line)
    return {"host": r["host"], "sections": {k: "\n".join(v).strip() for k, v in sections.items()}, "exit": r["exit"]}


# ------------------------------------------------------------------ reconnaissance et ajout automatique
