import io
import json
import logging
import re
import wave
from pathlib import Path

from piper import PiperVoice

from . import config, langues, lecture

try:  # piper-tts ≥ 1.3 : réglages de synthèse (vitesse, expressivité)
    from piper import SynthesisConfig
except ImportError:  # pragma: no cover - ancienne version : voix par défaut
    SynthesisConfig = None

logger = logging.getLogger("eva-voice.tts")

_voices: dict[str, PiperVoice] = {}
VOICE_RE = re.compile(r"^[A-Za-z0-9_.-]+(#[A-Za-z0-9_.-]+)?$")


class TtsError(RuntimeError):
    pass


def _paths(name: str) -> tuple[Path, Path]:
    d = Path(config.VOICES_DIR)
    return d / f"{name}.onnx", d / f"{name}.onnx.json"


def list_voices() -> list[dict]:
    """Voix installées. Un modèle multi-locuteurs donne une entrée par locuteur : « modèle#locuteur »."""
    out = []
    for onnx in sorted(Path(config.VOICES_DIR).glob("*.onnx")):
        name = onnx.name[:-len(".onnx")]
        cfg = onnx.with_name(onnx.name + ".json")
        if not cfg.exists():
            continue
        try:
            speakers = json.loads(cfg.read_text()).get("speaker_id_map") or {}
        except (OSError, ValueError):
            speakers = {}
        if len(speakers) > 1:
            out += [{"id": f"{name}#{spk}", "label": f"{name} · {spk}"} for spk in speakers]
        else:
            out.append({"id": name, "label": name})
    return out


def _load(model_name: str) -> PiperVoice:
    if model_name not in _voices:
        model_path, config_path = _paths(model_name)
        if not model_path.exists() or not config_path.exists():
            raise TtsError(
                f"Voix Piper '{model_name}' introuvable dans {config.VOICES_DIR}. "
                f"Télécharge-la avec : python -m piper.download_voices "
                f"--download-dir {config.VOICES_DIR} {model_name} "
                "(nécessite un accès internet normal — voir le README)."
            )
        logger.info("Chargement de la voix Piper '%s'", model_name)
        _voices[model_name] = PiperVoice.load(str(model_path), config_path=str(config_path))
    return _voices[model_name]


def _speaker_id(model_name: str, speaker: str | None) -> int | None:
    if not speaker:
        return None
    try:
        mapping = json.loads(_paths(model_name)[1].read_text()).get("speaker_id_map") or {}
    except (OSError, ValueError):
        return None
    return mapping.get(speaker)


def choisir_voix(text: str, voice: str | None, lang: str | None, voix_langues: dict | None = None) -> tuple[str | None, str]:
    """(voix à utiliser, langue du texte). La langue vient du client (celle que Whisper a entendue) ou du texte."""
    indice = (lang or "").split("-")[0].lower() if lang and re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z]{2})?", lang) else ""
    # Le texte décide quand il est clair ; sinon (phrase courte), la langue entendue, puis celle de la voix choisie.
    # La langue vient du TEXTE ; la langue entendue (indice) ne départage que les phrases trop courtes pour juger (« Ciao ! »).
    # Avant, une phrase française courte pouvait partir avec la voix d'une autre langue (accent bizarre) si Whisper s'était trompé.
    langue = langues.detecter(text, config.DEFAULT_LANGUAGE)
    if langue == config.DEFAULT_LANGUAGE and indice and indice != langue and len(re.findall(r"\w+", text or "")) <= 2:
        langue = indice
    choisie = voice if voice and VOICE_RE.match(voice) else None
    # Première phrase dans une nouvelle langue : on attend un peu la voix (téléchargement), sinon voix par défaut.
    prefs = {k: str(x) for k, x in (voix_langues or {}).items() if isinstance(k, str) and VOICE_RE.match(str(x))}
    v = langues.voix_pour(langue, choisie.partition("#")[0] if choisie else None, attendre=config.PIPER_DOWNLOAD_WAIT, preferees=prefs)
    if v and choisie and v == choisie.partition("#")[0]:
        v = choisie
    return v, langue


def synthesize(text: str, voice: str | None = None, speed: float | None = None, lang: str | None = None,
               voix_langues: dict | None = None) -> bytes:
    """Synthétise `text` et retourne un fichier WAV complet. `speed` : 1.0 = normal, <1 plus lent.
    Par défaut la voix est légèrement ralentie et adoucie (moins d'à-coups) : plus chaude à l'écoute.
    La voix suit la langue du texte (ou `lang`) : celle choisie par la personne pour sa langue, sinon celle de la langue."""
    voice, _langue = choisir_voix(text, voice, lang, voix_langues)
    text = lecture.preparer(text, _langue) or text
    from . import moteur
    if moteur.lire()["moteur"] == "edge":                    # voix neuronale Microsoft (en ligne), Piper en secours
        try:
            return moteur.synthese_edge(text, _langue, speed if speed and 0.6 <= speed <= 1.6 else 1.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Voix Microsoft indisponible (%s) : Piper à la place", exc)
    choice = voice if voice and VOICE_RE.match(voice) else config.PIPER_VOICE
    model_name, _, speaker = choice.partition("#")
    if not _paths(model_name)[0].exists():
        model_name, speaker = config.PIPER_VOICE, ""
    if not _paths(model_name)[0].exists():                   # voix par défaut absente (1re installation) : téléchargée
        from . import langues
        langues.telecharger_voix(model_name)
    pv = _load(model_name)

    kwargs = {}
    if SynthesisConfig is not None:
        rate = speed if speed and 0.6 <= speed <= 1.6 else 1.0
        kwargs["syn_config"] = SynthesisConfig(
            speaker_id=_speaker_id(model_name, speaker),
            length_scale=config.PIPER_LENGTH_SCALE / rate,
            noise_scale=config.PIPER_NOISE_SCALE,
            noise_w_scale=config.PIPER_NOISE_W,
        )

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        pv.synthesize_wav(text, wav_file, **kwargs)
    return buffer.getvalue()
