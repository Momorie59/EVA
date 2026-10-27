"""Gestes de la main devant la webcam du PC, pour piloter l'ordinateur sans le toucher (comme les gestes de Jarvis).

Tout reste sur l'ordinateur : l'image de la caméra n'est jamais envoyée ni enregistrée, seuls des gestes reconnus
(« main ouverte », « deux doigts »…) en sortent. Les gestes n'ont que des effets sans risque : lecture, volume, onglets,
défilement, zoom, souris. Jamais d'extinction, d'achat ni d'envoi par un geste ; le pouce levé / baissé répond seulement
« oui » / « non » quand EVA vient de poser une question à voix haute.

Vocabulaire (gestes TENUS environ une seconde, pour éviter les faux départs) :
  main ouverte immobile → lecture / pause          poing → EVA se tait (et, dans un mode, recentre la main)
  deux doigts → mode Onglets : main à gauche/droite = onglet précédent/suivant, en haut/en bas = page haut/bas
  trois doigts → mode Audio : en haut/en bas = volume, à gauche/droite = piste précédente/suivante
  index seul → mode Souris : l'index guide le pointeur (clic par pincement pouce-index, s'il est activé)
  deux mains ouvertes : écarter = zoom avant, rapprocher = zoom arrière
  pouce levé / baissé → « oui » / « non » à la question d'EVA
Un mode s'arrête si la main sort du cadre plus de 2 secondes, ou après 15 secondes sans mouvement.

Dépendances (installées avec l'option « gestes ») : pip install mediapipe opencv-python ; modèle hand_landmarker.task."""
import math
import os
import platform
import shutil
import subprocess
import threading
import time

SYSTEME = platform.system()


# ---------------------------------------------------------------- reconnaissance (fonctions pures, testables sans caméra)

def _pt(p):
    return (p.x, p.y) if hasattr(p, "x") else (p[0], p[1])


def _d(a, b) -> float:
    (ax, ay), (bx, by) = _pt(a), _pt(b)
    return math.hypot(ax - bx, ay - by)


def doigts(lm) -> dict:
    """Doigts tendus (21 points MediaPipe : 0 poignet, pouce 1-4, index 5-8, majeur 9-12, annulaire 13-16, auriculaire 17-20)."""
    w = lm[0]
    f = lambda bout, art: _d(lm[bout], w) > _d(lm[art], w) * 1.15  # noqa: E731
    pouce = _d(lm[4], lm[17]) > _d(lm[3], lm[17]) * 1.05 and _d(lm[4], lm[5]) > _d(lm[2], lm[5]) * 0.9
    return {"pouce": pouce, "index": f(8, 6), "majeur": f(12, 10), "annulaire": f(16, 14), "auriculaire": f(20, 18)}


def pose(lm) -> str | None:
    """« ouverte », « deux », « trois », « index », « poing », « pouce_haut », « pouce_bas » ou None."""
    if not lm or len(lm) < 21:
        return None
    e = doigts(lm)
    n4 = sum(e[k] for k in ("index", "majeur", "annulaire", "auriculaire"))
    if n4 == 4:
        return "ouverte"
    if e["index"] and e["majeur"] and e["annulaire"] and not e["auriculaire"]:
        return "trois"
    if e["index"] and e["majeur"] and not e["annulaire"] and not e["auriculaire"]:
        return "deux"
    if e["index"] and not e["majeur"] and not e["annulaire"] and not e["auriculaire"]:
        return "index"
    if n4 == 0 and e["pouce"]:
        (x4, y4), (x2, y2) = _pt(lm[4]), _pt(lm[2])
        dy, dx, taille = y4 - y2, abs(x4 - x2), _d(lm[0], lm[9])
        if dy < -0.45 * taille and abs(dy) > dx * 1.3 and y4 < min(_pt(lm[6])[1], _pt(lm[10])[1]):
            return "pouce_haut"
        if dy > 0.45 * taille and abs(dy) > dx * 1.3 and y4 > max(_pt(lm[6])[1], _pt(lm[10])[1]):
            return "pouce_bas"
    if n4 == 0:
        return "poing"
    return None


def centre(lm) -> tuple[float, float]:
    """Centre de la paume, en image MIROIR (ta main droite va à droite), coordonnées 0..1."""
    (x0, y0), (x9, y9) = _pt(lm[0]), _pt(lm[9])
    return 1 - (x0 + x9) / 2, (y0 + y9) / 2


class Detecteur:
    """Machine à états : step(t en secondes, mains) → liste d'actions. mains = liste de 0 à 2 mains (21 points chacune)."""

    TENUE = {"ouverte": 1.0, "deux": 0.9, "trois": 0.9, "index": 0.9, "poing": 0.8, "pouce_haut": 0.7, "pouce_bas": 0.7}
    PAS_H, PAS_V = 0.11, 0.08            # déplacement de la main (fraction de l'image) pour une action dans un mode
    IMMOBILE = 0.035
    REPOS = 1.2                          # entre deux gestes tenus
    PERTE = 2.0                          # main absente : le mode s'arrête
    INACTIF = 15.0

    def __init__(self, clic_souris: bool = False):
        self.mode = None                 # None | "onglets" | "audio" | "souris"
        self.clic_souris = clic_souris
        self.tenue = (None, 0.0, 0.0, 0.0)   # pose, depuis, x, y
        self.dernier_geste = -1e9
        self.ancre = None                # point de départ des déplacements dans un mode
        self.vu = self.actif = 0.0
        self.pince = False
        self.ecart = None                # zoom à deux mains

    def _sortir(self, raison: str) -> list:
        if self.mode is None:
            return []
        self.mode, self.ancre = None, None
        return [("mode", None, raison)]

    def step(self, t: float, mains: list) -> list:
        out: list = []
        if not mains:
            self.tenue, self.ecart = (None, 0.0, 0.0, 0.0), None
            if self.mode and t - self.vu > self.PERTE:
                out += self._sortir("main sortie du cadre")
            return out
        self.vu = t
        if self.mode and t - self.actif > self.INACTIF:
            out += self._sortir("inactif")
        if len(mains) >= 2:                                   # deux mains : zoom seulement
            a, b = mains[0], mains[1]
            if pose(a) == "ouverte" and pose(b) == "ouverte":
                (ax, ay), (bx, by) = centre(a), centre(b)
                e = math.hypot(ax - bx, ay - by)
                if self.ecart is None:
                    self.ecart = e
                elif abs(e - self.ecart) > 0.07:
                    out.append(("zoom", 1 if e > self.ecart else -1))
                    self.ecart, self.actif = e, t
            else:
                self.ecart = None
            return out
        self.ecart = None
        lm = mains[0]
        p, (x, y) = pose(lm), centre(lm)
        if self.mode == "souris":
            if p == "poing":
                return out + self._tenir(t, p, x, y, lambda: self._sortir("poing"))
            ix, iy = 1 - _pt(lm[8])[0], _pt(lm[8])[1]
            out.append(("souris", min(1.0, max(0.0, (ix - 0.2) / 0.6)), min(1.0, max(0.0, (iy - 0.15) / 0.6))))
            if self.clic_souris:
                r = _d(lm[4], lm[8]) / (_d(lm[0], lm[9]) or 1e-6)
                if not self.pince and r < 0.3:
                    self.pince = True
                    out.append(("clic",))
                elif self.pince and r > 0.5:
                    self.pince = False
            self.actif = t
            return out
        if self.mode in ("onglets", "audio"):
            if p == "poing":                                  # recentrer : on lâche l'ancre, sans action
                self.ancre = None
                return out
            if p == "ouverte":
                if self.ancre is None:
                    self.ancre = (x, y)
                dx, dy = x - self.ancre[0], y - self.ancre[1]
                if abs(dx) >= self.PAS_H and abs(dx) > abs(dy):
                    droite = dx > 0
                    out.append(("touche", ("onglet_suivant" if droite else "onglet_precedent") if self.mode == "onglets"
                                else ("suivant" if droite else "precedent")))
                    self.ancre, self.actif = (x, y), t
                elif abs(dy) >= self.PAS_V:
                    bas = dy > 0
                    out.append(("touche", ("page_bas" if bas else "page_haut") if self.mode == "onglets"
                                else ("volume_moins" if bas else "volume_plus")))
                    self.ancre, self.actif = (x, y), t
                return out
            # autre geste tenu : changer de mode reste possible
        modes = {"deux": "onglets", "trois": "audio", "index": "souris"}
        if p in modes and self.mode != modes[p]:
            return out + self._tenir(t, p, x, y, lambda: self._entrer(modes[p], t))
        if self.mode is None:
            if p == "ouverte":
                return out + self._tenir(t, p, x, y, lambda: [("touche", "lecture_pause")])
            if p == "poing":
                return out + self._tenir(t, p, x, y, lambda: [("stop",)])
            if p == "pouce_haut":
                return out + self._tenir(t, p, x, y, lambda: [("reponse", "oui")])
            if p == "pouce_bas":
                return out + self._tenir(t, p, x, y, lambda: [("reponse", "non")])
        if p is None or p not in self.TENUE:
            self.tenue = (None, 0.0, 0.0, 0.0)
        return out

    def _entrer(self, mode: str, t: float) -> list:
        self.mode, self.ancre, self.actif, self.pince = mode, None, t, False
        return [("mode", mode, "")]

    def _tenir(self, t: float, p: str, x: float, y: float, agir) -> list:
        if t - self.dernier_geste < self.REPOS:
            return []
        q, depuis, x0, y0 = self.tenue
        if q != p or math.hypot(x - x0, y - y0) > self.IMMOBILE * (3 if p in ("deux", "trois", "index") else 1):
            self.tenue = (p, t, x, y)
            return []
        if t - depuis >= self.TENUE[p]:
            self.tenue, self.dernier_geste = (None, 0.0, 0.0, 0.0), t
            return agir()
        return []


# ---------------------------------------------------------------- effets sur l'ordinateur

VK = {"ctrl": 0x11, "shift": 0x10, "tab": 0x09, "pageup": 0x21, "pagedown": 0x22, "plus": 0xBB, "minus": 0xBD,
      "lecture_pause": 0xB3, "suivant": 0xB0, "precedent": 0xB1, "volume_plus": 0xAF, "volume_moins": 0xAE}
XDO = {"onglet_suivant": "ctrl+Tab", "onglet_precedent": "ctrl+shift+Tab", "page_bas": "Next", "page_haut": "Prior",
       "lecture_pause": "XF86AudioPlay", "suivant": "XF86AudioNext", "precedent": "XF86AudioPrev",
       "volume_plus": "XF86AudioRaiseVolume", "volume_moins": "XF86AudioLowerVolume", "zoom+": "ctrl+plus", "zoom-": "ctrl+minus"}
WIN = {"onglet_suivant": ("ctrl", "tab"), "onglet_precedent": ("ctrl", "shift", "tab"), "page_bas": ("pagedown",), "page_haut": ("pageup",),
       "lecture_pause": ("lecture_pause",), "suivant": ("suivant",), "precedent": ("precedent",),
       "volume_plus": ("volume_plus",), "volume_moins": ("volume_moins",), "zoom+": ("ctrl", "plus"), "zoom-": ("ctrl", "minus")}


def touche(nom: str) -> None:
    if SYSTEME == "Windows":
        import ctypes
        u = ctypes.windll.user32
        codes = [VK[k] for k in WIN[nom]]
        for c in codes:
            u.keybd_event(c, 0, 0, 0)
        for c in reversed(codes):
            u.keybd_event(c, 0, 2, 0)
        if nom.startswith("volume"):                          # 2 % par appui : trois appuis pour que ça s'entende
            for _ in range(2):
                u.keybd_event(codes[0], 0, 0, 0)
                u.keybd_event(codes[0], 0, 2, 0)
    elif shutil.which("xdotool"):
        subprocess.run(["xdotool", "key", XDO[nom]], timeout=5, check=False)


def taille_ecran() -> tuple[int, int]:
    if SYSTEME == "Windows":
        import ctypes
        return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    try:
        out = subprocess.run(["xdotool", "getdisplaygeometry"], capture_output=True, text=True, timeout=5).stdout.split()
        return int(out[0]), int(out[1])
    except Exception:  # noqa: BLE001
        return 1920, 1080


def pointeur(x: int, y: int, clic: bool = False) -> None:
    if SYSTEME == "Windows":
        import ctypes
        u = ctypes.windll.user32
        u.SetCursorPos(int(x), int(y))
        if clic:
            u.mouse_event(2, 0, 0, 0, 0)
            u.mouse_event(4, 0, 0, 0, 0)
    elif shutil.which("xdotool"):
        subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))] + (["click", "1"] if clic else []), timeout=5, check=False)


# ---------------------------------------------------------------- caméra

class Gestes(threading.Thread):
    """Lit la webcam (10 images/s), reconnaît les gestes et appelle `quand(action)` pour ceux qui concernent le satellite
    (stop, oui/non, changement de mode) ; les touches, le zoom et la souris sont faits ici directement."""

    def __init__(self, modele: str, quand, camera: int = 0, clic_souris: bool = False):
        super().__init__(daemon=True)
        self.modele, self.quand, self.camera = modele, quand, camera
        self.det = Detecteur(clic_souris)
        self.lisse = None
        self.arret = threading.Event()

    def _agir(self, a: tuple) -> None:
        if a[0] == "touche":
            touche(a[1])
        elif a[0] == "zoom":
            touche("zoom+" if a[1] > 0 else "zoom-")
        elif a[0] in ("souris", "clic"):
            w, h = taille_ecran()
            if a[0] == "souris":
                x, y = a[1] * w, a[2] * h
                self.lisse = (x, y) if self.lisse is None else (self.lisse[0] * 0.6 + x * 0.4, self.lisse[1] * 0.6 + y * 0.4)
                pointeur(*self.lisse)
            elif self.lisse:
                pointeur(*self.lisse, clic=True)
        if a[0] not in ("souris",):
            self.quand(a)

    def run(self) -> None:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=self.modele),
                                            running_mode=vision.RunningMode.VIDEO, num_hands=2)
        detecteur = vision.HandLandmarker.create_from_options(opts)
        cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW if SYSTEME == "Windows" else 0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            self.quand(("erreur", f"webcam {self.camera} introuvable"))
            return
        debut = time.monotonic()
        try:
            while not self.arret.is_set():
                ok, image = cap.read()
                if not ok:
                    time.sleep(0.2)
                    continue
                t = time.monotonic() - debut
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                res = detecteur.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(t * 1000))
                for a in self.det.step(t, list(res.hand_landmarks or [])):
                    try:
                        self._agir(a)
                    except Exception:  # noqa: BLE001 — un geste raté ne coupe pas la caméra
                        pass
                time.sleep(0.06)
        finally:
            cap.release()


def modele_par_defaut(dossier) -> str:
    return os.path.join(str(dossier), "hand_landmarker.task")
