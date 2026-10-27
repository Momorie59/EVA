import asyncio
import re
import logging
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import langues, stt, tts
from .config import AUTH_TOKEN, PIPER_VOICE, VOICES_DIR, WHISPER_MODEL_SIZE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eva-voice")

logger.info("Accès /stt et /tts : décidé par EVA CORE (libre tant que la connexion n'est pas activée dans Paramètres › Sécurité).")

app = FastAPI(title="EVA VOICE")


@app.on_event("startup")
async def _warm_models() -> None:
    import threading
    threading.Thread(target=stt.warm_up, daemon=True, name="whisper-warmup").start()

    def _voix_par_defaut():                       # première installation : la voix française se télécharge toute seule
        from . import config as _c, langues as _l
        _l.telecharger_voix(_c.PIPER_VOICE)
    threading.Thread(target=_voix_par_defaut, daemon=True, name="voix-defaut").start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


CORE_URL = os.getenv("EVA_CORE_URL", "http://eva-core:8000").rstrip("/")
_ok_until: dict[str, float] = {}


def _ask_core(authorization: str | None) -> int | None:
    """Demande à EVA CORE si cette requête est autorisée (jeton ou session de connexion). None = EVA CORE injoignable."""
    req = urllib.request.Request(f"{CORE_URL}/api/auth/verify", headers={"Authorization": authorization} if authorization else {})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001
        return None


async def verify_token(authorization: str | None = Header(default=None)) -> None:
    """Même règle que EVA CORE : libre tant qu'EVA n'est pas protégée, sinon jeton EVA_AUTH_TOKEN ou session de connexion valide."""
    if AUTH_TOKEN and authorization == f"Bearer {AUTH_TOKEN}":
        return
    key = authorization or ""
    now = time.time()
    if _ok_until.get(key, 0) > now:
        return
    status = await asyncio.to_thread(_ask_core, authorization)
    if status == 200:
        _ok_until[key] = now + 20
        if len(_ok_until) > 200:
            for k in [k for k, v in _ok_until.items() if v < now]:
                _ok_until.pop(k, None)
        return
    if status is None:
        raise HTTPException(status_code=503, detail="EVA CORE injoignable : impossible de vérifier la connexion.")
    raise HTTPException(status_code=401, detail="Connexion requise.")


class TtsRequest(BaseModel):
    text: str
    voice: str | None = None
    speed: float | None = None
    lang: str | None = None          # langue entendue par Whisper (sinon devinée depuis le texte)
    voix_langues: dict[str, str] | None = None   # voix choisie langue par langue dans l'interface


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "whisper_model": WHISPER_MODEL_SIZE,
        "whisper": stt.info(),
        "piper_voice": PIPER_VOICE,
        "voices_dir": VOICES_DIR,
        "piper_voice_present": (Path(VOICES_DIR) / f"{PIPER_VOICE}.onnx").exists()
        and (Path(VOICES_DIR) / f"{PIPER_VOICE}.onnx.json").exists(),
    }


@app.get("/voices", dependencies=[Depends(verify_token)])
async def voices():
    return {"default": PIPER_VOICE, "voices": tts.list_voices(), "langues": langues.etat(), "noms": langues.NOMS}


@app.get("/moteur", dependencies=[Depends(verify_token)])
async def moteur_lire():
    from . import moteur
    return moteur.lire()


class MoteurRequest(BaseModel):
    moteur: str | None = None
    voix_edge: dict[str, str] | None = None


@app.put("/moteur", dependencies=[Depends(verify_token)])
async def moteur_ecrire(body: MoteurRequest):
    from . import moteur
    if body.moteur not in (None, "piper", "edge"):
        raise HTTPException(status_code=400, detail="Moteur : piper ou edge.")
    return moteur.ecrire(body.moteur, body.voix_edge)


@app.get("/moteur/voix/{langue}", dependencies=[Depends(verify_token)])
async def moteur_voix(langue: str):
    from . import moteur
    if not re.fullmatch(r"[a-z]{2,3}", langue):
        raise HTTPException(status_code=400, detail="Langue invalide.")
    try:
        return {"voix": await asyncio.to_thread(moteur.voix_disponibles, langue)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Catalogue Microsoft injoignable : {exc}") from exc


@app.get("/voix/langue/{langue}", dependencies=[Depends(verify_token)])
async def voix_langue(langue: str):
    """Voix Piper disponibles pour une langue (catalogue officiel), installées en premier."""
    if not re.fullmatch(r"[a-z]{2,3}", langue):
        raise HTTPException(status_code=400, detail="Langue invalide.")
    return {"langue": langue, "nom": langues.NOMS.get(langue, langue), "voix": await asyncio.to_thread(langues.voix_de_langue, langue)}


class VoixRequest(BaseModel):
    voix: str


@app.post("/voix/telecharger", dependencies=[Depends(verify_token)])
async def voix_telecharger(body: VoixRequest):
    cle = body.voix.partition("#")[0]
    if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)", cle):
        raise HTTPException(status_code=400, detail="Voix invalide.")
    langues.preparer_voix(cle)
    return {"ok": True, "voix": cle}


@app.post("/stt", dependencies=[Depends(verify_token)])
async def speech_to_text(audio: UploadFile = File(...), mode: str = ""):
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    data = await audio.read()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            text, langue = await asyncio.to_thread(stt.transcribe_lang, Path(tmp.name), mode == "fast")
        except stt.SttError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if text and mode != "fast":
        langues.preparer(langue)        # nouvelle langue : la voix se télécharge pendant qu'EVA réfléchit
    return {"text": text, "language": langue}


@app.post("/tts", dependencies=[Depends(verify_token)])
async def text_to_speech(payload: TtsRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        wav_bytes = await asyncio.to_thread(tts.synthesize, payload.text, payload.voice, payload.speed, payload.lang,
                                          payload.voix_langues)
    except tts.TtsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(content=wav_bytes, media_type="audio/wav")
