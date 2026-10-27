"""Installer un satellite depuis l'interface : Windows (.cmd à double-cliquer), Mac et Linux (commande), nouvelle clé,
version servie, mise à jour automatique du satellite."""
import sys
import types
from pathlib import Path

from integration_pg import requiert_pg

SAT = Path(__file__).resolve().parents[1] / "app" / "data" / "satellite"


@requiert_pg
def test_installateurs_depuis_l_interface(eva):
    from app import installateurs
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    s = c.post("/api/home/admin/satellites", json={"nom": "PC du testeur", "piece": "bureau", "compte": "alice"}, headers=A).json()
    ancien = {"Authorization": f"Bearer {s['jeton']}"}
    assert c.post("/api/satellite/bonjour", json={"capacites": ["dire"], "version": "1.1"}, headers=ancien).status_code == 200
    v = c.get("/api/public/satellite/version").json()["version"]
    assert v == installateurs.version() and v >= "1.3.1"
    lst = c.get("/api/home/admin/satellites", headers=A).json()
    assert lst["version"] == v and next(x for x in lst["satellites"] if x["id"] == s["id"])["version"] == "1.1"

    w = c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "windows", "options": ["ecran", "fenetre", "pirate"],
                                                                          "eva": "https://192.168.1.10:8443"}, headers=A).json()
    assert w["fichier"]["nom"] == "Installer-EVA-PC-du-testeur.cmd"
    cmd = w["fichier"]["contenu"]
    assert cmd.startswith("@echo off\r\n") and "-Fenetre -Ecran" in cmd and "pirate" not in cmd and "Invoke-WebRequest" not in cmd
    import base64
    import re
    embarque = base64.b64decode(re.sub(r"[^A-Za-z0-9+/=]", "", cmd[cmd.rindex("::EVAPS1::") + 10:]))      # installateur embarqué
    assert embarque.startswith(b"\xef\xbb\xbf") and b"function Telecharger" in embarque and b"Invoke-WebRequest" not in embarque
    assert cmd.index("exit /b\r\n") < cmd.index("::EVAPS1::") and cmd.count("::EVAPS1::") == 1
    jeton = cmd.split('-Jeton "')[1].split('"')[0]
    assert jeton.startswith("evasat_") and jeton != s["jeton"]
    assert c.post("/api/satellite/bonjour", json={}, headers=ancien).status_code == 401               # l'ancienne clé ne marche plus
    assert c.post("/api/satellite/bonjour", json={}, headers={"Authorization": f"Bearer {jeton}"}).status_code == 200

    m = c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "mac", "options": ["ecran", "gestes"],
                                                                          "eva": "https://192.168.1.10:8443"}, headers=A).json()
    assert m["commande"].startswith("curl -fsSk https://192.168.1.10:8443/api/public/satellite/installer-mac.sh")
    assert m["commande"].endswith(" ecran gestes") and m["fichier"]["nom"].endswith(".command") and "Accessibilité" in m["aide"]
    lx = c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "linux", "options": ["local"]}, headers=A).json()
    assert "installer-linux.sh" in lx["commande"] and lx["commande"].endswith(" local")
    assert c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "amiga"}, headers=A).status_code == 400
    assert c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "linux", "eva": "https://x; rm -rf /"}, headers=A).status_code == 400
    assert c.post("/api/home/admin/satellites/zzz/installateur", json={"systeme": "linux"}, headers=A).status_code == 400
    assert c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "linux"},
                  headers=eva["H"](eva["t"]["bob"])).status_code == 403

    ps = c.get("/api/public/satellite/installer-windows.ps1")
    assert ps.content.startswith(b"\xef\xbb\xbf") and b"winget install" in ps.content and ps.content.count(b"\xef\xbb\xbf") == 1
    assert b"Invoke-WebRequest" not in ps.content and b"WriteAllText" in ps.content
    assert c.get("/api/public/satellite/installer-mac.sh").status_code == 200
    c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A)


def _module_satellite(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", types.ModuleType("sounddevice"))
    monkeypatch.syspath_prepend(str(SAT))
    sys.modules.pop("satellite", None)
    import satellite
    return satellite


def test_mise_a_jour_automatique(monkeypatch, tmp_path):
    S = _module_satellite(monkeypatch)
    nouveau = (SAT / "satellite.py").read_text(encoding="utf-8").replace(f'VERSION = "{S.VERSION}"', 'VERSION = "9.9"')

    class Rep:
        def __init__(self, code=200, json=None, content=b""):
            self.status_code, self._j, self.content = code, json, content

        def json(self):
            return self._j

        def raise_for_status(self):
            pass
    reponses = {"/api/public/satellite/version": Rep(json={"version": "9.9"}),
                "/api/public/satellite/satellite.py": Rep(content=nouveau.encode()), "/api/public/satellite/gestes.py": Rep(content=b"X = 1\n")}
    eva = types.SimpleNamespace(url="https://eva", verif=True, s=types.SimpleNamespace(get=lambda url, **kw: reponses[url[len("https://eva"):]]))
    (tmp_path / "satellite.py").write_text("ancien = True\n")
    maj = S.MiseAJour(eva, tmp_path, {})
    assert maj.verifier()
    assert 'VERSION = "9.9"' in (tmp_path / "satellite.py").read_text() and (tmp_path / "satellite.ancien.py").read_text() == "ancien = True\n"
    reponses["/api/public/satellite/version"] = Rep(json={"version": S.VERSION})
    assert not maj.verifier()                                                             # déjà à jour
    reponses["/api/public/satellite/version"] = Rep(json={"version": "10.0"})
    reponses["/api/public/satellite/satellite.py"] = Rep(content=b"def casse(:\n")
    assert not maj.verifier() and 'VERSION = "9.9"' in (tmp_path / "satellite.py").read_text()   # fichier abîmé : rien remplacé
    assert S._num_version("1.10") > S._num_version("1.9")


def test_clavier_tous_systemes(monkeypatch):
    S = _module_satellite(monkeypatch)
    assert set(S.Clavier.TOUCHES) >= {"entree", "ctrl+l", "alt+tab", "espace"}
    assert all(len(v) == 3 and len(v[2]) == 2 for v in S.Clavier.TOUCHES.values())
    appels = []
    monkeypatch.setattr(S, "SYSTEME", "Linux")
    monkeypatch.setattr(S.shutil, "which", lambda n: "/usr/bin/xdotool")
    monkeypatch.setattr(S, "_cmd", lambda a: appels.append(a) or "")
    assert S.Clavier.clic(10.6, 20.2, True)["ok"] and appels[-1][:3] == ["xdotool", "mousemove", "10"]
    assert S.Clavier.touche("ctrl+l")["ok"] and appels[-1] == ["xdotool", "key", "ctrl+l"]
    # macOS : Quartz simulé
    q = types.ModuleType("Quartz")
    postes = []
    for n in ("kCGEventMouseMoved", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGMouseEventClickState", "kCGHIDEventTap", "kCGEventFlagMaskCommand"):
        setattr(q, n, n)
    q.CGPointMake = lambda x, y: (x, y)
    q.CGEventCreateMouseEvent = lambda _s, t, pt, _b: {"t": t, "pt": pt}
    q.CGEventSetIntegerValueField = lambda e, k, v: e.update(clics=v)
    q.CGEventCreateKeyboardEvent = lambda _s, code, bas: {"code": code, "bas": bas}
    q.CGEventKeyboardSetUnicodeString = lambda e, n, ch: e.update(ch=ch)
    q.CGEventSetFlags = lambda e, f: e.update(cmd=True)
    q.CGEventPost = lambda tap, e: postes.append(e)
    monkeypatch.setitem(sys.modules, "Quartz", q)
    monkeypatch.setattr(S, "SYSTEME", "Darwin")
    monkeypatch.setattr(S.time, "sleep", lambda _s: None)
    assert S.Clavier.clic(100, 50, True)["ok"] and [e.get("clics") for e in postes[1:]] == [1, 1, 2, 2]
    postes.clear()
    assert S.Clavier.saisir("é!")["ok"] and [e["ch"] for e in postes] == ["é", "é", "!", "!"]
    postes.clear()
    assert S.Clavier.touche("ctrl+l")["ok"] and postes[0] == {"code": 37, "bas": True, "cmd": True}         # Cmd+L sur Mac


@requiert_pg
def test_android_pause_desinstallation_sonner(eva):
    import threading
    import time
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]
    s = c.post("/api/home/admin/satellites", json={"nom": "Téléphone", "piece": "salon", "compte": "alice"}, headers=A).json()
    a = c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "android", "eva": "https://192.168.1.10:8443"}, headers=A).json()
    assert a["lien"].startswith("evasat://config?eva=https%3A%2F%2F192.168.1.10%3A8443&jeton=evasat_")
    assert a["apk"].endswith("/api/public/satellite/eva-satellite.apk") and a["duree"]["max"] <= 3
    w = c.post(f"/api/home/admin/satellites/{s['id']}/installateur", json={"systeme": "windows", "options": ["ecran", "gestes"]}, headers=A).json()
    assert w["duree"]["min"] == 5 + 2 + 5 and "minutes" in w["duree"]["texte"]
    jeton = w["fichier"]["contenu"].split('-Jeton "')[1].split('"')[0]
    S = {"Authorization": f"Bearer {jeton}"}
    assert c.post("/api/satellite/bonjour", json={"capacites": ["dire", "telephone"], "systeme": "Android 14", "version": "android-1"}, headers=S).json()["pause"] is False
    recus, fin = [], threading.Event()

    def satellite():
        while not fin.is_set():
            r = c.post("/api/satellite/ordres", headers=S)
            if r.status_code != 200:                                              # supprimé : le satellite s'arrête
                return
            for o in r.json()["ordres"]:
                recus.append(o)
                res = {"ok": True, "fait": ["lancement automatique retiré", "dossier effacé à l'arrêt"], "reste": []} if o["type"] == "desinstaller" else {"ok": True}
                c.post("/api/satellite/resultat", json={"id": o["id"], "resultat": res}, headers=S)
    threading.Thread(target=satellite, daemon=True).start()
    time.sleep(0.4)
    p = c.post(f"/api/home/admin/satellites/{s['id']}/ecoute", json={"actif": False}, headers=A).json()
    assert p["pause"] is True and recus[-1] == {**recus[-1], "type": "ecoute", "actif": False}
    assert c.post("/api/satellite/bonjour", json={}, headers=S).json()["pause"] is True                  # gardé à la reconnexion
    c.post(f"/api/home/admin/satellites/{s['id']}/ecoute", json={"actif": True}, headers=A)
    k = c.post(f"/api/home/admin/satellites/{s['id']}/controle", json={"action": "redemarrer"}, headers=A).json()
    assert k["ok"] and recus[-1]["type"] == "controle" and recus[-1]["action"] == "redemarrer"
    assert c.post(f"/api/home/admin/satellites/{s['id']}/controle", json={"action": "formater"}, headers=A).status_code == 400
    r = c.portal.call(lambda: m.registry.get("telephone_sonner").execute())
    assert r["ok"] and recus[-1]["type"] == "telephone" and recus[-1]["action"] == "sonner"
    d = c.delete(f"/api/home/admin/satellites/{s['id']}", headers=A).json()
    assert d["desinstalle"] and "dossier effacé à l'arrêt" in d["fait"] and recus[-1]["type"] == "desinstaller"
    assert d["commandes"]["linux"]["commande"] == "curl -fsSk http://testserver/api/public/satellite/desinstaller-linux.sh | bash"
    assert d["commandes"]["windows"]["fichier"].endswith("/desinstaller-windows.cmd") and "Désinstaller" in d["commandes"]["android"]["aide"]
    h = c.get("/api/home/admin/satellites-desinstallation", headers={**A, "X-Forwarded-Proto": "https", "Host": "192.168.1.10:8443"}).json()
    assert h["mac"]["commande"].startswith("curl -fsSk https://192.168.1.10:8443/api/public/satellite/")
    assert c.post("/api/satellite/bonjour", json={}, headers=S).status_code == 401
    fin.set()
    for f in ("desinstaller-linux.sh", "desinstaller-mac.sh", "desinstaller-windows.cmd"):
        assert c.get(f"/api/public/satellite/{f}").status_code == 200
    assert c.get("/api/public/satellite/version").json()["android"] >= 0


def test_satellite_pause_et_desinstallation(monkeypatch, tmp_path):
    S = _module_satellite(monkeypatch)
    sat = S.Satellite.__new__(S.Satellite)
    sat.pause_eva, sat.fichier_pause, sat.ptt = False, tmp_path / "pause", False
    assert sat.basculer_pause() is True and sat.fichier_pause.exists() and sat.basculer_pause() is False
    assert sat.controle("parler")["ok"] and sat.ptt and "inconnue" in sat.controle("x")["error"]
    assert S._PAUSE.match("pause") and S._PAUSE.match("mets-toi en pause") and not S._PAUSE.match("mets la musique en pause")
    appels = []
    monkeypatch.setattr(S, "SYSTEME", "Linux")
    monkeypatch.setattr(S.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".config" / "autostart").mkdir(parents=True)
    (tmp_path / ".config" / "autostart" / "eva-satellite.desktop").write_text("x")
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: appels.append(a))
    r = S.desinstaller(tmp_path / "eva-satellite")
    assert r["ok"] and "lancement à l'ouverture de session retiré" in r["fait"]
    assert not (tmp_path / ".config" / "autostart" / "eva-satellite.desktop").exists() and "rm -rf" in appels[-1][0][-1]
