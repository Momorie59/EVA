"""Éclaireur réseau d'EVA (network_mode: host) — une petite API interne, protégée par jeton, utilisée par eva-core."""
import hmac
import ipaddress
import os

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from . import probes

TOKEN = os.getenv("EVA_SCANNER_TOKEN") or os.getenv("EVA_AUTH_TOKEN") or ""
app = FastAPI(title="eva-scanner")


def guard(request: Request, authorization: str = Header(default="")):
    """Jeton exigé s'il est défini ; sinon, seuls les réseaux privés (le NAS, Docker, ton LAN) sont acceptés."""
    if TOKEN:
        if not hmac.compare_digest(authorization.removeprefix("Bearer ").strip(), TOKEN):
            raise HTTPException(status_code=401, detail="Jeton refusé.")
        return
    try:
        ip = ipaddress.ip_address(request.client.host)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=403, detail="Client inconnu.")
    if not (ip.is_private or ip.is_loopback):
        raise HTTPException(status_code=403, detail="Réseau privé uniquement.")


class ScanBody(BaseModel):
    cidrs: list[str] = []
    quick: bool = False


@app.get("/health")
async def health():
    return {"ok": True, "interfaces": probes.interfaces()}


@app.post("/scan", dependencies=[Depends(guard)])
async def scan(body: ScanBody):
    cidrs = []
    for c in body.cidrs[:4]:
        net = ipaddress.ip_network(c, strict=False)
        if not net.is_private or net.prefixlen < 22:
            raise HTTPException(status_code=400, detail="Réseau privé de taille raisonnable (/22 minimum) uniquement.")
        cidrs.append(str(net))
    return await probes.run_all(cidrs or None, body.quick)


@app.post("/presence", dependencies=[Depends(guard)])
async def presence():
    """Appareils qui répondent en ce moment sur le réseau de la maison (IP + MAC), pour savoir qui est là (téléphones)."""
    vus: dict[str, str] = {}
    for c in dict.fromkeys(i["cidr"] for i in probes.interfaces()):
        for h in await probes.arp_sweep(c, settle=2.0):
            vus[h["mac"]] = h["ip"]
    return {"appareils": [{"mac": m, "ip": ip} for m, ip in vus.items()]}


# ---- Audio temporaire pour les enceintes Google (Cast) : elles ne lisent qu'une adresse HTTP du réseau, sans certificat maison.
_audios: dict[str, tuple[float, bytes, str]] = {}


@app.post("/audio", dependencies=[Depends(guard)])
async def deposer_audio(request: Request, vers: str = "", type: str = "audio/wav"):
    """eva-core dépose une annonce (wav) ; renvoie l'adresse que l'enceinte `vers` (son IP) pourra lire pendant 5 minutes."""
    import secrets
    import socket
    import time
    data = await request.body()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio vide ou trop gros.")
    for k in [k for k, v in _audios.items() if time.time() - v[0] > 300]:
        _audios.pop(k, None)
    cle = secrets.token_urlsafe(18)
    _audios[cle] = (time.time(), data, type if type.startswith("audio/") else "audio/wav")
    ip = "127.0.0.1"
    try:                                                   # l'adresse du NAS vue depuis l'enceinte
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect((vers or "8.8.8.8", 9))
        ip = sk.getsockname()[0]
        sk.close()
    except OSError:
        pass
    return {"url": f"http://{ip}:{os.getenv('EVA_SCANNER_PORT', '8300')}/a/{cle}.wav"}


@app.get("/a/{nom}")
async def lire_audio(nom: str, request: Request):
    """Lecture par l'enceinte : nom aléatoire (la clé), valable 5 minutes, réseau privé seulement."""
    import time
    from fastapi.responses import Response
    try:
        prive = ipaddress.ip_address(request.client.host).is_private
    except (ValueError, AttributeError):
        prive = False
    if not prive:
        raise HTTPException(status_code=403, detail="Réseau privé uniquement.")
    v = _audios.get(nom.rsplit(".", 1)[0])
    if not v or time.time() - v[0] > 300:
        raise HTTPException(status_code=404, detail="Introuvable.")
    return Response(v[1], media_type=v[2])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("EVA_SCANNER_PORT", "8300")), log_level="warning")
