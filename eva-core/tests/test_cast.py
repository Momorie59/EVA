"""Google Home / Chromecast en direct (pychromecast simulé) : volume, pause, état, annonce vocale via eva-scanner."""
import sys
import types

import httpx

from integration_pg import requiert_pg

pytestmark = requiert_pg


class FauxMC:
    def __init__(self, journal):
        self.j = journal
        self.status = types.SimpleNamespace(title="One More Time", artist="Daft Punk", player_state="PLAYING")

    def play(self): self.j.append("play")
    def pause(self): self.j.append("pause")
    def update_status(self): pass
    def play_media(self, url, typ): self.j.append(("media", url, typ))
    def block_until_active(self, timeout=10): pass


class FauxCC:
    def __init__(self, journal):
        self.j = journal
        self.media_controller = FauxMC(journal)
        self.status = types.SimpleNamespace(display_name="Spotify", is_stand_by=False, volume_level=0.3)

    def wait(self, timeout=10): pass
    def set_volume(self, v): self.j.append(("volume", v))
    def quit_app(self): self.j.append("stop")
    def disconnect(self, timeout=3): pass


def test_cast(eva, monkeypatch):
    from app import cast, devices, voix_interne
    from app.config import settings
    journal = []
    monkeypatch.setitem(sys.modules, "pychromecast", types.SimpleNamespace(get_chromecast_from_host=lambda hote, **kw: FauxCC(journal)))
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    A = H(t["alice"])
    d = c.post("/api/home/admin/devices", json={"name": "Enceinte cuisine", "room": "cuisine", "type": "media", "driver": "cast",
                                                "config": {"ip": "192.168.1.60"}}, headers=A)
    assert d.status_code == 200, d.text
    c.portal.call(lambda: devices.control("enceinte cuisine", "brightness", 40))
    assert journal[-1] == ("volume", 0.4)
    c.portal.call(lambda: devices.control("enceinte cuisine", "toggle"))
    assert journal[-1] == "pause"
    e = c.portal.call(lambda: devices.run(devices.find("enceinte cuisine")[0], "state", None))
    assert e["app"] == "Spotify" and e["titre"] == "One More Time" and e["volume"] == 30

    async def fausse_voix(texte):
        return b"RIFFfaux"
    monkeypatch.setattr(voix_interne, "synthese", fausse_voix)
    monkeypatch.setattr(settings, "scanner_url", "http://scanner:8300")

    async def faux_post(self, url, params=None, content=None, headers=None, **kw):
        assert url == "http://scanner:8300/audio" and params == {"vers": "192.168.1.60"} and content == b"RIFFfaux"
        return httpx.Response(200, json={"url": "http://192.168.1.10:8300/a/cle.wav"})
    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    r = c.portal.call(lambda: m.registry.get("annonce").execute(texte="À table !", piece="cuisine"))
    assert "Enceinte cuisine" in r["annonce_sur"], r
    assert journal[-1] == ("media", "http://192.168.1.10:8300/a/cle.wav", "audio/wav")
    assert c.get("/api/auth/verify", headers={"Authorization": f"Bearer {voix_interne.CLE}"}).status_code == 200
    c.delete(f"/api/home/admin/devices/{d.json()['id']}", headers=A)          # base partagée entre les tests : on range
