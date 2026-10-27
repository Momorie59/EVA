"""Reconnaissance des utilisateurs : voix (comme une enceinte connectée) et visage (caméra).

100 % local : les modèles ONNX sont téléchargés une fois dans le workspace, les empreintes
(vecteurs de nombres, pas d'enregistrement ni de photo) sont stockées dans la base d'EVA.
Ce n'est PAS une authentification forte : une voix peut être imitée ou enregistrée, une photo
peut tromper une caméra. L'identification sert à personnaliser et à limiter les outils sensibles
pour les voix inconnues, jamais à autoriser seule une action dangereuse (les confirmations restent)."""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import zlib
import os
import random
import secrets
import time
import wave
from pathlib import Path

import httpx

from .config import settings
from .db import get_pool

log = logging.getLogger("eva-core.identity")

MODELS = {
    "speaker": {
        "file": "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        "urls": ["https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"],
        "min": 10_000_000,
    },
    "face_detect": {
        "file": "face_detection_yunet_2023mar.onnx",
        "urls": ["https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                 "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"],
        "min": 100_000,
    },
    "face_recog": {
        "file": "face_recognition_sface_2021dec.onnx",
        "urls": ["https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                 "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"],
        "min": 10_000_000,
    },
}
MAX_SAMPLES = 12
MIN_VOICE_SECONDS = 0.8
GUEST_TOOLS = {"weather_get", "web_search", "web_fetch", "system_stats", "present"}  # seuls outils offerts à une voix inconnue
DEFAULT_SETTINGS = {
    "voice_id": True, "face_id": False, "voice_threshold": 0.65, "face_threshold": 0.363,
    "restrict_unknown": False, "fresh_seconds": 60, "face_liveness": True, "style_id": False,
}
KV_KEY = "identity"
TOKEN_TTL = 90
_SECRET = os.urandom(32)  # change à chaque démarrage : les jetons ne survivent pas à un redémarrage
_download = {"running": False, "error": "", "done": []}
_engines: dict = {}
_lock = asyncio.Lock()


class IdentityError(Exception):
    pass


def models_dir() -> Path:
    d = Path(os.getenv("EVA_WORKSPACE", "/workspace")) / ".models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path(key: str) -> Path:
    return models_dir() / MODELS[key]["file"]


def models_status() -> dict:
    out = {}
    for k, m in MODELS.items():
        p = model_path(k)
        out[k] = p.exists() and p.stat().st_size >= m["min"]
    return out


def libs_status() -> dict:
    res = {}
    for name in ("numpy", "cv2", "sherpa_onnx"):
        try:
            __import__(name)
            res[name] = True
        except Exception:
            res[name] = False
    return res


# ---------- stockage ----------

async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV_KEY)
    data = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    data.setdefault("profiles", {})
    data["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
    return data


async def _save(data: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
            KV_KEY, json.dumps(data))


async def status() -> dict:
    data = await _load()
    return {
        "libs": libs_status(),
        "models": models_status(),
        "download": dict(_download),
        "settings": data["settings"],
        "profiles": [{"name": n, "voice": len(p.get("voice", [])), "face": len(p.get("face", [])), "style": (p.get("style") or {}).get("n", 0)}
                     for n, p in sorted(data["profiles"].items())],
    }


async def create_profile(name: str) -> None:
    name = name.strip()[:40]
    if not name:
        raise IdentityError("Donne un prénom.")
    data = await _load()
    data["profiles"].setdefault(name, {"voice": [], "face": []})
    await _save(data)


async def delete_profile(name: str, kind: str | None = None) -> None:
    data = await _load()
    if name not in data["profiles"]:
        raise IdentityError("Profil inconnu.")
    if kind == "style":
        data["profiles"][name].pop("style", None)
    elif kind in ("voice", "face"):
        data["profiles"][name][kind] = []
    else:
        del data["profiles"][name]
    await _save(data)


async def update_settings(patch: dict) -> dict:
    data = await _load()
    s = data["settings"]
    for k, v in patch.items():
        if k not in DEFAULT_SETTINGS or v is None:
            continue
        if isinstance(DEFAULT_SETTINGS[k], bool):
            s[k] = bool(v)
        else:
            s[k] = float(v) if isinstance(DEFAULT_SETTINGS[k], float) else int(v)
    s["voice_threshold"] = min(0.9, max(0.2, s["voice_threshold"]))
    s["face_threshold"] = min(0.8, max(0.2, s["face_threshold"]))
    await _save(data)
    return s


# ---------- modèles ----------

async def download_models() -> None:
    if _download["running"]:
        return
    _download.update(running=True, error="", done=[])
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            for key, m in MODELS.items():
                dest = model_path(key)
                if dest.exists() and dest.stat().st_size >= m["min"]:
                    _download["done"].append(key)
                    continue
                last = ""
                for url in m["urls"]:
                    try:
                        tmp = dest.with_suffix(".part")
                        async with client.stream("GET", url) as r:
                            r.raise_for_status()
                            with open(tmp, "wb") as f:
                                async for chunk in r.aiter_bytes(1 << 16):
                                    f.write(chunk)
                        if tmp.stat().st_size < m["min"]:
                            raise IdentityError("fichier incomplet")
                        tmp.rename(dest)
                        _download["done"].append(key)
                        break
                    except Exception as exc:  # essaie l'URL suivante
                        last = f"{type(exc).__name__}: {exc}"
                else:
                    raise IdentityError(f"Téléchargement impossible ({key}) : {last}")
    except Exception as exc:
        _download["error"] = str(exc)
    finally:
        _download["running"] = False
        _engines.clear()


# ---------- calcul des empreintes ----------

def _need(*keys: str) -> None:
    libs = libs_status()
    missing = [n for n, ok in libs.items() if not ok]
    if missing:
        raise IdentityError("Bibliothèques manquantes dans EVA CORE : " + ", ".join(missing) + " — reconstruis l'image (docker compose build eva-core).")
    st = models_status()
    if not all(st[k] for k in keys):
        raise IdentityError("Modèles d'identification non téléchargés : utilise le bouton « Télécharger les modèles ».")


def _wav_to_float(wav_bytes: bytes):
    import numpy as np
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except Exception as exc:
        raise IdentityError(f"Audio illisible (WAV attendu) : {exc}") from exc
    if sw != 2:
        raise IdentityError("WAV 16 bits attendu.")
    a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def _speaker_extractor():
    if "spk" not in _engines:
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model_path("speaker")), num_threads=2, provider="cpu")
        _engines["spk"] = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
    return _engines["spk"]


def voice_embedding(wav_bytes: bytes):
    _need("speaker")
    import numpy as np
    a, sr = _wav_to_float(wav_bytes)
    if len(a) / sr < MIN_VOICE_SECONDS:
        raise IdentityError("Enregistrement trop court (au moins une seconde de parole).")
    if float(np.sqrt(np.mean(a ** 2))) < 0.003:
        raise IdentityError("Enregistrement quasi silencieux.")
    ext = _speaker_extractor()
    st = ext.create_stream()
    st.accept_waveform(sample_rate=sr, waveform=a)
    st.input_finished()
    if not ext.is_ready(st):
        raise IdentityError("Pas assez de parole exploitable.")
    return np.array(ext.compute(st), dtype="float32")


def _face_engines(w: int, h: int):
    import cv2
    if "det" not in _engines:
        _engines["det"] = cv2.FaceDetectorYN.create(str(model_path("face_detect")), "", (320, 320), 0.8, 0.3, 5000)
        _engines["rec"] = cv2.FaceRecognizerSF.create(str(model_path("face_recog")), "")
    _engines["det"].setInputSize((w, h))
    return _engines["det"], _engines["rec"]


def face_analyze(image_bytes: bytes) -> list:
    """Pour chaque visage détecté (du plus grand au plus petit) : (empreinte, taille, lacet).
    `lacet` : décalage du nez par rapport au milieu des yeux, divisé par l'écart des yeux. ≈ 0 de face ;
    positif = la personne tourne la tête vers SA gauche, négatif = vers SA droite (caméra non inversée)."""
    _need("face_detect", "face_recog")
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise IdentityError("Image illisible.")
    h, w = img.shape[:2]
    if max(h, w) > 1280:
        s = 1280 / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)))
        h, w = img.shape[:2]
    det, rec = _face_engines(w, h)
    _, faces = det.detect(img)
    out = []
    if faces is not None:
        for f in sorted(faces, key=lambda r: -float(r[2] * r[3])):
            feat = rec.feature(rec.alignCrop(img, f)).flatten().astype("float32")
            out.append((feat, float(f[2] * f[3]), yaw_from_landmarks(f[4], f[6], f[8])))
    return out


def yaw_from_landmarks(right_eye_x: float, left_eye_x: float, nose_x: float) -> float:
    eye_dist = abs(float(left_eye_x) - float(right_eye_x))
    if eye_dist < 1:
        return 0.0
    return (float(nose_x) - (float(right_eye_x) + float(left_eye_x)) / 2) / eye_dist


def face_embeddings(image_bytes: bytes) -> list:
    """Liste [(empreinte, taille_du_visage)] pour chaque visage détecté."""
    return [(e, sz) for e, sz, _ in face_analyze(image_bytes)]


def _cos(a, b) -> float:
    import numpy as np
    a, b = np.asarray(a, dtype="float32"), np.asarray(b, dtype="float32")
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / d) if d else 0.0


def _best(emb, profiles: dict, kind: str):
    """Meilleur profil + score ; si deux personnes se ressemblent trop (écart < 0.05), on ne tranche pas."""
    per = {}
    for name, p in profiles.items():
        sc = [_cos(emb, ref) for ref in p.get(kind, [])]
        if sc:
            per[name] = max(sc)
    if not per:
        return None, -1.0
    ranked = sorted(per.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.05:
        return None, ranked[0][1]
    return ranked[0]


# ---------- enrôlement / identification ----------

async def enroll(name: str, kind: str, payload: bytes) -> dict:
    data = await _load()
    if name not in data["profiles"]:
        raise IdentityError("Crée d'abord le profil.")
    if kind == "voice":
        emb = await asyncio.to_thread(voice_embedding, payload)
    else:
        faces = await asyncio.to_thread(face_embeddings, payload)
        if not faces:
            raise IdentityError("Aucun visage détecté : place-toi de face, bien éclairé.")
        if len(faces) > 1:
            raise IdentityError("Plusieurs visages détectés : une seule personne devant la caméra pour l'enregistrement.")
        emb = faces[0][0]
    samples = data["profiles"][name].setdefault(kind, [])
    samples.append([round(float(x), 5) for x in emb])
    del samples[:-MAX_SAMPLES]
    await _save(data)
    return {"samples": len(samples)}


def make_token(name: str, source: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"n": name, "s": source, "e": int(time.time()) + TOKEN_TTL}).encode()).decode()
    sig = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def check_token(token: str | None) -> dict | None:
    """Renvoie {name, source} si le jeton est authentique et récent, sinon None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    good = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, good):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(body.encode()))
    except Exception:
        return None
    if d.get("e", 0) < time.time():
        return None
    return {"name": d["n"], "source": d["s"]}


async def identify_voice(wav_bytes: bytes) -> dict:
    data = await _load()
    if not any(p.get("voice") for p in data["profiles"].values()):
        return {"name": None, "score": 0.0, "enrolled": False}
    emb = await asyncio.to_thread(voice_embedding, wav_bytes)
    name, score = _best(emb, data["profiles"], "voice")
    ok = name is not None and score >= data["settings"]["voice_threshold"]
    res = {"name": name if ok else None, "score": round(score, 3), "enrolled": True}
    if ok:
        res["token"] = make_token(name, "voice")
    return res


async def identify_face(image_bytes: bytes) -> dict:
    data = await _load()
    if not any(p.get("face") for p in data["profiles"].values()):
        return {"name": None, "score": 0.0, "faces": 0, "enrolled": False}
    faces = await asyncio.to_thread(face_embeddings, image_bytes)
    if not faces:
        return {"name": None, "score": 0.0, "faces": 0, "enrolled": True}
    name, score = _best(faces[0][0], data["profiles"], "face")  # le visage le plus grand = la personne devant l'écran
    ok = name is not None and score >= data["settings"]["face_threshold"]
    res = {"name": name if ok else None, "score": round(score, 3), "faces": len(faces), "enrolled": True}
    if ok:
        res["token"] = make_token(name, "face")
    return res


async def turn_context(token: str | None, voice_turn: bool, text: str = "") -> dict:
    """Ce que le serveur sait de la personne qui parle pour ce tour : {name, source, trusted, guest}.
    Une identité « de confiance » = voix reconnue ou visage vérifié en direct. Un visage seulement aperçu par la
    caméra permet de saluer par le prénom mais ne lève pas les restrictions si la vérification en direct est exigée."""
    who = check_token(token)
    data = await _load()
    s = data["settings"]
    trusted = bool(who and (who["source"] in ("voice", "face-live") or not s["face_liveness"]))
    have_ids = any(p.get("voice") or p.get("face") for p in data["profiles"].values())
    guest = bool(voice_turn and s["restrict_unknown"] and have_ids and not trusted)
    ctx = {"name": who["name"] if who else None, "source": who["source"] if who else None, "trusted": trusted, "guest": guest}
    if not who and not voice_turn and s["style_id"]:
        guess = await identify_style(text)
        if guess:
            ctx.update(name=guess["name"], source="style", trusted=False)
    return ctx


GUEST_NOTE = ("Voix NON reconnue : tu parles peut-être à un invité. Reste aimable, mais ne révèle aucune information "
              "personnelle (mails, agenda, fichiers, domotique) et n'exécute aucune action : tu n'as que la météo, "
              "la recherche web et l'état du système. Propose de s'identifier si la demande est personnelle.")


def system_note(ctx: dict) -> str:
    parts = []
    if ctx["name"]:
        if ctx["source"] == "style":
            return (f"Indice faible : le style d'écriture évoque {ctx['name']} (peu fiable). Tu peux le saluer par son prénom "
                    "avec naturel, mais ne lui donne aucun accès ni information particulière sur cette base.")
        how = {"voice": "à sa voix", "face-live": "à son visage (vérifié en direct)"}.get(ctx["source"], "à son visage (caméra, non vérifié en direct)")
        parts.append(f"Interlocuteur actuel : {ctx['name']} (reconnu {how}). Adresse-toi à cette personne par son prénom "
                     "quand c'est naturel, sans en faire trop.")
    if ctx["guest"]:
        parts.append(GUEST_NOTE)
    return " ".join(parts)


class GuestRegistry:
    """Registre réduit pour une voix inconnue : seuls quelques outils inoffensifs."""

    def __init__(self, base):
        self._base = base

    def get(self, name):
        return self._base.get(name) if name in GUEST_TOOLS else None

    def names(self):
        return [n for n in self._base.names() if n in GUEST_TOOLS]

    def schemas(self):
        return [self._base.get(n).schema() for n in self.names() if self._base.get(n)]


# ---------- façon d'écrire (indice faible) ----------
# Empreinte = fréquences de séquences de 1 à 3 caractères (ponctuation, majuscules, abréviations, accents…), repliées
# dans un vecteur de 2048 nombres : on ne garde jamais le texte. Ne départage que des personnes DÉJÀ enregistrées
# (au moins deux profils) : elle ne peut pas reconnaître un inconnu. Indice faible, jamais une preuve d'identité.
STYLE_DIM = 2048
STYLE_MIN_TEXT = 60       # caractères minimum pour tenter une reconnaissance
STYLE_MIN_SAMPLES = 5     # textes appris minimum par personne
STYLE_MARGIN = 0.08


def style_vector(text: str):
    import numpy as np
    v = np.zeros(STYLE_DIM, dtype="float32")
    t = " " + " ".join(text.split()) + " "
    for n in (1, 2, 3):
        for i in range(len(t) - n + 1):
            v[zlib.crc32(t[i:i + n].encode("utf-8")) % STYLE_DIM] += 1.0
    v = np.log1p(v)
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


async def enroll_style(name: str, text: str) -> dict:
    text = (text or "").strip()
    if len(text) < 20:
        raise IdentityError("Texte trop court : écris au moins une ou deux phrases.")
    data = await _load()
    if name not in data["profiles"]:
        raise IdentityError("Crée d'abord le profil.")
    st = data["profiles"][name].setdefault("style", {"sum": [0.0] * STYLE_DIM, "n": 0})
    vec = style_vector(text[:4000])
    st["sum"] = [round(float(a) + float(b), 4) for a, b in zip(st["sum"], vec)]
    st["n"] = min(st["n"] + 1, 500)
    await _save(data)
    return {"samples": st["n"]}


async def identify_style(text: str) -> dict | None:
    """→ {name, score, margin} ou None si pas assez sûr. Nécessite ≥ 2 profils avec assez de textes appris."""
    import numpy as np
    if len(text.strip()) < STYLE_MIN_TEXT:
        return None
    data = await _load()
    cents = {n: np.asarray(p["style"]["sum"], dtype="float32") for n, p in data["profiles"].items()
             if p.get("style") and p["style"]["n"] >= STYLE_MIN_SAMPLES}
    if len(cents) < 2:
        return None
    mean = np.mean([c / (np.linalg.norm(c) or 1) for c in cents.values()], axis=0)
    v = style_vector(text) - mean
    scores = {}
    for n, c in cents.items():
        cc = c / (np.linalg.norm(c) or 1) - mean
        d = float(np.linalg.norm(v) * np.linalg.norm(cc))
        scores[n] = float(v @ cc / d) if d else 0.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    margin = ranked[0][1] - ranked[1][1]
    if ranked[0][1] <= 0 or margin < STYLE_MARGIN:
        return None
    return {"name": ranked[0][0], "score": round(ranked[0][1], 3), "margin": round(margin, 3)}


# ---------- visage vivant (défi en direct) ----------
# EVA demande de tourner la tête vers la gauche puis la droite (ordre tiré au hasard), en repassant par le centre,
# et vérifie à chaque image que c'est toujours la même personne reconnue. Une photo ou un écran immobile échoue ;
# une vidéo préparée ou un masque pourraient la tromper : c'est une barrière contre le « simple coup de photo ».
LIVE_TTL = 25
LIVE_YAW = 0.22
LIVE_CENTER = 0.12
_live: dict = {}


async def liveness_start() -> dict:
    now = time.time()
    for k in [k for k, v in _live.items() if now - v["t0"] > 120]:
        del _live[k]
    cid = secrets.token_urlsafe(9)
    steps = random.sample(["left", "right"], 2)
    _live[cid] = {"steps": steps, "idx": 0, "t0": now, "name": None, "centered": False, "bad": 0, "done": False}
    return {"challenge": cid, "steps": steps, "ttl": LIVE_TTL}


def _fail(cid: str, reason: str) -> dict:
    _live.pop(cid, None)
    return {"status": "failed", "reason": reason}


def live_step(ch: dict, yaw: float) -> str:
    """Fait avancer le défi avec le lacet d'une image. Renvoie 'center' (reviens face caméra), 'turn' (fais le
    mouvement demandé, `ch["steps"][ch["idx"]]`) ou 'ok' (défi réussi)."""
    if not ch["centered"]:
        if abs(yaw) < LIVE_CENTER:
            ch["centered"] = True
            return "turn"
        return "center"
    step = ch["steps"][ch["idx"]]
    if (step == "left" and yaw >= LIVE_YAW) or (step == "right" and yaw <= -LIVE_YAW):
        ch["idx"] += 1
        ch["centered"] = False  # il faut repasser par le centre avant le mouvement suivant
        return "ok" if ch["idx"] >= len(ch["steps"]) else "center"
    return "turn"


async def liveness_frame(cid: str, image_bytes: bytes) -> dict:
    ch = _live.get(cid)
    if not ch:
        return _fail(cid, "Vérification expirée : recommence.")
    if time.time() - ch["t0"] > LIVE_TTL:
        return _fail(cid, "Trop long : recommence.")
    faces = await asyncio.to_thread(face_analyze, image_bytes)
    if not faces:
        return {"status": "no_face"}
    if len(faces) > 1:
        return {"status": "multiple"}
    emb, _size, yaw = faces[0]
    data = await _load()
    name, score = _best(emb, data["profiles"], "face")
    if name is None or score < data["settings"]["face_threshold"]:
        ch["bad"] += 1
        return _fail(cid, "Visage non reconnu.") if ch["bad"] >= 3 else {"status": "unknown"}
    if ch["name"] is None:
        ch["name"] = name
    elif ch["name"] != name:
        return _fail(cid, "La personne a changé pendant la vérification.")
    res = live_step(ch, yaw)
    if res == "ok":
        _live.pop(cid, None)
        return {"status": "ok", "name": name, "token": make_token(name, "face-live")}
    return {"status": res, "step": ch["steps"][ch["idx"]], "index": ch["idx"], "yaw": round(yaw, 2)}
