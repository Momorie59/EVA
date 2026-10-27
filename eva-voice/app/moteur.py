"""Moteur de la voix d'EVA : Piper (sur le serveur, rien ne sort) ou voix neuronales Microsoft en ligne (bien plus naturelles,
comme Edge ou Windows ; le texte lu part chez Microsoft). Choix gardé dans le dossier des voix (moteur.json).
En cas de souci réseau, EVA retombe toute seule sur Piper."""
import asyncio
import io
import json
import logging
import wave
from pathlib import Path

from . import config

logger = logging.getLogger("eva-voice.moteur")
DEFAUT = {"moteur": "piper", "voix_edge": {"fr": "fr-FR-DeniseNeural", "en": "en-US-AvaMultilingualNeural", "it": "it-IT-ElsaNeural",
                                            "es": "es-ES-ElviraNeural", "de": "de-DE-KatjaNeural", "pt": "pt-PT-RaquelNeural",
                                            "nl": "nl-NL-FennaNeural"}}
_cache_voix: list | None = None


def _fichier() -> Path:
    return Path(config.VOICES_DIR) / "moteur.json"


def lire() -> dict:
    try:
        d = json.loads(_fichier().read_text())
    except (OSError, ValueError):
        d = {}
    return {"moteur": d.get("moteur", DEFAUT["moteur"]), "voix_edge": {**DEFAUT["voix_edge"], **(d.get("voix_edge") or {})}}


def ecrire(moteur: str | None = None, voix_edge: dict | None = None) -> dict:
    d = lire()
    if moteur in ("piper", "edge"):
        d["moteur"] = moteur
    if isinstance(voix_edge, dict):
        d["voix_edge"].update({k: str(v)[:80] for k, v in voix_edge.items() if isinstance(k, str) and len(k) <= 3})
    _fichier().parent.mkdir(parents=True, exist_ok=True)
    _fichier().write_text(json.dumps(d, indent=1))
    return d


def voix_disponibles(langue: str = "") -> list[dict]:
    """Voix Microsoft (catalogue en ligne, gardé en mémoire)."""
    global _cache_voix
    if _cache_voix is None:
        import edge_tts
        _cache_voix = asyncio.run(edge_tts.list_voices())
    out = []
    for v in _cache_voix:
        loc = v.get("Locale", "")
        if langue and not loc.lower().startswith(langue.lower()):
            continue
        out.append({"id": v.get("ShortName", ""), "nom": v.get("FriendlyName", v.get("ShortName", "")), "locale": loc, "genre": v.get("Gender", "")})
    return sorted(out, key=lambda x: (x["locale"], x["id"]))


def synthese_edge(texte: str, langue: str, vitesse: float = 1.0) -> bytes:
    """Texte → WAV (mono 24 kHz) avec une voix Microsoft. Lève une exception si le service ne répond pas."""
    import av
    import edge_tts
    voix = lire()["voix_edge"].get(langue) or DEFAUT["voix_edge"].get(langue) or DEFAUT["voix_edge"]["fr"]
    rate = f"{int(round((vitesse - 1) * 100)):+d}%"

    async def flux() -> bytes:
        mp3 = bytearray()
        async for morceau in edge_tts.Communicate(texte, voix, rate=rate).stream():
            if morceau.get("type") == "audio":
                mp3.extend(morceau["data"])
        return bytes(mp3)
    mp3 = asyncio.run(asyncio.wait_for(flux(), 20))
    if not mp3:
        raise RuntimeError("voix Microsoft : réponse vide")
    sortie = io.BytesIO()
    with av.open(io.BytesIO(mp3)) as conteneur, wave.open(sortie, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=24000)
        for trame in conteneur.decode(audio=0):
            for t in rs.resample(trame):
                w.writeframes(t.to_ndarray().tobytes())
        for t in rs.resample(None):
            w.writeframes(t.to_ndarray().tobytes())
    return sortie.getvalue()
