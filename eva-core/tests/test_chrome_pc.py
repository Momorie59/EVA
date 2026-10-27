"""« Mon Chrome EVA » piloté par le satellite : vrai Chromium, site local, domaines protégés, mot de passe refusé."""
import importlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from test_navigateur import CHROME, Site, _port

pytestmark = pytest.mark.skipif(not CHROME, reason="Chromium absent")


class SiteBanque(Site):
    def do_GET(self):
        if self.path.startswith("/banque"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<html><title>Ma banque</title><body><button>Virement</button></body></html>".encode())
            return
        super().do_GET()


def test_chrome_pc():
    pytest.importorskip("websocket")
    sys.modules.setdefault("sounddevice", types.SimpleNamespace())
    sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "data" / "satellite"))
    sat = importlib.import_module("satellite")
    port, profil = _port(), tempfile.mkdtemp()
    proc = subprocess.Popen([CHROME, "--headless", "--no-sandbox", f"--remote-debugging-port={port}", f"--user-data-dir={profil}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), SiteBanque)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        c = sat.ChromePC(port)
        r = c.faire("ouvrir", url=site + "/")
        assert r["titre"] == "Gare de test" and any(e.get("nom") == "ville" for e in r["elements"]), r
        oid = r["onglet"]
        refs = {(e.get("nom") or e.get("texte")): e["ref"] for e in c.faire("lire", onglet=oid)["elements"]}
        assert "mot de passe" in c.faire("remplir", onglet=oid, ref=refs["secret"], texte="1234")["error"]
        r = c.faire("remplir", onglet=oid, ref=refs["ville"], texte="Rome", valider=True)
        assert "Recherche : Rome" in r["texte"], r
        assert any(o["id"] == oid for o in c.faire("onglets")["onglets"])
        b = c.faire("ouvrir", url=site + "/banque")
        assert b["titre"] == "Ma banque"
        assert "protégé" in c.faire("cliquer", onglet=b["onglet"], ref=b["elements"][0]["ref"])["error"]
        assert c.faire("lire", onglet=b["onglet"])["titre"] == "Ma banque"            # lire reste permis
        assert c.faire("fermer", onglet=b["onglet"])["ok"]
    finally:
        srv.shutdown()
        proc.kill()
        shutil.rmtree(profil, ignore_errors=True)
