import logging
import threading
import wave
from pathlib import Path

from faster_whisper import WhisperModel

from . import config

logger = logging.getLogger("eva-voice.stt")

_models: dict[str, WhisperModel] = {}
_lock = threading.Lock()
_state: dict = {"device": None, "compute": None, "fallback_reason": ""}
GPU_ERRORS = ("cuda", "cublas", "cudnn", "libcu", "gpu", "out of memory")


class SttError(RuntimeError):
    pass


def _gpu_count() -> int:
    try:
        import ctranslate2
        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # noqa: BLE001 — ctranslate2 sans CUDA, ou absent
        return 0


def resolve_device() -> tuple[str, str]:
    """(périphérique, type de calcul) : GPU si demandé/visible, sinon processeur."""
    if _state["device"]:
        return _state["device"], _state["compute"]
    want = (config.WHISPER_DEVICE or "auto").lower()
    dev = "cuda" if (want == "cuda" or (want == "auto" and _gpu_count() > 0)) else "cpu"
    compute = config.WHISPER_COMPUTE_TYPE or ("float16" if dev == "cuda" else "int8")
    _state.update(device=dev, compute=compute)
    return dev, compute


def _fall_back_to_cpu(reason: str) -> None:
    logger.warning("Whisper : GPU inutilisable (%s) — bascule sur le processeur (plus lent)", reason)
    _state.update(device="cpu", compute="int8" if not config.WHISPER_COMPUTE_TYPE or config.WHISPER_COMPUTE_TYPE.startswith("float") else config.WHISPER_COMPUTE_TYPE,
                  fallback_reason=str(reason)[:200])
    _models.clear()


def info() -> dict:
    dev, compute = resolve_device()
    return {"device": dev, "compute_type": compute, "gpu_visible": _gpu_count() > 0, "fallback_reason": _state["fallback_reason"]}


def _get_model(size: str | None = None) -> WhisperModel:
    size = size or config.WHISPER_MODEL_SIZE
    with _lock:
        return _get_locked(size)


def _get_locked(size: str) -> WhisperModel:
    if size not in _models:
        device, compute = resolve_device()
        logger.info("Chargement du modèle Whisper '%s' (%s/%s) — peut télécharger le modèle si absent du cache", size, device, compute)
        try:
            try:
                _models[size] = WhisperModel(size, device=device, compute_type=compute, cpu_threads=config.WHISPER_THREADS)
            except Exception as exc:  # noqa: BLE001 — GPU demandé mais inutilisable : on retente sur le processeur
                if device != "cuda":
                    raise
                _fall_back_to_cpu(f"{type(exc).__name__}: {exc}")
                device, compute = resolve_device()
                _models[size] = WhisperModel(size, device=device, compute_type=compute, cpu_threads=config.WHISPER_THREADS)
        except Exception as exc:  # noqa: BLE001
            raise SttError(
                f"Impossible de charger le modèle Whisper '{size}' : {exc}. "
                "Vérifie que le serveur a accès à Internet au premier lancement "
                "(le modèle se télécharge depuis Hugging Face), ou pré-télécharge-le."
            ) from exc
    return _models[size]


def warm_up() -> None:
    """Charge les modèles au démarrage (en tâche de fond) : la première phrase n'attend plus le chargement."""
    for size in dict.fromkeys([config.WHISPER_FAST_MODEL_SIZE, config.WHISPER_MODEL_SIZE]):
        try:
            _get_model(size)
        except SttError as exc:
            logger.warning("Préchargement Whisper '%s' impossible : %s", size, exc)


PROMPT = "EVA, Éva. Hey Éva, dis Éva. Conversation en français avec Éva, l'assistante de la maison."
PROMPT_NEUTRE = "EVA, Éva."


def _load_wav(path: Path):
    """WAV PCM 16 bits mono/stéréo → tableau float32 (rééchantillonné à 16 kHz si besoin). None si autre format.
    Évite de passer par PyAV/ffmpeg pour les segments de l'écoute mains libres (déjà en WAV 16 kHz)."""
    try:
        import numpy as np
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                return None
            rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
            data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        if rate != 16000 and len(data):
            data = np.interp(np.linspace(0, len(data) - 1, int(len(data) * 16000 / rate)), np.arange(len(data)), data).astype(np.float32)
        return data
    except Exception:  # noqa: BLE001 — pas un WAV lisible : on laisse la bibliothèque décoder
        return None


def _decode_with_av(path: Path):
    """Décodage maison (webm, mp3…) avec PyAV SANS l'option `metadata_errors` que faster-whisper passe et que
    certaines versions de PyAV ne connaissent pas. None si PyAV est absent ou échoue."""
    try:
        import av
        import numpy as np
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        parts = []
        with av.open(str(path)) as container:
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1))
            for out in resampler.resample(None) or []:
                parts.append(out.to_ndarray().reshape(-1))
        if not parts:
            return None
        return np.concatenate(parts).astype(np.float32) / 32768.0
    except Exception:  # noqa: BLE001
        logger.warning("Décodage PyAV maison impossible", exc_info=True)
        return None


def _run(model, audio_path: Path, language: str | None, beam: int, **extra) -> tuple[str, str, float]:
    """→ (texte, langue, certitude de la langue). language=None : Whisper détecte la langue."""
    audio = _load_wav(audio_path)
    if audio is None:
        audio = _decode_with_av(audio_path)
    segments, info = model.transcribe(audio if audio is not None else str(audio_path), language=language, beam_size=beam,
                                      condition_on_previous_text=False, **extra)
    texte = " ".join(segment.text.strip() for segment in segments).strip()
    return texte, (getattr(info, "language", None) or language or config.DEFAULT_LANGUAGE), float(getattr(info, "language_probability", 1.0) or 0)


def _detecter_langue(audio_path: Path) -> tuple[str, float]:
    """Langue parlée (Whisper, sur les 30 premières secondes) → (code, certitude). Échec : langue par défaut."""
    try:
        audio = _load_wav(audio_path)
        if audio is None:
            audio = _decode_with_av(audio_path)
        if audio is None:
            return config.DEFAULT_LANGUAGE, 0.0
        model = _get_model(None)
        langue, proba, _toutes = model.detect_language(audio, vad_filter=True)
        return langue or config.DEFAULT_LANGUAGE, float(proba or 0)
    except Exception:  # noqa: BLE001 — ancienne faster-whisper, audio vide… : on reste sur la langue par défaut
        return config.DEFAULT_LANGUAGE, 0.0


def transcribe_lang(audio_path: Path, fast: bool = False) -> tuple[str, str]:
    """Transcrit dans la langue parlée → (texte, code langue).
    La langue est d'abord DÉTECTÉE ; puis la transcription se fait dans cette langue, avec le prompt français si c'est du
    français (bien plus juste qu'une transcription « auto » sans prompt). Une autre langue n'est retenue que si Whisper en
    est sûr (WHISPER_LANG_MIN_PROB, 0,8 par défaut) : sinon français. fast=True (mot d'éveil) : petit modèle, français."""
    if fast:
        return transcribe(audio_path, config.DEFAULT_LANGUAGE, fast=True), config.DEFAULT_LANGUAGE
    if config.WHISPER_LANGUAGE != "auto":
        langue = config.WHISPER_LANGUAGE
    else:
        langue, proba = _avec_repli_gpu(lambda: _detecter_langue(audio_path))
        if langue != config.DEFAULT_LANGUAGE and proba < config.WHISPER_LANG_MIN_PROB:
            logger.info("Langue incertaine (%s, %.2f) : transcription en %s", langue, proba, config.DEFAULT_LANGUAGE)
            langue = config.DEFAULT_LANGUAGE
    texte, _l, _p = _avec_repli_gpu(lambda: _transcribe_full(audio_path, langue, False))
    return texte, langue


def _avec_repli_gpu(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        if resolve_device()[0] == "cuda" and any(k in str(exc).lower() for k in GPU_ERRORS):
            _fall_back_to_cpu(f"{type(exc).__name__}: {exc}")
            return fn()
        raise


def transcribe(audio_path: Path, language: str = "fr", fast: bool = False) -> str:
    try:
        return _transcribe(audio_path, language, fast)
    except Exception as exc:  # noqa: BLE001
        # Les bibliothèques CUDA manquantes ne se révèlent souvent qu'au premier calcul, pas au chargement.
        if resolve_device()[0] == "cuda" and any(k in str(exc).lower() for k in GPU_ERRORS):
            _fall_back_to_cpu(f"{type(exc).__name__}: {exc}")
            return _transcribe(audio_path, language, fast)
        raise


def _transcribe(audio_path: Path, language: str = "fr", fast: bool = False) -> str:
    return _transcribe_full(audio_path, language, fast)[0]


def _transcribe_full(audio_path: Path, language: str | None = "fr", fast: bool = False) -> tuple[str, str, float]:
    """fast=True : écoute du mot d'éveil (beam 1, plus rapide). Le filtre de silence évite que Whisper
    invente du texte sur du bruit ; le prompt aide à reconnaître « Éva ». Si ces options avancées échouent
    (version de bibliothèque, VAD indisponible…), on retombe sur une transcription simple."""
    model = _get_model(config.WHISPER_FAST_MODEL_SIZE if fast else None)
    beam = 1 if fast else 5
    try:
        # Le prompt français aide à reconnaître « Éva » mais pousserait vers le français : neutre en détection automatique.
        prompt = PROMPT if language == "fr" else PROMPT_NEUTRE
        return _run(model, audio_path, language, beam, vad_filter=True, initial_prompt=prompt, no_speech_threshold=0.6,
                    without_timestamps=True, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Transcription avancée en échec (%s: %s) — nouvel essai simple", type(exc).__name__, exc, exc_info=True)
    try:
        return _run(model, audio_path, language, beam)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Transcription en échec")
        raise SttError(f"Whisper a échoué : {type(exc).__name__}: {exc}") from exc
