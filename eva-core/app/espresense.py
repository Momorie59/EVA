"""Présence pièce par pièce avec des ESP32 (firmware libre ESPresense, https://espresense.com).

Chaque ESP32, posé dans une pièce, repère en Bluetooth les téléphones, montres et balises de la famille et publie en MQTT :
    espresense/devices/<appareil>/<pièce>   {"id": "...", "name": "...", "rssi": -67, "distance": 1.84}
EVA écoute ces messages (courtier MQTT : le service « eva-mqtt » de docker-compose, ou celui de Home Assistant).
La pièce d'une personne = la pièce où l'un de ses appareils a été vu au plus près dans les 30 dernières secondes.
L'administrateur associe chaque appareil vu à une personne (Maison › Présence). Rien ne sort de la maison."""
import json
import logging
import threading
import time

from .db import get_pool

logger = logging.getLogger("eva-core.espresense")
KV = "espresense"
FRAIS_S = 30                 # une mesure plus vieille ne compte plus pour la pièce
DISTANCE_MAX = 12.0          # au-delà, trop loin pour être sûr de la pièce
DEFAUT = {"actif": False, "hote": "eva-mqtt", "port": 1883, "utilisateur": "", "mot_de_passe": "", "prefixe": "espresense", "appareils": {}}

_mesures: dict[str, dict[str, dict]] = {}     # appareil → pièce → {"distance", "rssi", "ts"}
_noms: dict[str, str] = {}                    # appareil → nom annoncé (« iPhone de… »)
_etat: dict = {"connecte": False, "erreur": "", "messages": 0}
_client = None
_verrou = threading.Lock()
_conf: dict = dict(DEFAUT)


async def reglages() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return {**DEFAUT, **{k: v for k, v in d.items() if k in DEFAUT}}


async def regler(chg: dict) -> dict:
    d = {**await reglages(), **{k: v for k, v in (chg or {}).items() if k in DEFAUT}}
    d["port"] = int(d["port"] or 1883)
    d["appareils"] = {str(k)[:120]: " ".join(str(v).split())[:40] for k, v in (d.get("appareils") or {}).items() if str(v).strip()}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    await demarrer(d)
    return d


def recevoir(topic: str, payload: bytes | str, prefixe: str = "espresense", maintenant: float | None = None) -> bool:
    """Traite un message ESPresense. Renvoie True s'il a été compris (sert aussi aux tests)."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != prefixe or parts[1] != "devices":
        return False
    appareil, piece = parts[2], parts[3]
    try:
        d = json.loads(payload)
    except (ValueError, TypeError):
        return False
    try:
        dist = float(d.get("distance"))
    except (TypeError, ValueError):
        return False
    with _verrou:
        _mesures.setdefault(appareil, {})[piece] = {"distance": dist, "rssi": d.get("rssi"), "ts": maintenant or time.time()}
        if d.get("name"):
            _noms[appareil] = str(d["name"])[:60]
        _etat["messages"] += 1
    return True


def piece_de_appareil(appareil: str, maintenant: float | None = None) -> tuple[str, float] | None:
    now = maintenant or time.time()
    with _verrou:
        vus = [(p, m["distance"]) for p, m in _mesures.get(appareil, {}).items() if now - m["ts"] < FRAIS_S and m["distance"] <= DISTANCE_MAX]
    return min(vus, key=lambda x: x[1]) if vus else None


def pieces(appareils: dict[str, str], maintenant: float | None = None) -> dict[str, dict]:
    """personne → {"piece", "distance"} d'après ses appareils associés."""
    out: dict[str, dict] = {}
    for appareil, personne in appareils.items():
        r = piece_de_appareil(appareil, maintenant)
        if r and (personne not in out or r[1] < out[personne]["distance"]):
            out[personne] = {"piece": _joli(r[0]), "distance": round(r[1], 1)}
    return out


def _joli(piece: str) -> str:
    return piece.replace("_", " ").replace("-", " ").strip().capitalize()


async def pieces_famille() -> dict[str, dict]:
    c = await reglages()
    return pieces(c["appareils"]) if c["actif"] else {}


async def piece_de(personne: str) -> str | None:
    """Pièce actuelle d'une personne (nom ou compte, sans tenir compte des majuscules), ou None."""
    for nom, info in (await pieces_famille()).items():
        if nom.lower() == (personne or "").lower():
            return info["piece"]
    return None


def appareils_vus(maintenant: float | None = None) -> list[dict]:
    now = maintenant or time.time()
    out = []
    with _verrou:
        for a, par_piece in _mesures.items():
            recents = {p: m for p, m in par_piece.items() if now - m["ts"] < 600}
            if not recents:
                continue
            p, m = min(recents.items(), key=lambda x: x[1]["distance"])
            out.append({"id": a, "nom": _noms.get(a, ""), "piece": _joli(p), "distance": round(m["distance"], 1),
                        "vu_il_y_a_s": round(now - m["ts"])})
    return sorted(out, key=lambda x: (x["vu_il_y_a_s"], x["id"]))


def etat() -> dict:
    return {**_etat, "pieces_vues": sorted({_joli(p) for d in _mesures.values() for p in d})}


async def demarrer(conf: dict | None = None) -> None:
    """(Re)connecte le client MQTT selon les réglages (dans un fil à part : paho est bloquant)."""
    global _client, _conf
    conf = conf or await reglages()
    _conf = conf
    if _client is not None:
        try:
            _client.loop_stop()
            _client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        _client = None
        _etat["connecte"] = False
    if not conf["actif"]:
        return
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="eva-espresense")
        if conf["utilisateur"]:
            c.username_pw_set(conf["utilisateur"], conf["mot_de_passe"] or None)
        prefixe = conf["prefixe"] or "espresense"

        def connecte(cl, _u, _f, rc, _p=None):
            ok = not getattr(rc, "is_failure", False) if not isinstance(rc, int) else rc == 0
            _etat.update(connecte=ok, erreur="" if ok else f"Le courtier MQTT refuse la connexion ({rc}).")
            if ok:
                cl.subscribe(f"{prefixe}/devices/#")

        def deconnecte(_cl, _u, _f, rc, _p=None):
            _etat["connecte"] = False

        c.on_connect = connecte
        c.on_disconnect = deconnecte
        c.on_message = lambda _cl, _u, msg: recevoir(msg.topic, msg.payload, prefixe)
        c.connect_async(conf["hote"], int(conf["port"]), keepalive=30)
        c.loop_start()
        _client = c
    except Exception as exc:  # noqa: BLE001
        _etat.update(connecte=False, erreur=f"Courtier MQTT injoignable : {exc}"[:200])
