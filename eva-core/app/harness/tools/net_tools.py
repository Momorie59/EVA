from typing import Any

from ... import network
from ..permissions import Permission
from .base import Tool


def _err(exc: Exception) -> dict:
    return {"error": str(exc)}


class NetHostsTool(Tool):
    name = "net_hosts"
    description = "Montre le dernier résultat d'analyse du réseau (adresses, noms, constructeurs, ports ouverts) et les machines SSH enregistrées. Ne scanne rien."
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        last = await network.last_scan()
        return {"registered": [{"name": h["name"], "address": h["address"], "user": h["username"]} for h in await network.list_hosts()],
                "last_scan": ({"at": last["at"], "cidr": last["cidr"], "hosts": [
                    {"ip": h["ip"], "name": h.get("known_as") or h.get("hostname") or "", "vendor": h.get("vendor", ""), "mac": h.get("mac", ""),
                     "ports": [p["service"] or p["port"] for p in h["ports"]]} for h in last["hosts"]]} if last else None)}


class NetScanTool(Tool):
    name = "net_scan"
    description = ("Analyse le réseau local pour lister les appareils connectés (adresse, nom, constructeur, ports ouverts). cidr ex. 192.168.1.0/24. "
                   "deep=true : analyse approfondie avec nmap (adresses MAC, système). Réseau privé uniquement ; soumis à l'accord de l'utilisateur.")
    parameters = {"type": "object", "properties": {"cidr": {"type": "string"}, "deep": {"type": "boolean"}}, "required": []}
    permission = Permission.CONFIRM

    async def execute(self, cidr: str = "", deep: bool = False, **_: Any) -> dict:
        from ...printing import default_cidr
        try:
            r = await network.scan(cidr or default_cidr(), bool(deep))
        except network.NetError as exc:
            return _err(exc)
        return {"cidr": r["cidr"], "count": len(r["hosts"]), "hosts": [
            {"ip": h["ip"], "name": h.get("known_as") or h.get("hostname") or "", "vendor": h.get("vendor", ""), "mac": h.get("mac", ""),
             "ports": [p["service"] or p["port"] for p in h["ports"]]} for h in r["hosts"]]}


class NetProbeTool(Tool):
    name = "net_probe"
    description = "Teste si une machine du réseau local répond et quels ports sont ouverts (liste de ports facultative). Adresse privée uniquement."
    parameters = {"type": "object", "properties": {"host": {"type": "string"}, "ports": {"type": "array", "items": {"type": "integer"}}}, "required": ["host"]}
    permission = Permission.AUTO

    async def execute(self, host: str = "", ports: Any = None, **_: Any) -> dict:
        try:
            return await network.probe_ports(host, ports if isinstance(ports, list) else [])
        except (network.NetError, ValueError) as exc:
            return _err(exc)


class NetHttpTool(Tool):
    name = "net_http"
    description = "Appelle l'API HTTP d'un appareil du réseau local (GET/POST/PUT, adresse privée seulement). Soumis à l'accord de l'utilisateur."
    parameters = {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "body": {"type": "string"}}, "required": ["url"]}
    permission = Permission.CONFIRM

    async def execute(self, url: str = "", method: str = "GET", body: str = "", **_: Any) -> dict:
        try:
            return await network.lan_http(method, url, body)
        except network.NetError as exc:
            return _err(exc)


class NetSshTool(Tool):
    name = "net_ssh"
    description = ("Exécute une commande sur une machine enregistrée (Maison › Réseau) par SSH, avec les droits du compte enregistré (souvent root). "
                   "Toujours soumis à l'accord de l'utilisateur, tracé dans le journal d'accès. Préfère des commandes de lecture.")
    parameters = {"type": "object", "properties": {"host": {"type": "string", "description": "Nom de la machine enregistrée"},
                                                  "command": {"type": "string"}, "timeout": {"type": "integer", "description": "Secondes (60 par défaut, 120 max)"}}, "required": ["host", "command"]}
    permission = Permission.CONFIRM

    async def execute(self, host: str = "", command: str = "", timeout: int = 60, **_: Any) -> dict:
        try:
            return await network.ssh_run(host, command, timeout)
        except network.NetError as exc:
            return _err(exc)


class NetInspectTool(Tool):
    name = "net_inspect"
    description = ("Inspecte une machine enregistrée par SSH (lecture seule) : système, disques, mémoire, réseau, ports à l'écoute, processus, connexions récentes, "
                   "services en échec, conteneurs. Soumis à l'accord de l'utilisateur, tracé dans le journal d'accès.")
    parameters = {"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]}
    permission = Permission.CONFIRM

    async def execute(self, host: str = "", **_: Any) -> dict:
        try:
            return await network.inspect(host)
        except network.NetError as exc:
            return _err(exc)


class NetDiscoverTool(Tool):
    name = "net_discover"
    description = ("Cherche les appareils de la maison sur le réseau (ampoules et prises Tuya, Yeelight, WiZ, Kasa, Shelly, Tasmota, WLED, imprimantes, ordinateurs à réveiller) "
                   "et dit lesquels ne sont pas encore ajoutés. Ne modifie rien : l'ajout se fait dans Maison › Appareils › Ajouter un appareil.")
    parameters = {"type": "object", "properties": {"quick": {"type": "boolean"}}, "required": []}
    permission = Permission.CONFIRM

    async def execute(self, quick: bool = False, **_: Any) -> dict:
        from ... import lan_discovery
        try:
            await lan_discovery.run_scan(bool(quick))
            ov = await lan_discovery.overview()
            r = ov["result"]
            return {"source": r["source"], "problem": r["problem"],
                    "found": [{"ip": c["ip"], "kind": c["kind"], "label": c["label"], "status": c["status"], "already_added": bool(c["already"])} for c in r["candidates"]]}
        except Exception as exc:  # noqa: BLE001
            return _err(exc)
