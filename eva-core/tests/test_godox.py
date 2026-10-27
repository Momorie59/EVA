"""Lumière blanche réglable via Home Assistant (Godox…) : kelvins ou pourcentage."""
import asyncio

from app import devices


def test_temperature_lumiere(monkeypatch):
    appels = []

    async def faux(dom, svc, eid, data):
        appels.append((dom, svc, eid, data))
        return {"ok": True}
    monkeypatch.setattr(devices.ha, "call_service", faux)
    d = {"config": {"entity_id": "light.godox_tl60"}}
    for v, k in (("5600", 5600), ("3200 K", 3200), (0, 2700), (100, 6500), ("50 %", 4600)):
        asyncio.run(devices._ha(d, "temperature", v))
        assert appels[-1] == ("light", "turn_on", "light.godox_tl60", {"color_temp_kelvin": k}), (v, appels[-1])
