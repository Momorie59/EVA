"""Navigateur d'EVA : vrai Chromium sans écran (si présent) piloté par DevTools, sur un petit site local."""
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from integration_pg import requiert_pg

CHROME = next((p for p in (os.getenv("EVA_TEST_CHROME", ""), "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
                           shutil.which("chromium") or "", shutil.which("google-chrome") or "") if p and Path(p).exists()), None)
pytestmark = [requiert_pg, pytest.mark.skipif(not CHROME, reason="Chromium absent")]

ACCUEIL = """<html><head><title>Gare de test</title></head><body><h1>Réserver un train</h1>
<form action="/resultat" method="get"><input name="ville" placeholder="Destination">
<input type="password" name="secret"><select name="classe"><option>Seconde</option><option>Première</option></select>
<button type="submit">Chercher</button></form><a href="/aide">Aide</a></body></html>"""


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/resultat"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            corps = f"<html><title>Résultats</title><body>Recherche : {q.get('ville', [''])[0]} en {q.get('classe', [''])[0]}</body></html>"
        elif self.path == "/aide":
            corps = "<html><title>Aide</title><body>Page d'aide</body></html>"
        else:
            corps = ACCUEIL
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corps.encode())


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def chrome():
    port, profil = _port(), tempfile.mkdtemp()
    proc = subprocess.Popen([CHROME, "--headless", "--no-sandbox", f"--remote-debugging-port={port}", f"--user-data-dir={profil}",
                             "--disable-gpu", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pret = False
    for _ in range(150):                                   # jusqu'à 30 s : premier démarrage lent sur les machines de CI
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            pret = True
            break
        except OSError:
            time.sleep(0.2)
    if not pret:
        proc.kill()
        pytest.skip("Chromium ne répond pas sur son port de débogage")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    proc.kill()
    shutil.rmtree(profil, ignore_errors=True)


def test_garde_fous_reseau():
    from app import navigateur as nav
    for u in ("http://192.168.1.1/admin", "http://localhost:8443", "http://nas.local", "file:///etc/passwd", "http://10.0.0.5", "http://[::1]/"):
        with pytest.raises(nav.NavigateurError):
            nav.verifier_url(u)
    assert nav.verifier_url("example.com") == "https://example.com"


def test_navigation_formulaire_capture(eva, chrome, monkeypatch):
    from app import navigateur as nav
    cdp, site = chrome
    monkeypatch.setattr(nav, "CDP_DIRECT", cdp)
    monkeypatch.setattr(nav, "_prive", lambda h: h == "interdit.test")
    nav._etat.update(page_ws="", base="")
    c, m = eva["c"], eva["m"]
    run = lambda nom, **kw: c.portal.call(lambda: m.registry.get(nom).execute(**kw))       # noqa: E731
    p = run("navigateur_ouvrir", url=site + "/")
    assert p["titre"] == "Gare de test" and "Réserver un train" in p["texte"], p
    refs = {(e.get("nom") or e.get("texte")): e["ref"] for e in p["elements"]}
    assert {"ville", "secret", "classe", "Chercher", "Aide"} <= set(refs)
    assert m.registry.get("navigateur_remplir").permission.value == "confirm"
    assert "mot de passe" in run("navigateur_remplir", ref=refs["secret"], texte="1234")["error"]
    run("navigateur_remplir", ref=refs["classe"], texte="première")
    r = run("navigateur_remplir", ref=refs["ville"], texte="Lyon", valider=True)
    assert r["titre"] == "Résultats" and "Recherche : Lyon en Première" in r["texte"], r
    cap = run("navigateur_capture")
    assert cap["ok"] and cap["markdown"].startswith("![Capture : Résultats](/api/public/medias/")
    assert c.get(cap["image"]).headers["content-type"] == "image/png"
    p = run("navigateur_ouvrir", url=site + "/")
    aide = next(e["ref"] for e in p["elements"] if e.get("texte") == "Aide")
    assert run("navigateur_cliquer", ref=aide)["titre"] == "Aide"
    assert "réseau de la maison" in run("navigateur_ouvrir", url="http://interdit.test/")["error"]
    assert "invalide" in run("navigateur_cliquer", ref="abc")["error"]
