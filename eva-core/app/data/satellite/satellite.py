#!/usr/bin/env python3
"""Satellite vocal d'EVA : un micro et un haut-parleur dans une pièce (Raspberry Pi, vieux PC, portable Windows/Linux/Mac).

Il écoute en continu, ne réagit qu'au mot « EVA » (« EVA, allume la lumière »), envoie la phrase à EVA sur le NAS et
lit la réponse à voix haute. Rien n'est enregistré : chaque phrase est transcrite par le Whisper d'EVA puis oubliée.
Réglages : satellite.json à côté de ce fichier (écrit par l'installateur), ou options en ligne de commande.

    python3 satellite.py --eva https://192.168.1.10:8443 --jeton evasat_… [--certificat eva-certificat.crt]
    python3 satellite.py --liste-audio        (micros et haut-parleurs disponibles)

Dépendances : pip install numpy sounddevice requests  (Linux : sudo apt install libportaudio2).
Options du PC : écran (pip install mss pillow rapidocr_onnxruntime), gestes (pip install mediapipe opencv-python), tableau au repos."""
import argparse
import io
import json
import math
import os
import platform
import shutil
import subprocess
import webbrowser
import queue
import re
import sys
import threading
import time
import unicodedata
import wave
from collections import deque
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd

TAUX = 16000
TRAME = 480                      # 30 ms
PREROLL_MS = 350
FIN_SILENCE_MS = 900                # fin de phrase : 0,9 s de silence (700 ms coupait les phrases avec une hésitation)
MIN_PAROLE_MS = 300
MAX_PAROLE_MS = 12000
EVEIL_MS = 8000
ECOUTE_MUSIQUE_S = 12
VERSION = "1.7"

_EVEIL = re.compile(r"^\W*(?:(?:hey|h[eé]|dis|ok|okay|bonjour|salut|coucou)\W+)?(?:[eé]h?\W*)?(?:[eéèêë]+|a)\s?v(?:a|ah|ha|à|e)\b[\s,.!?:;-]*", re.I)
_PAUSE = re.compile(r"^\W*(?:mets[- ]toi en |passe en )?(?:pause|veille)\W*$|^\W*arr[êe]te d.[ée]couter\W*$|^\W*ne m.[ée]coute plus\W*$", re.I)
_MUSIQUE = re.compile(r"(quel(?:le)?|c.?est quoi|qu.?est.?ce que c.?est|reconna\w+|trouve).{0,25}(musique|chanson|morceau|titre|son)\b", re.I)
_HALLUCINATIONS = [re.compile(x, re.I) for x in (r"sous-?titr", r"amara\.org", r"merci d'avoir regard", r"abonne", r"^\W*merci\W*$",
                                                   r"^\W*(?:\.{2,}|…|♪+)\W*$", r"^\W*(?:euh+|hum+|hmm+|ah+|oh+)\W*$")]


def hallucination(texte: str) -> bool:
    """Whisper invente du texte sur du bruit ou du silence : on l'écarte (mêmes règles que l'interface web)."""
    t = (texte or "").strip()
    return len(t) < 2 or any(r.search(t) for r in _HALLUCINATIONS)


_JOURNAL: "deque[str]" = deque(maxlen=200)              # dernières lignes, envoyées à EVA pour le diagnostic
_FICHIER_JOURNAL = Path(__file__).resolve().parent / "satellite.log"


def log(*a):
    ligne = time.strftime("%d/%m %H:%M:%S ") + " ".join(str(x) for x in a)
    _JOURNAL.append(ligne)
    try:
        print(ligne, flush=True)
    except Exception:  # noqa: BLE001 — pythonw (Windows) : pas de console
        pass
    try:                                              # aussi dans satellite.log (Windows lance le satellite sans fenêtre)
        if _FICHIER_JOURNAL.exists() and _FICHIER_JOURNAL.stat().st_size > 1_000_000:
            _FICHIER_JOURNAL.replace(_FICHIER_JOURNAL.with_suffix(".log.1"))
        with open(_FICHIER_JOURNAL, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError:
        pass


def sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


def commande_apres_eveil(texte: str):
    """« EVA, allume la cuisine » → « allume la cuisine » ; « EVA » seul → "" ; pas de mot d'éveil → None."""
    m = _EVEIL.match(texte or "")
    if not m:
        return None
    reste = texte[m.end():].strip()
    return reste[:1].upper() + reste[1:] if reste else ""


def wav(pcm: np.ndarray, taux: int = TAUX) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return b.getvalue()


class Eva:
    def __init__(self, url: str, jeton: str, verif):
        self.url, self.verif = url.rstrip("/"), verif
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {jeton}"

    def _post(self, chemin: str, delai: float = 60, **kw):
        r = self.s.post(self.url + chemin, timeout=delai, verify=self.verif, **kw)
        if r.status_code == 401:
            raise SystemExit("Jeton refusé : ce satellite a été supprimé dans EVA (Maison › Satellites). Recrée-le.")
        r.raise_for_status()
        return r

    def bonjour(self, infos: dict | None = None) -> dict:
        return self._post("/api/satellite/bonjour", 10, json=infos or {}).json()

    def transcrire(self, pcm: np.ndarray, rapide: bool = False) -> str:
        """rapide=True : petit modèle (repérer « EVA ») ; sinon le modèle complet, bien plus juste (la vraie demande)."""
        r = self._post("/voice/stt" + ("?mode=fast" if rapide else ""), 60 if not rapide else 30,
                       files={"audio": ("phrase.wav", wav(normaliser(pcm)), "audio/wav")})
        return (r.json().get("text") or "").strip()

    flux_ok = True                       # EVA récente : réponse phrase par phrase (sinon, réponse complète d'un bloc)
    eveil_ok = True                      # EVA récente : un seul satellite répond quand plusieurs entendent

    def demander(self, texte: str) -> dict:
        return self._post("/api/satellite/demander", 260, json={"texte": texte}).json()

    def repondre(self, texte: str) -> dict:
        return self._post("/api/satellite/repondre", 260, json={"texte": texte}).json()

    def _flux(self, chemin: str, texte: str):
        """Événements au fil de l'eau : {"attente"}, {"dire"}, puis {"question"} ou {"reponse"}."""
        if self.flux_ok:
            r = self.s.post(self.url + chemin + "_flux", json={"texte": texte}, timeout=(10, 260), verify=self.verif, stream=True)
            if r.status_code == 404:
                self.flux_ok = False
            else:
                if r.status_code == 401:
                    raise SystemExit("Jeton refusé : ce satellite a été supprimé dans EVA (Maison › Satellites). Recrée-le.")
                r.raise_for_status()
                r.encoding = "utf-8"
                for ligne in r.iter_lines(chunk_size=None, decode_unicode=True):
                    if ligne and ligne.strip():
                        yield json.loads(ligne)
                return
        rep = self._post(chemin, 260, json={"texte": texte}).json()          # ancienne EVA
        yield {**rep, "dire_aussi": True} if "reponse" in rep else rep

    def demander_flux(self, texte: str):
        return self._flux("/api/satellite/demander", texte)

    def repondre_flux(self, texte: str):
        return self._flux("/api/satellite/repondre", texte)

    def eveil(self, score: float, suite: bool) -> bool:
        if not self.eveil_ok:
            return True
        try:
            r = self.s.post(self.url + "/api/satellite/eveil", json={"score": round(score, 2), "suite": suite}, timeout=5, verify=self.verif)
        except requests.RequestException:
            return True
        if r.status_code == 404:
            self.eveil_ok = False
            return True
        return bool(r.ok and r.json().get("repondre", True))

    def tableau(self) -> dict:
        r = self.s.get(self.url + "/api/satellite/tableau", timeout=40, verify=self.verif)
        return r.json() if r.ok else {}

    def ordres(self) -> list[dict]:
        return self._post("/api/satellite/ordres", 40).json().get("ordres", [])

    def resultat(self, oid: str, resultat: dict) -> None:
        self._post("/api/satellite/resultat", 15, json={"id": oid, "resultat": resultat})

    def musique(self, pcm: np.ndarray, taux: int = TAUX) -> dict:
        r = self.s.post(self.url + "/api/satellite/musique?nom=extrait.wav", data=wav(pcm, taux), timeout=60, verify=self.verif)
        if r.status_code >= 400:
            try:
                return {"phrase": r.json().get("detail", "La reconnaissance musicale a échoué.")}
            except ValueError:
                return {"phrase": "La reconnaissance musicale a échoué."}
        return r.json()

    def voix(self, texte: str) -> tuple[np.ndarray, int]:
        r = self._post("/voice/tts", 60, json={"text": texte})
        with wave.open(io.BytesIO(r.content)) as w:
            taux, n = w.getframerate(), w.getnchannels()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return (pcm.reshape(-1, n) if n > 1 else pcm), taux


KWS_DOSSIER = "modele-eveil"
KWS_MOTS = "▁E V A @EVA\n▁A V A @EVA\n▁E VE @EVA\n▁HE Y ▁E V A @EVA\n"


class EveilLocal:
    """Mot d'éveil détecté SUR le satellite (sherpa-onnx, comme openWakeWord chez Jarvis) : rien ne part vers le NAS
    tant que « EVA » n'est pas entendu. Whisper confirme ensuite la phrase : un faux déclenchement ne fait rien."""

    def __init__(self, dossier: Path, sensibilite: float = 0.5):
        import sherpa_onnx
        f = lambda motif: str(next(dossier.glob(motif)))  # noqa: E731
        (dossier / "eva-mots.txt").write_text(KWS_MOTS, encoding="utf-8")
        s = min(1.0, max(0.0, float(sensibilite)))
        self.kws = sherpa_onnx.KeywordSpotter(
            tokens=f("tokens.txt"), encoder=f("encoder-*.int8.onnx"), decoder=f("decoder-*.int8.onnx"), joiner=f("joiner-*.int8.onnx"),
            num_threads=1, keywords_file=str(dossier / "eva-mots.txt"), keywords_score=1.0 + 2.0 * s, keywords_threshold=0.30 - 0.20 * s)
        self.flux = self.kws.create_stream()
        self.dernier = 0.0

    def ecouter(self, trame: np.ndarray) -> bool:
        self.flux.accept_waveform(TAUX, trame.astype(np.float32) / 32768)
        entendu = False
        while self.kws.is_ready(self.flux):
            self.kws.decode_stream(self.flux)
            if self.kws.get_result(self.flux):
                self.kws.reset_stream(self.flux)
                self.dernier, entendu = time.time(), True
        return entendu



# ---------------------------------------------------------------- pilotage de l'ordinateur (ordres envoyés par EVA)

SYSTEME = platform.system()            # Windows, Linux, Darwin
APPLIS_PAR_DEFAUT = {
    "Windows": {"bloc-notes": "notepad", "calculatrice": "calc", "explorateur": "explorer", "paint": "mspaint",
                "spotify": "start spotify:", "paramètres": "start ms-settings:"},
    "Linux": {"calculatrice": "gnome-calculator", "fichiers": "xdg-open ~", "terminal": "x-terminal-emulator", "spotify": "spotify"},
    "Darwin": {"calculatrice": "open -a Calculator", "finder": "open ~", "spotify": "open -a Spotify"},
}


def _touche(code: int, n: int = 1) -> None:
    import ctypes
    for _ in range(n):
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)


def _cmd(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "échec").strip()[:200])
    return r.stdout.strip()


class Ordinateur:
    """Exécute les ordres de pilotage. Seules les applis listées (satellite.json, « applis ») peuvent être lancées."""

    def __init__(self, applis: dict | None, source_musique, eva: "Eva"):
        self.applis = {**APPLIS_PAR_DEFAUT.get(SYSTEME, {}), **{k.lower(): v for k, v in (applis or {}).items()}}
        self.source_musique, self.eva = source_musique, eva

    def faire(self, action: str, valeur: str) -> dict:
        v = (valeur or "").strip()
        if action == "ouvrir":
            nom = next((k for k in self.applis if k == v.lower()), None) or next((k for k in self.applis if v.lower() and v.lower() in k), None)
            if not nom:
                return {"error": f"« {v} » n'est pas dans la liste des applis autorisées sur cet ordinateur : {', '.join(sorted(self.applis))}. "
                                 "Ajoute-la dans satellite.json (« applis »)."}
            subprocess.Popen(os.path.expanduser(self.applis[nom]), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "texte": f"{nom} est lancé."}
        if action == "ouvrir_site":
            if not v.startswith(("http://", "https://")):
                v = "https://" + v
            webbrowser.open(v)
            return {"ok": True, "texte": f"J'ouvre {v}."}
        if action in ("volume", "muet", "lecture_pause", "suivant", "precedent"):
            return self._son(action, v)
        if action == "verrouiller":
            if SYSTEME == "Windows":
                import ctypes
                ctypes.windll.user32.LockWorkStation()
            elif SYSTEME == "Darwin":
                _cmd(["pmset", "displaysleepnow"])
            else:
                _cmd(["loginctl", "lock-session"])
            return {"ok": True, "texte": "Ordinateur verrouillé."}
        if action in ("eteindre", "redemarrer"):
            if SYSTEME == "Windows":
                _cmd(["shutdown", "/s" if action == "eteindre" else "/r", "/t", "60"])
            else:
                _cmd(["shutdown", "-h" if action == "eteindre" else "-r", "+1"])
            return {"ok": True, "texte": f"L'ordinateur {'s’éteint' if action == 'eteindre' else 'redémarre'} dans une minute (« annule l'extinction » pour arrêter)."}
        if action == "annuler_extinction":
            _cmd(["shutdown", "/a"] if SYSTEME == "Windows" else ["shutdown", "-c"])
            return {"ok": True, "texte": "Extinction annulée."}
        if action == "etat":
            return self._etat()
        if action == "reconnaitre_musique":
            return self._musique()
        return {"error": f"Action inconnue : {action}."}

    def _son(self, action: str, v: str) -> dict:
        if SYSTEME == "Windows":
            codes = {"muet": 0xAD, "lecture_pause": 0xB3, "suivant": 0xB0, "precedent": 0xB1}
            if action == "volume":
                if v in ("plus", "+", "monte"):
                    _touche(0xAF, 5)
                elif v in ("moins", "-", "baisse"):
                    _touche(0xAE, 5)
                else:
                    n = max(0, min(100, int(v.strip("% ") or 50)))
                    _touche(0xAE, 50)                       # tout en bas, puis 2 % par appui
                    _touche(0xAF, round(n / 2))
            else:
                _touche(codes[action])
        elif SYSTEME == "Darwin":
            if action == "volume":
                n = 70 if v in ("plus", "+") else 30 if v in ("moins", "-") else max(0, min(100, int(v.strip("% ") or 50)))
                _cmd(["osascript", "-e", f"set volume output volume {n}"])
            elif action == "muet":
                _cmd(["osascript", "-e", "set volume with output muted"])
            else:
                return {"error": "Sur Mac, la lecture se pilote depuis l'appli (ou Spotify par EVA)."}
        else:
            if action == "volume":
                arg = "+10%" if v in ("plus", "+") else "-10%" if v in ("moins", "-") else f"{max(0, min(100, int(v.strip('% ') or 50)))}%"
                _cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", arg])
            elif action == "muet":
                _cmd(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            else:
                if not shutil.which("playerctl"):
                    return {"error": "Installe playerctl (sudo apt install playerctl) pour piloter la lecture."}
                _cmd(["playerctl", {"lecture_pause": "play-pause", "suivant": "next", "precedent": "previous"}[action]])
        return {"ok": True}

    def _etat(self) -> dict:
        try:
            import psutil
            d = psutil.disk_usage(os.path.expanduser("~"))
            return {"ok": True, "processeur_pct": psutil.cpu_percent(interval=0.5), "memoire_pct": psutil.virtual_memory().percent,
                    "disque_pct": d.percent, "allume_depuis_h": round((time.time() - psutil.boot_time()) / 3600, 1), "systeme": SYSTEME}
        except ImportError:
            charge = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
            return {"ok": True, "charge": charge, "systeme": SYSTEME, "note": "pip install psutil pour plus de détails"}

    def _musique(self) -> dict:
        if self.source_musique in (None, ""):
            return {"error": "Aucune source « son de l'ordinateur » réglée : mets \"source_musique\" dans satellite.json "
                             "(Linux : l'appareil « Monitor of … » ; Windows : « Mixage stéréo », à activer dans les réglages du son ; voir --liste-audio)."}
        dev = int(self.source_musique) if str(self.source_musique).isdigit() else self.source_musique
        info = sd.query_devices(dev, "input")
        taux = int(info["default_samplerate"])
        canaux = max(1, min(2, int(info["max_input_channels"])))
        pcm = sd.rec(int(ECOUTE_MUSIQUE_S * taux), samplerate=taux, channels=canaux, dtype="int16", device=dev)
        sd.wait()
        mono = pcm.mean(axis=1).astype(np.int16) if pcm.ndim > 1 else pcm
        r = self.eva.musique(mono, taux)
        return {"ok": "titre" in r, "texte": r.get("phrase", ""), **{k: r[k] for k in ("titre", "artiste", "album") if k in r}}


# ---------------------------------------------------------------- « mon Chrome EVA » (comme le vrai Chrome de Jarvis)

DOMAINES_PROTEGES = re.compile(r"(impots\.gouv|ameli\.fr|\bcaf\.fr|banque|bank|credit-?agricole|bnpparibas|societegenerale|caisse-?epargne|"
                               r"labanquepostale|\blcl\.fr|boursorama|fortuneo|hellobank|revolut|paypal|n26\.com|doctolib|mutuelle|"
                               r"mon-?espace-?sante|sante\.fr|urssaf|pole-?emploi|francetravail)", re.I)
INSTANTANE = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-eva-ref]').forEach((e) => e.removeAttribute('data-eva-ref'));
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=checkbox], [role=tab], [onclick], summary';
  const els = []; let n = 0;
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || n >= 80) continue;
    n += 1; e.setAttribute('data-eva-ref', String(n));
    const t = (e.innerText || e.value || e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('alt') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const o = { ref: n, type: e.tagName.toLowerCase() + (e.type ? ':' + e.type : '') };
    if (t) o.texte = t;
    if (e.placeholder) o.indice = e.placeholder.slice(0, 60);
    if (e.name) o.nom = e.name.slice(0, 40);
    if (e.tagName === 'A') o.lien = e.href.slice(0, 160);
    if (e.tagName === 'SELECT') o.choix = [...e.options].slice(0, 15).map((x) => x.text.trim()).filter(Boolean);
    if (e.type === 'checkbox' || e.type === 'radio') o.coche = e.checked;
    els.push(o);
  }
  const texte = (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n').trim();
  return { titre: document.title, url: location.href, texte: texte.slice(0, 7000), tronque: texte.length > 7000, elements: els };
})()
"""
SENSIBLE = r"""
((e) => {
  if (!e) return 'introuvable';
  const t = (e.type || '').toLowerCase(), ac = (e.autocomplete || '').toLowerCase();
  const id = ((e.name || '') + ' ' + (e.id || '') + ' ' + (e.placeholder || '') + ' ' + (e.getAttribute('aria-label') || '')).toLowerCase();
  if (t === 'password' || ac.includes('password') || ac.startsWith('cc-') || ac.includes('one-time-code')) return 'sensible';
  if (/pass|mot.?de.?passe|mdp|cvv|cvc|cryptogramme|carte|card|iban|otp|code.?secret|pin\b/.test(id)) return 'sensible';
  return 'ok';
})(document.querySelector('[data-eva-ref="REF"]'))
"""


def _chemin_chrome() -> str | None:
    candidats = {
        "Windows": [os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")],
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium"],
    }.get(SYSTEME, [shutil.which(x) or "" for x in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")])
    return next((c for c in candidats if c and os.path.exists(c)), None)


class ChromePC:
    """Chrome visible sur l'ordinateur, profil dédié « EVA » (tes connexions y restent). Lire et ouvrir : libre.
    Cliquer / remplir : demandé à chaque fois par EVA, jamais sur la banque, les impôts ou la santé, jamais un mot de passe."""

    def __init__(self, port: int = 9333):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"

    def _get(self, chemin: str, methode: str = "GET"):
        r = requests.request(methode, self.base + chemin, timeout=5)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _pret(self):
        try:
            return self._get("/json/version")
        except requests.RequestException:
            pass
        chrome = _chemin_chrome()
        if not chrome:
            raise RuntimeError("Chrome (ou Edge) n'est pas installé sur cet ordinateur.")
        profil = str(Path.home() / ".eva-chrome")
        subprocess.Popen([chrome, f"--remote-debugging-port={self.port}", f"--user-data-dir={profil}", "--no-first-run",
                          "--no-default-browser-check", "--remote-allow-origins=http://127.0.0.1"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            time.sleep(0.25)
            try:
                return self._get("/json/version")
            except requests.RequestException:
                continue
        raise RuntimeError("Chrome ne répond pas.")

    def onglets(self) -> list[dict]:
        self._pret()
        return [{"id": t["id"], "titre": t.get("title", "")[:100], "url": t.get("url", "")[:200]} for t in self._get("/json/list") if t.get("type") == "page"]

    def _onglet(self, oid: str) -> dict:
        lst = [t for t in self._get("/json/list") if t.get("type") == "page"]
        if not lst:
            raise RuntimeError("Aucun onglet ouvert.")
        t = next((x for x in lst if x["id"] == oid), None) if oid else lst[0]
        if not t:
            raise RuntimeError("Onglet introuvable : relis la liste des onglets.")
        return t

    def _eval(self, t: dict, expr: str):
        import websocket
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == 1:
                    return ((m.get("result") or {}).get("result") or {}).get("value")
        finally:
            ws.close()

    def faire(self, action: str, onglet: str = "", url: str = "", ref=None, texte: str = "", valider: bool = False) -> dict:
        self._pret()
        if action == "onglets":
            return {"ok": True, "onglets": self.onglets()}
        if action == "ouvrir":
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            t = self._get("/json/new?" + requests.utils.quote(url, safe=":/?=&%#"), "PUT")
            time.sleep(2.5)
            return {"ok": True, "onglet": t.get("id"), **(self._eval(self._onglet(t.get("id")), INSTANTANE) or {})}
        if action == "fermer":
            requests.get(f"{self.base}/json/close/{self._onglet(onglet)['id']}", timeout=5)
            return {"ok": True}
        t = self._onglet(onglet)
        if action == "lire":
            return {"ok": True, "onglet": t["id"], **(self._eval(t, INSTANTANE) or {})}
        if action in ("cliquer", "remplir"):
            if DOMAINES_PROTEGES.search(t.get("url", "")):
                return {"error": "Site protégé (banque, impôts, santé, organismes) : EVA peut le lire mais n'y clique ni n'y écrit jamais. Fais-le toi-même."}
            n = int(ref)
            if action == "cliquer":
                ok = self._eval(t, f"""((e) => {{ if (!e) return false; e.scrollIntoView({{block: 'center'}}); e.click(); return true; }})(document.querySelector('[data-eva-ref="{n}"]'))""")
            else:
                if self._eval(t, SENSIBLE.replace("REF", str(n))) == "sensible":
                    return {"error": "Champ de mot de passe, code ou carte bancaire : EVA ne le remplit jamais."}
                ok = self._eval(t, f"""((e, v) => {{ if (!e) return false; e.focus();
                    const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                    const d = Object.getOwnPropertyDescriptor(proto, 'value'); if (d && d.set && e.tagName !== 'SELECT') d.set.call(e, v); else e.value = v;
                    e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
                    {"if (e.form && e.form.requestSubmit) e.form.requestSubmit();" if valider else ""} return true; }})(document.querySelector('[data-eva-ref="{n}"]'), {json.dumps(texte)})""")
            if not ok:
                return {"error": "Élément introuvable : relis la page (les numéros changent)."}
            time.sleep(2)
            return {"ok": True, "onglet": t["id"], **(self._eval(self._onglet(t["id"]), INSTANTANE) or {})}
        return {"error": f"Action inconnue : {action}."}


# ---------------------------------------------------------------- l'écran du PC : voir et cliquer (comme Jarvis)

class Clavier:
    """Souris et clavier : Windows (API Win32), macOS (Quartz), Linux (xdotool)."""
    MANQUE = ("Pour cliquer et écrire : Windows ; macOS avec pyobjc-framework-Quartz et l'autorisation « Accessibilité » ; "
              "ou Linux avec xdotool (sudo apt install xdotool).")
    # nom : (touche X11, codes Windows, (code Mac, avec Cmd))
    TOUCHES = {"entree": ("Return", [0x0D], (36, 0)), "tab": ("Tab", [0x09], (48, 0)), "echap": ("Escape", [0x1B], (53, 0)),
               "retour": ("BackSpace", [0x08], (51, 0)), "suppr": ("Delete", [0x2E], (117, 0)), "haut": ("Up", [0x26], (126, 0)),
               "bas": ("Down", [0x28], (125, 0)), "gauche": ("Left", [0x25], (123, 0)), "droite": ("Right", [0x27], (124, 0)),
               "pageup": ("Prior", [0x21], (116, 0)), "pagedown": ("Next", [0x22], (121, 0)), "debut": ("Home", [0x24], (115, 0)),
               "fin": ("End", [0x23], (119, 0)), "ctrl+l": ("ctrl+l", [0x11, 0x4C], (37, 1)), "ctrl+t": ("ctrl+t", [0x11, 0x54], (17, 1)),
               "ctrl+w": ("ctrl+w", [0x11, 0x57], (13, 1)), "ctrl+a": ("ctrl+a", [0x11, 0x41], (0, 1)), "ctrl+c": ("ctrl+c", [0x11, 0x43], (8, 1)),
               "ctrl+v": ("ctrl+v", [0x11, 0x56], (9, 1)), "ctrl+f": ("ctrl+f", [0x11, 0x46], (3, 1)), "ctrl+s": ("ctrl+s", [0x11, 0x53], (1, 1)),
               "ctrl+z": ("ctrl+z", [0x11, 0x5A], (6, 1)), "alt+tab": ("alt+Tab", [0x12, 0x09], (48, 1)),
               "alt+gauche": ("alt+Left", [0x12, 0x25], (33, 1)), "f5": ("F5", [0x74], (15, 1)),       # Mac : Cmd+[ (retour), Cmd+R
               "windows": ("super", [0x5B], (49, 1)), "espace": ("space", [0x20], (49, 0))}           # Mac : Cmd+Espace (Spotlight)

    @staticmethod
    def possible() -> bool:
        if SYSTEME == "Windows":
            return True
        if SYSTEME == "Darwin":
            try:
                import Quartz  # noqa: F401
                return True
            except ImportError:
                return False
        return bool(shutil.which("xdotool"))

    @staticmethod
    def _mac(evts) -> None:
        import Quartz
        for e in evts:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
            time.sleep(0.01)

    @classmethod
    def clic(cls, x: float, y: float, double: bool = False) -> dict:
        if not cls.possible():
            return {"error": cls.MANQUE}
        x, y = int(x), int(y)
        if SYSTEME == "Windows":
            import ctypes
            u = ctypes.windll.user32
            u.SetCursorPos(x, y)
            for _ in range(2 if double else 1):
                u.mouse_event(2, 0, 0, 0, 0)
                u.mouse_event(4, 0, 0, 0, 0)
        elif SYSTEME == "Darwin":
            import Quartz
            pt = Quartz.CGPointMake(x, y)
            evts = [Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0)]
            for n in range(1, 3 if double else 2):
                for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
                    e = Quartz.CGEventCreateMouseEvent(None, t, pt, 0)
                    Quartz.CGEventSetIntegerValueField(e, Quartz.kCGMouseEventClickState, n)
                    evts.append(e)
            cls._mac(evts)
        else:
            _cmd(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2" if double else "1", "1"])
        return {"ok": True}

    @classmethod
    def saisir(cls, texte: str) -> dict:
        if not cls.possible():
            return {"error": cls.MANQUE}
        if SYSTEME == "Windows":
            import ctypes
            from ctypes import wintypes

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                            ("dwExtraInfo", ctypes.c_size_t)]

            class INPUT(ctypes.Structure):
                class _U(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
                _anonymous_ = ("u",)
                _fields_ = [("type", wintypes.DWORD), ("u", _U)]
            for ch in texte:
                o = ord(ch)
                codes = [o] if o < 0x10000 else [0xD800 + ((o - 0x10000) >> 10), 0xDC00 + ((o - 0x10000) & 0x3FF)]   # émojis
                for code in codes:
                    for flags in (0x0004, 0x0004 | 0x0002):              # KEYEVENTF_UNICODE, puis relâché
                        i = INPUT(type=1)
                        i.ki = KEYBDINPUT(0, code, flags, 0, 0)
                        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
        elif SYSTEME == "Darwin":
            import Quartz
            evts = []
            for ch in texte:
                for bas in (True, False):
                    e = Quartz.CGEventCreateKeyboardEvent(None, 0, bas)
                    Quartz.CGEventKeyboardSetUnicodeString(e, len(ch.encode("utf-16-le")) // 2, ch)
                    evts.append(e)
            cls._mac(evts)
        else:
            _cmd(["xdotool", "type", "--delay", "20", "--", texte])
        return {"ok": True}

    @classmethod
    def touche(cls, nom: str) -> dict:
        if not cls.possible():
            return {"error": cls.MANQUE}
        x11, codes, (mac, cmd) = cls.TOUCHES[nom]
        if SYSTEME == "Windows":
            import ctypes
            u = ctypes.windll.user32
            for c in codes:
                u.keybd_event(c, 0, 0, 0)
            for c in reversed(codes):
                u.keybd_event(c, 0, 2, 0)
        elif SYSTEME == "Darwin":
            import Quartz
            evts = []
            for bas in (True, False):
                e = Quartz.CGEventCreateKeyboardEvent(None, mac, bas)
                if cmd:
                    Quartz.CGEventSetFlags(e, Quartz.kCGEventFlagMaskCommand)
                evts.append(e)
            cls._mac(evts)
        else:
            _cmd(["xdotool", "key", x11])
        return {"ok": True}


class Ecran:
    """Capture ponctuelle de l'écran (rien n'est gardé sur le disque) : texte lu par OCR sur l'ordinateur même, image réduite
    envoyée à EVA pour la description. Le clic vise un texte VISIBLE (« Envoyer ») : EVA a demandé l'accord avant."""

    def __init__(self):
        import mss  # noqa: F401 — vérifie la présence au démarrage
        from PIL import Image  # noqa: F401
        self._ocr = None

    def _moteur(self):
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr, self._v2 = RapidOCR(), False
            except ImportError:
                from rapidocr import RapidOCR
                self._ocr, self._v2 = RapidOCR(), True
        return self._ocr

    def capture(self):
        import mss
        from PIL import Image
        with mss.mss() as sct:
            m = sct.monitors[0]                                 # tous les écrans
            brut = sct.grab(m)
            self.echelle = (brut.size[0] / m["width"]) if m.get("width") else 1.0   # 2 sur un écran Retina, 1 ailleurs
            return Image.frombytes("RGB", brut.size, brut.rgb), m["left"], m["top"]

    def lire(self, img) -> list[dict]:
        """Lignes de texte : {texte, x, y, l, h} en pixels de l'image."""
        r = self._moteur()(np.asarray(img))
        if getattr(self, "_v2", False):
            lignes = list(zip(r.boxes if r.boxes is not None else [], r.txts or [], r.scores or []))
        else:
            lignes = [(b, t, sc) for b, t, sc in (r[0] or [])]
        out = []
        for boite, texte, score in lignes:
            if float(score) < 0.5 or not str(texte).strip():
                continue
            xs, ys = [p[0] for p in boite], [p[1] for p in boite]
            out.append({"texte": str(texte).strip(), "x": min(xs), "y": min(ys), "l": max(xs) - min(xs), "h": max(ys) - min(ys)})
        out.sort(key=lambda o: (round(o["y"] / 12), o["x"]))
        return out

    @staticmethod
    def fenetre_active() -> str:
        try:
            if SYSTEME == "Windows":
                import ctypes
                u = ctypes.windll.user32
                h = u.GetForegroundWindow()
                n = u.GetWindowTextLengthW(h)
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                return b.value
            if SYSTEME == "Darwin":
                return _cmd(["osascript", "-e", 'tell application "System Events" to set p to first application process whose frontmost is true',
                             "-e", 'tell application "System Events" to try', "-e", "return (name of p) & \" - \" & (name of front window of p)",
                             "-e", "on error", "-e", "return name of p", "-e", "end try"])
            if shutil.which("xdotool"):
                return _cmd(["xdotool", "getactivewindow", "getwindowname"])
        except Exception:  # noqa: BLE001
            pass
        return ""

    def voir(self, elements: bool = False) -> dict:
        img, ox, oy = self.capture()
        lignes = []
        try:
            lignes = self.lire(img)
            texte = "\n".join(o["texte"] for o in lignes)
        except Exception as exc:  # noqa: BLE001 — sans OCR, l'image seule reste utile
            texte = f"(lecture du texte impossible : {exc})"[:200]
        if elements:                                      # mode opérateur : ce qui est visible, numéroté, avec sa position
            k = getattr(self, "echelle", 1.0) or 1.0
            els = [{"n": i + 1, "texte": o["texte"][:80], "x": int(ox + (o["x"] + o["l"] / 2) / k), "y": int(oy + (o["y"] + o["h"] / 2) / k)}
                   for i, o in enumerate(lignes[:150])]
            return {"ok": True, "fenetre": self.fenetre_active(), "elements": els, "taille": list(img.size)}
        petit = img.copy()
        petit.thumbnail((1280, 1280))
        b = io.BytesIO()
        petit.save(b, "JPEG", quality=70)
        import base64
        return {"ok": True, "texte": texte[:8000], "fenetre": self.fenetre_active(), "image": base64.b64encode(b.getvalue()).decode()}

    def _protege(self) -> str | None:
        titre = self.fenetre_active()
        return titre if DOMAINES_PROTEGES.search(titre or "") else None

    def cliquer_xy(self, x: int, y: int, double: bool = False) -> dict:
        if self._protege():
            return {"error": "Fenêtre protégée (banque, impôts, santé…) : je n'agis pas ici."}
        return Clavier.clic(x, y, double)

    def taper(self, texte: str) -> dict:
        if self._protege():
            return {"error": "Fenêtre protégée (banque, impôts, santé…) : je n'écris rien ici."}
        return Clavier.saisir(str(texte or "")[:2000])

    TOUCHES = None                                          # voir Clavier.TOUCHES

    def touche(self, nom: str) -> dict:
        nom = sans_accents(str(nom or "")).replace(" ", "")
        if nom not in Clavier.TOUCHES:
            return {"error": f"Touche inconnue : {nom}. Possibles : {', '.join(Clavier.TOUCHES)}."}
        if self._protege():
            return {"error": "Fenêtre protégée : je n'agis pas ici."}
        return Clavier.touche(nom)

    def cliquer(self, cible: str, double: bool = False) -> dict:
        if not Clavier.possible():
            return {"error": Clavier.MANQUE}
        titre = self.fenetre_active()
        if DOMAINES_PROTEGES.search(titre or ""):
            return {"error": "Fenêtre protégée (banque, impôts, santé…) : je ne clique pas ici, fais-le toi-même."}
        img, ox, oy = self.capture()
        lignes = self.lire(img)
        c = sans_accents(cible).strip(" .!«»\"'")
        if not c:
            return {"error": "Cible vide."}
        exacts = [o for o in lignes if sans_accents(o["texte"]).strip(" .!:«»\"'") == c]
        if len(exacts) > 1:
            return {"error": f"« {cible} » apparaît {len(exacts)} fois à l'écran : précise (par exemple le texte d'à côté)."}
        choix, debut, long = (exacts[0], 0, len(exacts[0]["texte"])) if exacts else (None, 0, 0)
        if not choix:
            contient = [o for o in lignes if re.search(rf"(?<!\w){re.escape(c)}(?!\w)", sans_accents(o["texte"]))]
            contient.sort(key=lambda o: len(o["texte"]))
            if not contient:
                import difflib
                proches = difflib.get_close_matches(c, [sans_accents(o["texte"]) for o in lignes], n=3, cutoff=0.8)
                if len(proches) == 1:
                    choix = next(o for o in lignes if sans_accents(o["texte"]) == proches[0])
                    debut, long = 0, len(choix["texte"])
                else:
                    return {"error": f"Je ne vois pas « {cible} » à l'écran.", "textes_visibles": [o["texte"] for o in lignes][:40]}
            else:
                choix = contient[0]
                debut, long = sans_accents(choix["texte"]).find(c), len(c)
        n = max(1, len(choix["texte"]))
        k = getattr(self, "echelle", 1.0) or 1.0
        x = ox + (choix["x"] + choix["l"] * (debut + long / 2) / n) / k          # au milieu du mot visé dans la ligne
        y = oy + (choix["y"] + choix["h"] / 2) / k
        r = Clavier.clic(x, y, double)
        return {"ok": True, "clique_sur": choix["texte"], "fenetre": titre} if r.get("ok") else r


# ---------------------------------------------------------------- fenêtre flottante (comme Jarvis)

_SILENCE = re.compile(r"^\W*(?:passe en |active le |mets le )?mode (?:silencieux|muet|discret)\W*$|^\W*tais-toi\W*$", re.I)
_PAROLE = re.compile(r"^\W*(?:reparle|parle de nouveau|parle à nouveau|mode (?:normal|vocal|parlé)|tu peux parler)\W*$", re.I)


class Fenetre:
    """Petite fenêtre toujours au premier plan, sans bordure et sans prendre le clavier : ce que tu as dit, ce qu'EVA répond.
    Tourne dans le fil principal (tkinter) ; le satellite lui envoie des messages par une file."""

    def __init__(self, position="bas-droite", duree_s: int = 15, largeur: int = 420):
        import tkinter as tk
        self.tk = tk
        self.q: queue.Queue = queue.Queue()
        self.duree_ms, self.largeur = int(duree_s) * 1000, largeur
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        cadre = tk.Frame(self.root, bg="#141a33", padx=14, pady=10, highlightthickness=1, highlightbackground="#ffc45c")
        cadre.pack(fill="both", expand=True)
        self.etat = tk.Label(cadre, text="", fg="#ffc45c", bg="#141a33", font=("Segoe UI", 9, "bold"), anchor="w")
        self.etat.pack(fill="x")
        self.toi = tk.Label(cadre, text="", fg="#b9c3e6", bg="#141a33", font=("Segoe UI", 10), wraplength=largeur - 30, justify="left", anchor="w")
        self.toi.pack(fill="x")
        self.eva = tk.Label(cadre, text="", fg="#ffffff", bg="#141a33", font=("Segoe UI", 11), wraplength=largeur - 30, justify="left", anchor="w")
        self.eva.pack(fill="x", pady=(4, 0))
        self.tuiles = tk.Frame(cadre, bg="#141a33")              # tableau au repos (tuiles), sous la conversation
        self.horloge = tk.Label(cadre, text="", fg="#ffc45c", bg="#141a33", font=("Segoe UI", 20, "bold"), anchor="w")
        for w in (cadre, self.etat, self.toi, self.eva, self.tuiles, self.horloge):
            w.bind("<Button-1>", lambda _e: self.cacher(clic=True))
        self.position = position
        self._minuteur = None
        self.repos = False               # le tableau est affiché
        self.tableau = None              # dernières tuiles reçues (None : tableau désactivé)
        self.masque_jusqua = 0.0
        if SYSTEME == "Windows":                                # ne jamais voler le clavier à l'appli en cours
            self.root.after(50, self._sans_focus)
        self.root.after(100, self._lire_file)

    def _sans_focus(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)   # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        except Exception:  # noqa: BLE001
            pass

    def _placer(self):
        self.root.update_idletasks()
        w, h = self.largeur, self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        p = self.position
        if isinstance(p, (list, tuple)) and len(p) == 2:          # coordonnées libres : un 2e écran, par exemple [2000, 900]
            x, y = int(p[0]), int(p[1])
        else:
            x = 20 if "gauche" in str(p) else sw - w - 20
            y = 20 if "haut" in str(p) else sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _lire_file(self):
        try:
            while True:
                genre, texte = self.q.get_nowait()
                if genre == "tableau":
                    self.tableau = texte
                    if self.repos:
                        self._dessiner_tableau()
                    elif not self.root.winfo_viewable():
                        self.au_repos()
                    continue
                self._quitter_repos()
                if genre == "etat":
                    self.etat.config(text=texte)
                elif genre == "toi":
                    self.toi.config(text=f"Toi : {texte}")
                    self.eva.config(text="")
                elif genre == "eva":
                    self.eva.config(text=texte[:700])
                self.montrer()
        except queue.Empty:
            pass
        self.root.after(100, self._lire_file)

    def montrer(self):
        self._placer()
        self.root.deiconify()
        self.root.lift()
        if self._minuteur:
            self.root.after_cancel(self._minuteur)
        self._minuteur = self.root.after(self.duree_ms, self.cacher)

    def cacher(self, clic: bool = False):
        if clic and self.repos:
            self.masque_jusqua = time.time() + 1800              # un clic sur le tableau : caché 30 minutes
        if not clic and self.tableau is not None and time.time() >= self.masque_jusqua:
            self.au_repos()                                     # fin de conversation : retour au tableau
            return
        self._quitter_repos()
        self.root.withdraw()

    # ---- tableau au repos (comme le HUD de Jarvis) : heure, météo, agenda, colis, musique, post-its
    def au_repos(self):
        if self.tableau is None or time.time() < self.masque_jusqua:
            return
        self.repos = True
        for w in (self.etat, self.toi, self.eva):
            w.pack_forget()
        self.horloge.pack(fill="x")
        self.tuiles.pack(fill="x")
        self._dessiner_tableau()
        self._tic()
        self._placer()
        self.root.deiconify()

    def _quitter_repos(self):
        if not self.repos:
            return
        self.repos = False
        self.horloge.pack_forget()
        self.tuiles.pack_forget()
        self.etat.pack(fill="x")
        self.toi.pack(fill="x")
        self.eva.pack(fill="x", pady=(4, 0))

    def _tic(self):
        if not self.repos:
            return
        self.horloge.config(text=time.strftime("%H:%M"))
        self.root.after(15000, self._tic)

    def _dessiner_tableau(self):
        tk = self.tk
        for w in self.tuiles.winfo_children():
            w.destroy()
        for t in (self.tableau or {}).get("tuiles", [])[:5]:
            bloc = tk.Frame(self.tuiles, bg="#1c2447", padx=8, pady=4)
            bloc.pack(fill="x", pady=2)
            tk.Label(bloc, text=f"{t.get('icone', '')} {t.get('titre', '')}", fg="#ffc45c", bg="#1c2447", font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(fill="x")
            for ligne in t.get("lignes", [])[:3]:
                tk.Label(bloc, text=ligne, fg="#ffffff", bg="#1c2447", font=("Segoe UI", 10), anchor="w", justify="left",
                         wraplength=self.largeur - 40).pack(fill="x")
            for w in (bloc, *bloc.winfo_children()):
                w.bind("<Button-1>", lambda _e: self.cacher(clic=True))
        if self.repos:
            self._placer()

    def afficher(self, genre: str, texte: str):
        self.q.put((genre, texte))

    def boucle(self):
        self.root.mainloop()

class Micro:
    """Capture continue + détection de parole par l'énergie (comme l'interface web d'EVA)."""

    def __init__(self, appareil=None, seuil=None, eveil: "EveilLocal | None" = None):
        self.eveil = eveil
        self.q: queue.Queue = queue.Queue()
        self.muet = False
        self.seuil_fixe = seuil
        self.seuil = seuil or 400.0
        self.flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=TRAME, device=appareil, callback=self._cb)

    def _cb(self, data, _frames, _t, statut):
        if not self.muet:
            self.q.put(data[:, 0].copy())

    def demarrer(self):
        self.flux.start()
        if not self.seuil_fixe:
            niveaux = [self._rms(self.q.get()) for _ in range(50)]          # 1,5 s de bruit de fond
            self.seuil = max(np.median(niveaux) * 3.0, 250.0)
        log(f"Micro prêt (seuil de parole {self.seuil:.0f}).")

    @staticmethod
    def _rms(t: np.ndarray) -> float:
        return float(np.sqrt(np.mean(t.astype(np.float32) ** 2))) if len(t) else 0.0

    def vider(self):
        while not self.q.empty():
            self.q.get_nowait()

    def phrase(self, attente_max_s: float | None = None):
        """Attend une phrase complète ; None si rien n'est dit avant attente_max_s."""
        avant = deque(maxlen=PREROLL_MS // 30)
        debut = time.time()
        voix, silence, parle = [], 0, 0
        while True:
            try:
                t = self.q.get(timeout=0.5)
            except queue.Empty:
                t = None
            if not voix and attente_max_s and time.time() - debut > attente_max_s:
                return None
            if t is None:
                continue
            if self.eveil is not None:
                self.eveil.ecouter(t)
            n = self._rms(t)
            self.niveau_recent = max(n, getattr(self, "niveau_recent", 0.0) * 0.995)
            fort = n > self.seuil
            if not voix:
                avant.append(t)
                parle = parle + 1 if fort else 0
                if parle >= 3:
                    voix = list(avant)
                continue
            voix.append(t)
            silence = 0 if fort else silence + 1
            duree = len(voix) * 30
            if silence * 30 >= FIN_SILENCE_MS or duree >= MAX_PAROLE_MS:
                if duree - silence * 30 >= MIN_PAROLE_MS:
                    return np.concatenate(voix)
                voix, silence, parle = [], 0, 0
                avant.clear()

    def enregistrer(self, secondes: float) -> np.ndarray:
        self.vider()
        morceaux, fin = [], time.time() + secondes
        while time.time() < fin:
            try:
                morceaux.append(self.q.get(timeout=0.5))
            except queue.Empty:
                pass
        return np.concatenate(morceaux) if morceaux else np.zeros(0, dtype=np.int16)


def nettoyer(texte: str) -> str:
    """Texte prêt à être dit : sans markdown, liens, emoji ; heures « 14:30 » → « 14 h 30 »."""
    texte = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", texte or "")
    texte = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texte)
    texte = re.sub(r"https?://\S+", " lien ", texte)
    texte = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{int(m[1])} h {m[2]}" if m[2] != "00" else f"{int(m[1])} h", texte)
    texte = re.sub(r"(\d)\s?€", r"\1 euros", texte)
    texte = re.sub(r"(\d)\s?°C\b", r"\1 degrés", texte)
    texte = re.sub(r"(\d)\s?%", r"\1 pour cent", texte)
    texte = re.sub(r"[*_#`>|~]", "", texte)
    texte = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", texte)
    return re.sub(r"\s*\n+\s*", ". ", texte).strip()


class Parole:
    """Lit des phrases à la suite, sans blanc : la phrase suivante est synthétisée pendant que la précédente est jouée
    (comme le « streaming phrase par phrase » de Jarvis). Le micro est coupé pendant toute la lecture (pas d'écho)."""

    def __init__(self, sat: "Satellite"):
        self.sat = sat
        self.textes: queue.Queue = queue.Queue()
        self.sons: queue.Queue = queue.Queue(maxsize=2)
        self.generation = 0
        threading.Thread(target=self._synthese, daemon=True).start()
        threading.Thread(target=self._lecture, daemon=True).start()

    def dire(self, texte: str) -> None:
        t = nettoyer(texte)
        if t:
            self.textes.put((self.generation, t))

    def attendre(self) -> None:
        self.textes.join()
        self.sons.join()
        if self.sat.micro.muet:                                  # filet de sécurité : le micro ne reste jamais coupé
            time.sleep(0.4)
            self.sat.micro.vider()
            self.sat.micro.muet = False

    def couper(self) -> None:
        """« Stop » (poing devant la caméra) : on jette ce qui reste à dire."""
        self.generation += 1
        try:
            sd.stop()
        except Exception:  # noqa: BLE001
            pass

    def _synthese(self):
        while True:
            gen, t = self.textes.get()
            try:
                if gen == self.generation:
                    pcm, taux = self.sat.eva.voix(t[:900])
                    if gen == self.generation:
                        self.sons.put((gen, pcm, taux))
            except Exception as exc:  # noqa: BLE001
                log("Synthèse vocale impossible :", exc)
            finally:
                self.textes.task_done()

    def _lecture(self):
        while True:
            gen, pcm, taux = self.sons.get()
            try:
                if gen == self.generation:
                    with self.sat._parole:
                        self.sat.micro.muet = True
                        sd.play(pcm, taux, device=self.sat.sortie)
                        sd.wait()
                if self.sons.empty() and self.textes.unfinished_tasks == 0:
                    time.sleep(0.4)                              # pas d'écho de sa propre voix
                    self.sat.micro.vider()
                    self.sat.micro.muet = False
            except Exception as exc:  # noqa: BLE001
                log("Lecture impossible :", exc)
                self.sat.micro.muet = False
            finally:
                self.sons.task_done()


class Satellite:
    def __init__(self, eva: Eva, micro: Micro, sortie=None, pc: "Ordinateur | None" = None, fenetre: "Fenetre | None" = None,
                 silencieux: bool = False, ecran: "Ecran | None" = None, gestes: bool = False):
        self.eva, self.micro, self.sortie, self.pc, self.fenetre, self.ecran = eva, micro, sortie, pc, fenetre, ecran
        self.silencieux = silencieux and fenetre is not None          # mode silencieux : seulement affiché, jamais sans fenêtre
        self.gestes = gestes
        self._parole = threading.Lock()
        self.parole = Parole(self)
        self.reponse_geste: queue.Queue = queue.Queue()               # pouce levé / baissé pendant une question
        self.attend_reponse = False
        self.pause_eva = False                                        # écoute coupée depuis EVA (Maison › Satellites)
        self.fichier_pause = Path(__file__).resolve().parent / "pause"   # écoute coupée sur l'ordinateur (raccourci « EVA pause »)
        self._etait_en_pause = False
        self.ptt = False                                              # « Parler maintenant » (icône) : pas besoin de dire « EVA »
        self.diag: dict = {"demarre": time.time(), "phrases": 0, "transcrites": 0, "eveils": 0, "commandes": 0}

    def diagnostic(self) -> dict:
        m = self.micro
        return {**self.diag, "version": VERSION, "systeme": SYSTEME, "en_pause": self.en_pause(),
                "micro": {"seuil": round(m.seuil), "niveau_recent": round(getattr(m, "niveau_recent", 0.0)),
                          "eveil_local": m.eveil is not None, "muet": bool(getattr(m, "muet", False))},
                "journal": list(_JOURNAL)[-60:]}

    def test_micro(self) -> dict:
        """Teste le haut-parleur (phrase dite) puis le micro (4 s d'écoute) : niveau entendu et texte compris."""
        self.dire("Test du satellite. Après le bip, dis une phrase.")
        self.bip()
        pcm = self.micro.enregistrer(4)
        lvl = niveau(pcm)
        try:
            texte = self.eva.transcrire(pcm) if len(pcm) else ""
        except Exception as exc:  # noqa: BLE001
            texte = f"(reconnaissance impossible : {exc})"
        log(f"Test micro : niveau {lvl:.0f} (seuil {self.micro.seuil:.0f}), compris : {texte!r}")
        return {"ok": True, "niveau": round(lvl), "seuil": round(self.micro.seuil), "entendu": lvl > self.micro.seuil,
                "texte": texte, "mot_eveil": commande_apres_eveil(texte) is not None}

    def basculer_pause(self) -> bool:
        """Pause / reprise sur l'ordinateur (icône, raccourcis) ; la pause décidée dans EVA se lève depuis EVA."""
        if self.fichier_pause.exists():
            self.fichier_pause.unlink()
        else:
            self.fichier_pause.touch()
        return self.en_pause()

    def controle(self, action: str) -> dict:
        """Redémarrer / arrêter le programme du satellite (depuis l'icône ou depuis EVA)."""
        if action == "redemarrer":
            log("Redémarrage demandé.")
            threading.Timer(1.0, MiseAJour.relancer).start()
            return {"ok": True, "info": "Le satellite redémarre."}
        if action == "arreter":
            if SYSTEME == "Windows":
                arret_volontaire(Path(__file__).resolve().parent)
            log("Arrêt demandé : le satellite repartira à la prochaine ouverture de session (ou raccourci « EVA démarrer »).")
            threading.Timer(1.0, lambda: os._exit(0)).start()
            return {"ok": True, "info": "Satellite arrêté : il repartira à la prochaine ouverture de session, ou avec le raccourci « EVA démarrer »."}
        if action == "parler":
            self.ptt = True
            return {"ok": True}
        return {"error": "Action inconnue (redemarrer, arreter, parler)."}

    def en_pause(self) -> bool:
        return self.pause_eva or self.fichier_pause.exists()

    def jouer(self, pcm: np.ndarray, taux: int):
        with self._parole:
            self.micro.muet = True
            try:
                sd.play(pcm, taux, device=self.sortie)
                sd.wait()
            finally:
                time.sleep(0.4)                       # pas d'écho de sa propre voix
                self.micro.vider()
                self.micro.muet = False

    def bip(self, freq=880, duree=0.12):
        t = np.arange(int(TAUX * duree)) / TAUX
        env = np.minimum(1, np.minimum(t, duree - t) * 40)
        self.jouer((np.sin(2 * math.pi * freq * t) * env * 6000).astype(np.int16), TAUX)

    def afficher(self, genre: str, texte: str):
        if self.fenetre:
            self.fenetre.afficher(genre, texte)

    def dire(self, texte: str, afficher: bool = True, attendre: bool = True):
        t = nettoyer(texte)
        if not t:
            return
        log("EVA :", t)
        if afficher and self.fenetre:
            self.fenetre.afficher("etat", "EVA")
            self.fenetre.afficher("eva", texte)
        if self.silencieux:
            return
        self.parole.dire(t)
        if attendre:
            self.parole.attendre()

    def ecouter_texte(self, attente_s: float):
        pcm = self.micro.phrase(attente_s)
        if pcm is None:
            return None
        t = self.eva.transcrire(pcm)
        return None if hallucination(t) else t

    def _oui_non(self) -> str:
        """Réponse à une question d'accord : à voix haute, ou pouce levé / baissé devant la caméra."""
        self.attend_reponse = True
        while not self.reponse_geste.empty():
            self.reponse_geste.get_nowait()
        try:
            if self.gestes:
                fin = time.time() + 10
                while time.time() < fin:
                    try:
                        return self.reponse_geste.get_nowait()
                    except queue.Empty:
                        pass
                    t = self.ecouter_texte(1.5) if not self.micro.muet else None
                    if t:
                        return t
                return "non"
            return self.ecouter_texte(10) or "non"
        finally:
            self.attend_reponse = False

    def _derouler(self, evenements) -> dict | None:
        """Dit au fil de l'eau ce qu'EVA envoie ; rend la question d'accord éventuelle (sinon None quand c'est fini)."""
        dit = False
        for ev in evenements:
            if "attente" in ev and "question" not in ev:
                log("EVA (attente) :", ev["attente"])
                self.afficher("etat", ev["attente"])
                if not self.silencieux:
                    self.parole.dire(ev["attente"])
            elif "dire" in ev:
                if not dit:
                    self.afficher("etat", "EVA")
                dit = True
                log("EVA :", ev["dire"])
                if not self.silencieux:
                    self.parole.dire(ev["dire"])
            elif "question" in ev:
                self.parole.attendre()
                return ev
            elif "reponse" in ev:
                self.afficher("etat", "EVA")
                self.afficher("eva", ev["reponse"])
                if ev.get("dire_aussi") or not dit:
                    self.dire(ev["reponse"], afficher=False, attendre=False)
                if ev.get("erreur"):
                    log("Erreur côté EVA :", ev["erreur"])
                break
        self.parole.attendre()
        return None

    def traiter(self, commande: str):
        log("Toi :", commande)
        if self.fenetre:
            self.fenetre.afficher("toi", commande)
            self.fenetre.afficher("etat", "Je réfléchis…")
            if _SILENCE.match(commande) or _PAROLE.match(commande):
                self.silencieux = bool(_SILENCE.match(commande))
                self.fenetre.afficher("eva", "Mode silencieux : je réponds seulement ici." if self.silencieux else "Je parle de nouveau.")
                if not self.silencieux:
                    self.dire("Je parle de nouveau.")
                return
        if _PAUSE.match(commande):
            self.fichier_pause.touch()
            self.dire("Je me mets en pause. Pour me réactiver : le raccourci « EVA reprise », ou Maison, Satellites, dans EVA.")
            return
        if _MUSIQUE.search(commande):
            self.dire("J'écoute.")
            r = self.eva.musique(self.micro.enregistrer(ECOUTE_MUSIQUE_S))
            self.dire(r.get("phrase", "Je n'ai pas reconnu ce morceau."))
            return
        q = self._derouler(self.eva.demander_flux(commande))
        for _ in range(4):                               # une ou plusieurs demandes d'accord
            if not q:
                break
            self.dire(q["question"])
            self.bip(660)
            oui_non = self._oui_non()
            log("Accord :", oui_non)
            q = self._derouler(self.eva.repondre_flux(oui_non))

    def geste(self, a: tuple):
        """Ce que la caméra a reconnu et qui concerne EVA (le reste — touches, souris — est déjà fait par gestes.py)."""
        if a[0] == "stop":
            self.parole.couper()
            self.afficher("etat", "✋ Je me tais.")
        elif a[0] == "reponse" and self.attend_reponse:
            self.reponse_geste.put(a[1])
            self.afficher("etat", "👍 Oui" if a[1] == "oui" else "👎 Non")
        elif a[0] == "mode":
            self.afficher("etat", {"onglets": "🗂 Mode onglets", "audio": "🔊 Mode audio", "souris": "🖱 Mode souris"}.get(a[1], "Mode terminé"))
        elif a[0] == "erreur":
            log("Gestes :", a[1])

    def infos(self) -> dict:
        cap = ["dire"] + (["pc"] if self.pc else []) + (["chrome"] if self.pc and _chemin_chrome() else []) + \
              (["ecran"] if self.ecran else []) + (["gestes"] if self.gestes else []) + (["tableau"] if self.fenetre and self.fenetre.tableau is not None else [])
        return {"capacites": cap, "systeme": SYSTEME, "applis": sorted(self.pc.applis) if self.pc else [], "version": VERSION,
                "en_pause": self.en_pause()}

    def _ordres(self):
        """Écoute les ordres d'EVA : annonce à voix haute, pilotage de l'ordinateur, écran."""
        while True:
            try:
                for o in self.eva.ordres():
                    try:
                        if o.get("type") == "desinstaller":
                            log("EVA a retiré ce satellite : désinstallation.")
                            res = desinstaller(Path(__file__).resolve().parent)
                            self.eva.resultat(o.get("id", ""), res)
                            time.sleep(1)
                            os._exit(0)
                        if o.get("type") == "diagnostic":
                            self.eva.resultat(o.get("id", ""), {"ok": True, **self.diagnostic()})
                            continue
                        if o.get("type") == "test_micro":
                            self.eva.resultat(o.get("id", ""), self.test_micro())
                            continue
                        if o.get("type") == "controle":
                            self.eva.resultat(o.get("id", ""), self.controle(str(o.get("action", ""))))
                            continue
                        if o.get("type") == "ecoute":
                            self.pause_eva = not bool(o.get("actif", True))
                            log("Écoute", "en pause (depuis EVA)" if self.pause_eva else "réactivée (depuis EVA)")
                            self.afficher("etat", "⏸ En pause" if self.en_pause() else "Dis « EVA… »")
                            self.eva.resultat(o.get("id", ""), {"ok": True, "en_pause": self.en_pause()})
                            continue
                        if o.get("type") == "dire":
                            self.bip(1046, 0.15)
                            self.dire(o.get("texte", ""))
                            res = {"ok": True}
                        elif o.get("type") == "chrome" and self.pc:
                            log("Chrome :", o.get("action"), o.get("url", ""))
                            res = ChromePC().faire(o.get("action", ""), o.get("onglet", ""), o.get("url", ""), o.get("ref"),
                                                   o.get("texte", ""), bool(o.get("valider")))
                        elif o.get("type") == "pc" and self.pc:
                            log("Ordre :", o.get("action"), o.get("valeur", ""))
                            res = self.pc.faire(o.get("action", ""), o.get("valeur", ""))
                        elif o.get("type") == "ecran" and self.ecran:
                            log("Écran :", o.get("action"), o.get("cible", ""))
                            a = o.get("action")
                            if a == "voir":
                                res = self.ecran.voir()
                            elif a == "elements":
                                res = self.ecran.voir(elements=True)
                            elif a == "cliquer_xy":
                                res = self.ecran.cliquer_xy(int(o.get("x", 0)), int(o.get("y", 0)), bool(o.get("double")))
                            elif a == "taper":
                                res = self.ecran.taper(str(o.get("texte", "")))
                            elif a == "touche":
                                res = self.ecran.touche(str(o.get("touche", "")))
                            else:
                                res = self.ecran.cliquer(str(o.get("cible", "")), bool(o.get("double")))
                            if a in ("cliquer_xy", "taper", "touche"):
                                self.afficher("etat", f"🤖 EVA agit : {a.replace('_xy', '')} {o.get('texte') or o.get('touche') or ''}"[:80])
                        else:
                            res = {"error": "Ordre non pris en charge par ce satellite."}
                    except Exception as exc:  # noqa: BLE001
                        res = {"error": f"{type(exc).__name__} : {exc}"[:200]}
                    self.eva.resultat(o.get("id", ""), res)
            except SystemExit:
                raise
            except Exception:  # noqa: BLE001 — EVA redémarre, réseau coupé… on réessaie
                time.sleep(5)

    def _tableau(self):
        while True:
            try:
                d = self.eva.tableau()
                if d:
                    self.fenetre.afficher("tableau", d)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(300)

    def boucle(self):
        info = self.eva.bonjour(self.infos())
        self.pause_eva = bool(info.get("pause"))
        log(f"Connecté à EVA : satellite « {info['nom']} »{' (' + info['piece'] + ')' if info.get('piece') else ''}. Dis « EVA… ».")
        threading.Thread(target=self._signes_de_vie, daemon=True).start()
        threading.Thread(target=self._ordres, daemon=True).start()
        if self.fenetre and self.fenetre.tableau is not None:
            threading.Thread(target=self._tableau, daemon=True).start()
        self.micro.demarrer()
        eveille_jusqua = 0.0
        while True:
            try:
                if self.ptt:                                 # « Parler maintenant » : la phrase suivante, sans « EVA »
                    self.ptt = False
                    self.bip()
                    self.micro.vider()
                    pcm = self.micro.phrase(attente_max_s=8)
                    texte = self.eva.transcrire(pcm) if pcm is not None else ""
                    if texte and not hallucination(texte):
                        self.traiter(commande_apres_eveil(texte) or texte)
                    continue
                if self.en_pause():
                    if not self._etait_en_pause:
                        self._etait_en_pause = True
                        log("En pause : je n'écoute plus (raccourci « EVA reprise », ou Maison › Satellites dans EVA).")
                        self.afficher("etat", "⏸ En pause")
                    time.sleep(1)
                    self.micro.vider()                       # rien n'est gardé ni envoyé pendant la pause
                    continue
                if self._etait_en_pause:
                    self._etait_en_pause = False
                    log("Écoute réactivée.")
                    self.afficher("etat", "Dis « EVA… »")
                pcm = self.micro.phrase(attente_max_s=2)
                if pcm is None:
                    continue
                self.diag["phrases"] += 1
                self.diag["derniere_voix"] = time.time()
                ev = self.micro.eveil
                if ev is not None and time.time() >= eveille_jusqua and time.time() - ev.dernier > len(pcm) / TAUX + 2:
                    continue                                 # éveil local : pas de « EVA » entendu, la phrase ne quitte pas la pièce
                suite = time.time() < eveille_jusqua
                # Plusieurs satellites ont entendu : seul celui qui entend le mieux (parole / bruit de fond) continue.
                if not self.eva.eveil(niveau(pcm) / max(self.micro.seuil, 1.0), suite):
                    log("Un autre satellite m'entend mieux : c'est lui qui répond.")
                    continue
                texte = self.eva.transcrire(pcm, rapide=not suite)       # 1) repérer « EVA » vite (petit modèle)
                if not suite and commande_apres_eveil(texte):          # 2) « EVA, … » : la demande retranscrite avec le grand modèle
                    juste = self.eva.transcrire(pcm)
                    if juste and not hallucination(juste):
                        texte = juste if commande_apres_eveil(juste) is not None else "EVA, " + juste
                self.diag["transcrites"] += 1
                self.diag["dernier_texte"] = texte
                if hallucination(texte):
                    continue
                if suite:
                    commande = commande_apres_eveil(texte) or texte
                else:
                    commande = commande_apres_eveil(texte)
                    if commande is None and ev is not None and len(texte.split()) > 1:
                        commande = texte                     # « EVA » entendu par le détecteur, mal transcrit par Whisper
                    if commande is None:
                        log(f"Entendu sans « EVA » au début (ignoré) : {texte!r}")
                        continue
                    self.diag["eveils"] += 1
                    if not commande:
                        self.bip()
                        eveille_jusqua = time.time() + EVEIL_MS / 1000
                        continue
                eveille_jusqua = 0.0
                self.diag["commandes"] += 1
                self.traiter(commande)
            except requests.RequestException as exc:
                log("EVA injoignable :", exc)
                self.diag["derniere_erreur"] = f"{time.strftime('%H:%M')} EVA injoignable : {exc}"[:300]
                time.sleep(3)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 — un satellite ne s'arrête pas pour une erreur passagère
                log("Erreur :", exc)
                self.diag["derniere_erreur"] = f"{time.strftime('%H:%M')} {type(exc).__name__} : {exc}"[:300]
                time.sleep(1)

    def _signes_de_vie(self):
        while True:
            time.sleep(60)
            try:
                self.pause_eva = bool(self.eva.bonjour(self.infos()).get("pause", self.pause_eva))
            except Exception:  # noqa: BLE001
                pass


def normaliser(pcm: np.ndarray) -> np.ndarray:
    """Voix trop faible (micro loin, gain bas) : on la remonte avant la reconnaissance, sans saturer."""
    if pcm is None or not len(pcm):
        return pcm
    crete = float(np.percentile(np.abs(pcm.astype(np.float32)), 99.5))
    if crete < 1:
        return pcm
    gain = min(8.0, 12000.0 / crete)
    if gain <= 1.2:
        return pcm
    return np.clip(pcm.astype(np.float32) * gain, -32000, 32000).astype(np.int16)


def niveau(pcm: np.ndarray) -> float:
    """Force de la parole : 90e centile de l'énergie par tranche de 30 ms (les silences ne comptent pas)."""
    if len(pcm) < TRAME:
        return 0.0
    n = len(pcm) // TRAME
    t = pcm[:n * TRAME].astype(np.float32).reshape(n, TRAME)
    return float(np.percentile(np.sqrt((t ** 2).mean(axis=1)), 90))


# ---------------------------------------------------------------- icône à côté de l'horloge (Windows, Linux)

class Icone:
    """Petite icône EVA dans la zone de notification : Parler, Pause / Reprendre, Redémarrer, Arrêter, Ouvrir EVA.
    Facultative (module pystray) ; sur Mac, ce sont les raccourcis du bureau qui font ce travail."""

    def __init__(self, sat: "Satellite", url_eva: str):
        import pystray
        from PIL import Image, ImageDraw
        self.pystray, self.sat, self.url = pystray, sat, url_eva

        def image(couleur):
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.ellipse((6, 6, 58, 58), fill=couleur)
            d.ellipse((24, 24, 40, 40), fill=(27, 31, 59, 255))
            return im
        self.img_ok, self.img_pause = image((255, 200, 87, 255)), image((140, 140, 150, 255))
        M = pystray.MenuItem
        self.icone = pystray.Icon("eva-satellite", self.img_ok, "Satellite EVA", menu=pystray.Menu(
            M(lambda _i: "⏸ En pause" if sat.en_pause() else "🎙 EVA écoute", None, enabled=False),
            M("Parler maintenant", lambda: sat.controle("parler"), default=True),
            M(lambda _i: "Reprendre l'écoute" if sat.en_pause() else "Mettre en pause", self._pause),
            M("Ouvrir EVA", lambda: webbrowser.open(self.url)),
            pystray.Menu.SEPARATOR,
            M("Redémarrer le satellite", lambda: sat.controle("redemarrer")),
            M("Arrêter le satellite", lambda: sat.controle("arreter")),
        ))
        threading.Thread(target=self._suivre, daemon=True).start()

    def _pause(self):
        self.sat.basculer_pause()
        self._maj()

    def _maj(self):
        p = self.sat.en_pause()
        self.icone.icon = self.img_pause if p else self.img_ok
        self.icone.title = "Satellite EVA — en pause" if p else "Satellite EVA — dis « EVA… »"
        try:
            self.icone.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def _suivre(self):
        avant = None
        while True:
            time.sleep(2)
            if self.sat.en_pause() != avant:
                avant = self.sat.en_pause()
                self._maj()

    def demarrer(self):
        threading.Thread(target=self.icone.run, daemon=True).start()


# ---------------------------------------------------------------- désinstallation (demandée depuis EVA)

def desinstaller(dossier: Path) -> dict:
    """Retire le satellite de cet ordinateur : lancement automatique, puis (après l'arrêt) son dossier. Demandé quand on le
    supprime dans EVA (Maison › Satellites). Ce qui demande un mot de passe administrateur est signalé, pas forcé."""
    import subprocess
    dossier = Path(dossier).resolve()
    fait, reste = [], []
    if SYSTEME == "Windows":
        demarrage = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "eva-satellite.cmd"
        if demarrage.exists():
            demarrage.unlink()
            fait.append("lancement au démarrage retiré")
        r = subprocess.run(["schtasks", "/Delete", "/TN", "EVA Satellite", "/F"], capture_output=True)   # installé en administrateur
        if r.returncode == 0:
            fait.append("tâche « EVA Satellite » (droits administrateur) retirée")
        bureau = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        for n in ("EVA pause.cmd", "EVA reprise.cmd", "EVA démarrer.cmd", "EVA arrêter.cmd"):
            try:
                (bureau / n).unlink()
            except OSError:
                pass
        # le dossier ne peut pas s'effacer pendant que Python tourne : une commande détachée le fait 5 s après l'arrêt
        subprocess.Popen(f'cmd /c timeout /t 5 /nobreak >nul & rmdir /s /q "{dossier}"', shell=True,
                         creationflags=0x00000008 | 0x00000200)        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    elif SYSTEME == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "fr.eva.satellite.plist"
        if plist.exists():
            plist.unlink()
            fait.append("lancement à l'ouverture de session retiré")
        subprocess.Popen(["/bin/sh", "-c", f'sleep 3; rm -rf "{dossier}"; launchctl remove fr.eva.satellite'], start_new_session=True)
    else:
        bureau = Path.home() / ".config" / "autostart" / "eva-satellite.desktop"
        if bureau.exists():
            bureau.unlink()
            fait.append("lancement à l'ouverture de session retiré")
        if Path("/etc/systemd/system/eva-satellite.service").exists():
            r = subprocess.run(["sudo", "-n", "sh", "-c", "systemctl disable eva-satellite && rm -f /etc/systemd/system/eva-satellite.service "
                                "&& systemctl daemon-reload"], capture_output=True)
            if r.returncode == 0:
                fait.append("service au démarrage retiré")
                subprocess.Popen(["/bin/sh", "-c", f'sleep 3; rm -rf "{dossier}"; sudo -n systemctl stop eva-satellite'], start_new_session=True)
            else:
                reste.append("service système : lance « bash desinstaller.sh » (mot de passe administrateur)")
                try:
                    conf = dossier / "satellite.json"
                    d = json.loads(conf.read_text(encoding="utf-8-sig")) if conf.exists() else {}
                    d["retire"] = True                          # relancé par le service : il restera en sommeil, sans rien écouter
                    conf.write_text(json.dumps(d, indent=1), encoding="utf-8")
                except OSError:
                    pass
                return {"ok": True, "fait": fait, "reste": reste}
        else:
            subprocess.Popen(["/bin/sh", "-c", f'sleep 3; rm -rf "{dossier}"'], start_new_session=True)
    fait.append("dossier effacé à l'arrêt")
    return {"ok": True, "fait": fait, "reste": reste}


# ---------------------------------------------------------------- mise à jour automatique depuis EVA

def _num_version(v) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3])


class MiseAJour:
    """Le satellite se met à jour tout seul quand EVA a une version plus récente (au démarrage, puis toutes les 6 h) :
    télécharge satellite.py et gestes.py, vérifie qu'ils se compilent, garde l'ancienne version, installe les modules
    qui manquent pour les options choisies, puis se relance. Rien à refaire à la main après une mise à jour d'EVA."""
    PAQUETS = {"ecran": [("mss", "mss"), ("PIL", "pillow"), ("rapidocr_onnxruntime", "rapidocr_onnxruntime")],
               "gestes": [("mediapipe", "mediapipe"), ("cv2", "opencv-python")]}

    def __init__(self, eva: "Eva", dossier: Path, options: dict):
        self.eva, self.dossier, self.options = eva, Path(dossier), options

    def dependances(self) -> None:
        import importlib.util
        import subprocess
        manque = []
        for opt, paquets in self.PAQUETS.items():
            if self.options.get(opt):
                manque += [pip for mod, pip in paquets if importlib.util.find_spec(mod) is None]
        if (self.options.get("ecran") or self.options.get("fenetre")) and SYSTEME in ("Windows", "Linux") \
                and importlib.util.find_spec("pystray") is None:
            manque.append("pystray")
        if self.options.get("ecran") and SYSTEME == "Darwin" and importlib.util.find_spec("Quartz") is None:
            manque.append("pyobjc-framework-Quartz")
        if manque:
            log("Installation des modules manquants :", ", ".join(manque))
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", *manque], check=False)

    def verifier(self) -> bool:
        try:
            r = self.eva.s.get(self.eva.url + "/api/public/satellite/version", timeout=15, verify=self.eva.verif)
            if r.status_code != 200:
                return False
            nouvelle = r.json().get("version", "")
            if _num_version(nouvelle) <= _num_version(VERSION):
                return False
            fichiers = {}
            for nom in ("satellite.py", "gestes.py"):
                f = self.eva.s.get(self.eva.url + "/api/public/satellite/" + nom, timeout=60, verify=self.eva.verif)
                f.raise_for_status()
                compile(f.content, nom, "exec")                  # un fichier abîmé ne remplace jamais celui qui marche
                fichiers[nom] = f.content
        except Exception as exc:  # noqa: BLE001 — on réessaiera plus tard
            log("Mise à jour du satellite impossible pour l'instant :", exc)
            return False
        for nom, contenu in fichiers.items():
            cible = self.dossier / nom
            if cible.is_file():
                shutil.copy2(cible, self.dossier / (nom[:-3] + ".ancien.py"))
            tmp = self.dossier / (nom + ".nouveau")
            tmp.write_bytes(contenu)
            os.replace(tmp, cible)
        log(f"Satellite mis à jour : {VERSION} → {nouvelle}. Je redémarre.")
        return True

    @staticmethod
    def relancer() -> None:
        """Relance le programme. Sous Windows, os.execv laisse mourir le satellite lancé par la tâche planifiée
        (le lanceur du venv et la tâche se terminent avec lui) : on confie la relance à un petit programme
        détaché qui attend que celui-ci soit fermé, relance la tâche « EVA Satellite » (ou pythonw à défaut)."""
        if SYSTEME != "Windows":
            os.execv(sys.executable, [sys.executable] + sys.argv)
        import subprocess
        ici = Path(__file__).resolve().parent
        py = Path(sys.executable)
        if py.name.lower() == "python.exe" and (py.parent / "pythonw.exe").is_file():
            py = py.parent / "pythonw.exe"
        cmd = (f'timeout /t 4 /nobreak >nul & schtasks /Run /TN "EVA Satellite" >nul 2>&1 || '
               f'(cd /d "{ici}" & start "" /min "{py}" {subprocess.list2cmdline(sys.argv)})')
        drapeaux = 0x00000200 | 0x08000000                       # nouveau groupe, sans fenêtre
        for extra in (0x01000000, 0):                             # sortir du « job » de la tâche planifiée si possible
            try:
                subprocess.Popen(f'cmd /c "{cmd}"', creationflags=drapeaux | extra, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            except OSError:
                continue
        log("Relance programmée dans 4 secondes.")
        os._exit(0)

    @staticmethod
    def gardien(dossier: Path) -> None:
        """Windows, installation administrateur : ajoute à la tâche « EVA Satellite » un déclencheur toutes les 5 minutes
        (sans effet s'il tourne déjà) : un satellite arrêté par erreur repart tout seul. Fait une seule fois."""
        if SYSTEME != "Windows" or (dossier / "gardien.ok").exists():
            return
        raccourcis_windows(dossier)
        import subprocess
        ps = ("$t=Get-ScheduledTask -TaskName 'EVA Satellite' -ErrorAction Stop; "
              "if(-not ($t.Triggers | Where-Object { $_.Repetition.Interval })){ "
              "$r=New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5); "
              "Set-ScheduledTask -TaskName 'EVA Satellite' -Trigger (@($t.Triggers)+$r) -ErrorAction Stop | Out-Null }; 'ok'")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60,
                               creationflags=0x08000000)
            if "ok" in (r.stdout or ""):
                (dossier / "gardien.ok").write_text("ok")
                log("Relance automatique activée (la tâche vérifie toutes les 5 minutes que le satellite tourne).")
            else:
                log("Relance automatique non activée (installation sans droits administrateur ?) :", (r.stderr or "").strip()[:200])
        except Exception as exc:  # noqa: BLE001
            log("Relance automatique non activée :", exc)

    def surveiller(self, toutes_les_s: int = 6 * 3600) -> None:
        def boucle():
            while True:
                time.sleep(toutes_les_s)
                if self.verifier():
                    self.dependances()
                    self.relancer()
        threading.Thread(target=boucle, daemon=True).start()


def arret_volontaire(dossier: Path) -> None:
    """Windows : note l'arrêt volontaire, pour que le gardien (tâche toutes les 5 min) ne le relance pas."""
    try:
        (dossier / "arrete").touch()
    except OSError:
        pass


def arrete_cette_session(dossier: Path) -> bool:
    """Vrai si le satellite a été arrêté volontairement depuis le dernier démarrage du PC."""
    f = dossier / "arrete"
    if not f.exists():
        return False
    try:
        import ctypes
        demarrage = time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000
    except Exception:  # noqa: BLE001
        demarrage = 0
    if f.stat().st_mtime > demarrage:
        return True
    f.unlink(missing_ok=True)                                     # PC redémarré depuis : on repart
    return False


def raccourcis_windows(dossier: Path) -> None:
    """Met à jour les raccourcis « EVA démarrer / arrêter » du bureau (installations d'avant la 1.7)."""
    bureaux = [Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop",
               *[Path(os.environ[v]) / "Desktop" for v in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial") if os.environ.get(v)]]
    py = dossier / "venv" / "Scripts" / "pythonw.exe"
    tue = ("powershell -NoProfile -Command \"Get-CimInstance Win32_Process -Filter 'Name like ''python%%'' ' | "
           "Where-Object { $_.CommandLine -like '*eva-satellite*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
           "-ErrorAction SilentlyContinue }\"")
    demarrer = (f'@echo off\r\ndel "{dossier}\\arrete" 2>nul\r\nschtasks /Run /TN "EVA Satellite" >nul 2>&1 || '
                f'(cd /d "{dossier}" & start "" /min "{py}" satellite.py)\r\necho Satellite EVA demarre.\r\ntimeout /t 2 >nul\r\n')
    arreter = (f'@echo off\r\ntype nul > "{dossier}\\arrete"\r\nschtasks /End /TN "EVA Satellite" >nul 2>&1\r\n{tue}\r\n'
               'echo Satellite EVA arrete (raccourci EVA demarrer pour le relancer).\r\ntimeout /t 3 >nul\r\n')
    for b in bureaux:
        for nom, contenu in (("EVA démarrer.cmd", demarrer), ("EVA arrêter.cmd", arreter)):
            f = b / nom
            if f.is_file():
                try:
                    f.write_bytes(contenu.encode("ascii", "replace"))
                except OSError:
                    pass


def main():
    ici = Path(__file__).resolve().parent
    conf = {}
    if (ici / "satellite.json").is_file():
        conf = json.loads((ici / "satellite.json").read_text(encoding="utf-8-sig"))   # Windows PowerShell 5 ajoute une marque BOM
    if SYSTEME == "Windows" and arrete_cette_session(ici):
        log("Satellite arrêté volontairement : il attend le raccourci « EVA démarrer » ou le prochain démarrage du PC.")
        return
    if conf.get("retire"):
        log("Ce satellite a été retiré d'EVA : il ne fait plus rien. Pour l'effacer : bash desinstaller.sh (dans ce dossier).")
        while True:
            time.sleep(3600)
    p = argparse.ArgumentParser(description="Satellite vocal d'EVA")
    p.add_argument("--eva", default=conf.get("eva"), help="Adresse d'EVA, ex. https://192.168.1.10:8443")
    p.add_argument("--jeton", default=conf.get("jeton"), help="Jeton du satellite (Maison › Satellites)")
    p.add_argument("--certificat", default=conf.get("certificat"), help="Certificat d'EVA (eva-certificat.crt)")
    p.add_argument("--micro", default=conf.get("micro"), help="Numéro ou nom du micro (voir --liste-audio)")
    p.add_argument("--haut-parleur", default=conf.get("haut_parleur"), help="Numéro ou nom du haut-parleur")
    p.add_argument("--seuil", type=float, default=conf.get("seuil"), help="Seuil de parole (automatique par défaut)")
    p.add_argument("--eveil", choices=["whisper", "local"], default=conf.get("eveil", "whisper"),
                   help="whisper : chaque phrase est transcrite puis on cherche « EVA » ; local : détecteur sur le satellite (modele-eveil/)")
    p.add_argument("--sensibilite", type=float, default=conf.get("sensibilite_eveil", 0.5), help="Éveil local : 0 (strict) à 1 (sensible)")
    p.add_argument("--liste-audio", action="store_true", help="Affiche les micros et haut-parleurs")
    p.add_argument("--fenetre", action="store_true", default=bool(conf.get("fenetre")), help="Fenêtre flottante avec les réponses (PC)")
    p.add_argument("--silencieux", action="store_true", default=bool(conf.get("silencieux")), help="Avec la fenêtre : afficher sans parler")
    p.add_argument("--sans-pc", action="store_true", default=not conf.get("pc", True), help="Ne pas laisser EVA piloter cet ordinateur")
    p.add_argument("--ecran", action="store_true", default=bool(conf.get("ecran")), help="EVA peut regarder l'écran et y cliquer (avec ton accord)")
    p.add_argument("--gestes", action="store_true", default=bool(conf.get("gestes")), help="Gestes de la main devant la webcam")
    p.add_argument("--camera", type=int, default=conf.get("camera", 0), help="Numéro de la webcam pour les gestes")
    p.add_argument("--sans-icone", action="store_true", default=conf.get("icone") is False, help="Pas d'icône à côté de l'horloge")
    p.add_argument("--sans-maj", action="store_true", default=conf.get("mise_a_jour_auto") is False,
                   help="Ne pas se mettre à jour tout seul depuis EVA")
    p.add_argument("--tableau", action="store_true", default=bool(conf.get("tableau")), help="Avec la fenêtre : tableau de bord au repos")
    a = p.parse_args()
    if a.liste_audio:
        print(sd.query_devices())
        return
    if not a.eva or not a.jeton:
        p.error("il faut --eva et --jeton (ou un fichier satellite.json).")
    cert = a.certificat
    if cert and not Path(cert).is_absolute():
        cert = str(ici / cert)
    verif = cert if cert and Path(cert).is_file() else True
    num = lambda v: int(v) if isinstance(v, str) and v.isdigit() else v  # noqa: E731
    log(f"Satellite EVA {VERSION} → {a.eva}")
    if SYSTEME == "Windows":                                    # vrais pixels (écran, souris) sur les écrans à 125-150 %
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001
                pass
    try:
        eveil = None
        if a.eveil == "local":
            dossier = ici / KWS_DOSSIER
            if not any(dossier.glob("tokens.txt")):
                sys.exit("Éveil local : modèle absent (dossier modele-eveil). Relance l'installateur avec l'option « local ».")
            eveil = EveilLocal(dossier, a.sensibilite)
            log("Mot d'éveil détecté sur le satellite (rien n'est envoyé avant « EVA »).")
        eva = Eva(a.eva, a.jeton, verif)
        maj = MiseAJour(eva, ici, {"ecran": a.ecran, "gestes": a.gestes, "fenetre": a.fenetre})
        if not a.sans_maj:
            if maj.verifier():
                maj.dependances()
                maj.relancer()
            maj.surveiller()
        threading.Thread(target=MiseAJour.gardien, args=(ici,), daemon=True).start()
        maj.dependances()                                        # option ajoutée dans satellite.json : modules installés tout seuls
        pc = None if a.sans_pc else Ordinateur(conf.get("applis"), conf.get("source_musique"), eva)
        fenetre = None
        if a.fenetre:
            try:
                fenetre = Fenetre(conf.get("fenetre_position", "bas-droite"), conf.get("fenetre_duree", 15))
            except Exception as exc:  # noqa: BLE001 — pas d'écran, ou tkinter absent (Linux : sudo apt install python3-tk)
                log("Fenêtre flottante indisponible :", exc)
        if fenetre and a.tableau:
            fenetre.tableau = {}                                 # tableau au repos activé (rempli par EVA toutes les 5 minutes)
        ecran = None
        if a.ecran and not a.sans_pc:
            try:
                ecran = Ecran()
                log("Écran : EVA peut regarder l'écran et y cliquer (toujours avec ton accord).")
            except ImportError as exc:
                log("Écran indisponible (pip install mss pillow rapidocr_onnxruntime) :", exc)
        sat = Satellite(eva, Micro(num(a.micro), a.seuil, eveil), num(a.haut_parleur), pc, fenetre, a.silencieux, ecran)
        if a.gestes:
            try:
                import gestes as gestes_mod
                modele = gestes_mod.modele_par_defaut(ici)
                if not Path(modele).is_file():
                    raise FileNotFoundError("hand_landmarker.task absent : relance l'installateur avec l'option gestes")
                import cv2  # noqa: F401
                import mediapipe  # noqa: F401
                gestes_mod.Gestes(modele, sat.geste, a.camera, bool(conf.get("gestes_clic"))).start()
                sat.gestes = True
                log("Gestes : main ouverte = pause, 2 doigts = onglets, 3 doigts = audio, index = souris, poing = EVA se tait.")
            except Exception as exc:  # noqa: BLE001
                log("Gestes indisponibles (pip install mediapipe opencv-python) :", exc)
        if SYSTEME in ("Windows", "Linux") and not a.sans_icone and (a.fenetre or a.ecran or conf.get("icone")):
            try:
                Icone(sat, a.eva).demarrer()
                log("Icône EVA à côté de l'horloge : Parler, Pause, Redémarrer, Arrêter.")
            except Exception as exc:  # noqa: BLE001 — pas de zone de notification (Raspberry Pi sans écran…)
                log("Icône indisponible (pip install pystray) :", exc)
        if fenetre:
            threading.Thread(target=sat.boucle, daemon=True).start()
            fenetre.boucle()                                     # tkinter doit tourner dans le fil principal
        else:
            sat.boucle()
    except KeyboardInterrupt:
        log("Arrêt.")
    except requests.exceptions.SSLError:
        sys.exit("Certificat refusé : relance l'installateur (il récupère le certificat d'EVA) ou passe --certificat.")


if __name__ == "__main__":
    main()
