import os

# Modèle Whisper : "tiny", "base", "small", "medium"... — voir faster-whisper.
# Chargé à la demande depuis le cache HuggingFace (téléchargé au 1er appel,
# nécessite un accès internet normal sur le serveur qui héberge ce service).
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
# "auto" (défaut) : GPU NVIDIA s'il est visible dans le conteneur, sinon processeur. "cpu" / "cuda" pour forcer.
# Si le GPU échoue (bibliothèques CUDA absentes…), Whisper retombe tout seul sur le processeur.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "")  # vide = float16 sur GPU, int8 sur processeur

# Voix Piper : fichiers .onnx + .onnx.json à télécharger manuellement
# (voir README) et déposer dans ce dossier, monté en volume.
VOICES_DIR = os.getenv("EVA_VOICES_DIR", "./models")
PIPER_VOICE = os.getenv("PIPER_VOICE", "fr_FR-siwis-medium")

# Même secret que EVA CORE — protège /stt et /tts. Vide = pas d'authentification.
AUTH_TOKEN = os.getenv("EVA_AUTH_TOKEN") or None

# Timbre de la synthèse : length_scale > 1 = débit plus lent et posé ; noise_scale/noise_w plus bas = voix plus
# lisse et régulière (moins « robotique saccadée »). Ajustables sans reconstruire : variables d'environnement.
PIPER_LENGTH_SCALE = float(os.getenv("PIPER_LENGTH_SCALE", "1.12"))
PIPER_NOISE_SCALE = float(os.getenv("PIPER_NOISE_SCALE", "0.5"))
PIPER_NOISE_W = float(os.getenv("PIPER_NOISE_W", "0.6"))

# Modèle Whisper de l'écoute mains libres : plus petit = bien plus rapide (base ≈ 3× plus rapide que small sur CPU).
WHISPER_FAST_MODEL_SIZE = os.getenv("WHISPER_FAST_MODEL_SIZE", "base")
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "0"))  # 0 = automatique

# --- Langues ---
# « auto » : Whisper détecte la langue (une centaine). Un code (« fr », « it »…) force une langue.
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "auto").strip().lower() or "auto"
# Langue par défaut : celle du mot d'éveil, et repli quand la détection est incertaine (phrase très courte).
DEFAULT_LANGUAGE = os.getenv("EVA_LANGUE", "fr").strip().lower() or "fr"
WHISPER_LANG_MIN_PROB = float(os.getenv("WHISPER_LANG_MIN_PROB", "0.8"))
# Voix des autres langues : téléchargées automatiquement depuis le catalogue Piper la première fois qu'il en faut une.
PIPER_AUTO_DOWNLOAD = os.getenv("PIPER_AUTO_DOWNLOAD", "1") not in ("0", "false", "no")
PIPER_DOWNLOAD_WAIT = float(os.getenv("PIPER_DOWNLOAD_WAIT", "25"))   # secondes d'attente max d'une nouvelle voix
PIPER_VOICES_URL = os.getenv("PIPER_VOICES_URL", "https://huggingface.co/rhasspy/piper-voices/resolve/main")


def voix_preferee(langue: str) -> str:
    """Voix imposée pour une langue : PIPER_VOICE_IT=it_IT-riccardo-x_low, PIPER_VOICE_EN=…"""
    return os.getenv(f"PIPER_VOICE_{langue.upper()}", "").strip()
