"""Pilotes réseau local sans bibliothèque : Yeelight (TCP 55443), WiZ (UDP 38899), TP-Link Kasa ancien protocole (TCP 9999)."""
import asyncio
import json
import struct

TIMEOUT = 4.0


def _dev():
    from . import devices          # import tardif : devices importe ce module
    return devices


# ------------------------------------------------------------------ Yeelight
async def yeelight(d: dict, action: str, value) -> dict:
    dv = _dev()
    ip, port = d["config"]["ip"], int(d["config"].get("port") or 55443)

    async def call(method: str, params: list) -> list:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), TIMEOUT)
        try:
            w.write((json.dumps({"id": 1, "method": method, "params": params}) + "\r\n").encode())
            await w.drain()
            while True:                                           # l'ampoule peut intercaler des notifications « props »
                line = await asyncio.wait_for(r.readline(), TIMEOUT)
                if not line:
                    raise dv.DeviceError("Yeelight : connexion fermée sans réponse (active « Contrôle LAN » dans l'appli Yeelight).")
                msg = json.loads(line)
                if msg.get("id") == 1:
                    if "error" in msg:
                        raise dv.DeviceError(f"Yeelight : {msg['error'].get('message', 'refusé')}")
                    return msg.get("result", [])
        finally:
            w.close()
    if action == "state":
        res = await call("get_prop", ["power", "bright"])
        return {"on": (res[0] == "on") if res else None, "raw": {"bright": res[1] if len(res) > 1 else None}}
    if action in ("on", "off"):
        await call("set_power", [action, "smooth", 300])
    elif action == "toggle":
        await call("toggle", [])
    elif action == "brightness":
        await call("set_power", ["on", "smooth", 300]); await call("set_bright", [max(1, dv._pct(value)), "smooth", 300])
    elif action == "color":
        rgb = dv._rgb(value); await call("set_power", ["on", "smooth", 300]); await call("set_rgb", [(rgb[0] << 16) + (rgb[1] << 8) + rgb[2], "smooth", 300])
    elif action == "temperature":
        await call("set_power", ["on", "smooth", 300]); await call("set_ct_abx", [max(1700, min(6500, int(value))), "smooth", 300])
    else:
        raise dv.DeviceError("Yeelight : action non prise en charge.")
    return {"ok": True}


# ------------------------------------------------------------------ WiZ
async def _wiz_call(ip: str, port: int, payload: dict) -> dict:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    class P(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            if not fut.done():
                try:
                    fut.set_result(json.loads(data))
                except ValueError:
                    pass
    tr, _ = await loop.create_datagram_endpoint(P, remote_addr=(ip, port))
    try:
        tr.sendto(json.dumps(payload).encode())
        return await asyncio.wait_for(fut, TIMEOUT)
    finally:
        tr.close()


async def wiz(d: dict, action: str, value) -> dict:
    dv = _dev()
    ip, port = d["config"]["ip"], int(d["config"].get("port") or 38899)

    async def pilot() -> dict:
        try:
            return (await _wiz_call(ip, port, {"method": "getPilot", "params": {}})).get("result") or {}
        except asyncio.TimeoutError as exc:
            raise dv.DeviceError("WiZ ne répond pas (éteinte, autre adresse IP, ou « communication locale » désactivée dans l'appli WiZ).") from exc

    async def setp(params: dict):
        try:
            r = await _wiz_call(ip, port, {"method": "setPilot", "params": params})
        except asyncio.TimeoutError as exc:
            raise dv.DeviceError("WiZ ne répond pas.") from exc
        if "error" in r:
            raise dv.DeviceError(f"WiZ : {r['error'].get('message', 'refusé')}")
    if action == "state":
        r = await pilot()
        return {"on": r.get("state"), "raw": {"dimming": r.get("dimming")}}
    if action in ("on", "off"):
        await setp({"state": action == "on"})
    elif action == "toggle":
        await setp({"state": not bool((await pilot()).get("state"))})
    elif action == "brightness":
        await setp({"state": True, "dimming": max(10, dv._pct(value))})
    elif action == "color":
        r, g, b = dv._rgb(value); await setp({"state": True, "r": r, "g": g, "b": b})
    elif action == "temperature":
        await setp({"state": True, "temp": max(2200, min(6500, int(value)))})
    else:
        raise dv.DeviceError("WiZ : action non prise en charge.")
    return {"ok": True}


# ------------------------------------------------------------------ TP-Link Kasa (protocole historique : HS100/HS110, KP, KL…)
def kasa_encrypt(text: str) -> bytes:
    key, out = 171, bytearray()
    for ch in text.encode():
        key ^= ch
        out.append(key)
    return bytes(out)


def kasa_decrypt(data: bytes) -> str:
    key, out = 171, bytearray()
    for b in data:
        out.append(key ^ b)
        key = b
    return out.decode(errors="replace")


async def _kasa_call(ip: str, port: int, payload: dict) -> dict:
    r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), TIMEOUT)
    try:
        body = kasa_encrypt(json.dumps(payload))
        w.write(struct.pack(">I", len(body)) + body)
        await w.drain()
        n = struct.unpack(">I", await asyncio.wait_for(r.readexactly(4), TIMEOUT))[0]
        return json.loads(kasa_decrypt(await asyncio.wait_for(r.readexactly(min(n, 65536)), TIMEOUT)))
    finally:
        w.close()


async def kasa(d: dict, action: str, value) -> dict:
    dv = _dev()
    ip, port = d["config"]["ip"], int(d["config"].get("port") or 9999)
    bulb = d["type"] == "light"
    LIGHT = "smartlife.iot.smartbulb.lightingservice"
    try:
        info = (await _kasa_call(ip, port, {"system": {"get_sysinfo": {}}}))["system"]["get_sysinfo"]
    except (asyncio.TimeoutError, OSError, ValueError, KeyError, asyncio.IncompleteReadError) as exc:
        raise dv.DeviceError("Kasa ne répond pas (les modèles récents Tapo utilisent un autre protocole : passe par Home Assistant).") from exc
    on = bool(info.get("light_state", {}).get("on_off")) if bulb and "light_state" in info else bool(info.get("relay_state"))
    if action == "state":
        return {"on": on, "raw": {"alias": info.get("alias"), "model": info.get("model")}}
    if action == "toggle":
        action = "off" if on else "on"
    if action in ("on", "off"):
        cmd = {LIGHT: {"transition_light_state": {"on_off": int(action == "on")}}} if bulb else {"system": {"set_relay_state": {"state": int(action == "on")}}}
    elif action == "brightness" and bulb:
        cmd = {LIGHT: {"transition_light_state": {"on_off": 1, "brightness": max(1, dv._pct(value))}}}
    else:
        raise dv.DeviceError("Kasa : action non prise en charge par cet appareil.")
    res = await _kasa_call(ip, port, cmd)
    err = next((v.get("err_code") for m in res.values() for v in m.values() if isinstance(v, dict) and v.get("err_code")), 0)
    if err:
        raise dv.DeviceError(f"Kasa : erreur {err}.")
    return {"ok": True}
