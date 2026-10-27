"""Google Home, Nest et Chromecast en direct (comme Jarvis), par le protocole Cast du réseau de la maison.

Les enceintes et TV trouvées par la détection réseau s'ajoutent comme appareils (pilote « cast ») : volume, pause / lecture,
arrêt, état (ce qui joue). Annonces vocales : EVA fabrique la phrase avec sa voix (eva-voice), la dépose sur eva-scanner
(adresse http du réseau local, valable 5 minutes) et demande à l'enceinte de la lire."""
import asyncio

import httpx

from .config import settings


class CastError(RuntimeError):
    pass


def _connecter(ip: str, port: int = 8009):
    try:
        import pychromecast
    except ImportError as exc:
        raise CastError("Module pychromecast absent : reconstruis eva-core.") from exc
    try:
        cc = pychromecast.get_chromecast_from_host((ip, int(port or 8009), None, None, None), tries=2, timeout=8)
        cc.wait(timeout=10)
    except Exception as exc:  # noqa: BLE001
        raise CastError(f"L'enceinte {ip} ne répond pas ({type(exc).__name__}).") from exc
    return cc


def _faire(ip: str, port: int, action: str, valeur=None, url: str = "", type_media: str = "audio/wav") -> dict:
    cc = _connecter(ip, port)
    try:
        mc = cc.media_controller
        if action == "state":
            st = cc.status
            ms = mc.status
            return {"on": bool(st and st.display_name and st.display_name != "Backdrop" and not st.is_stand_by),
                    "app": getattr(st, "display_name", "") or "", "volume": round((getattr(st, "volume_level", 0) or 0) * 100),
                    "titre": getattr(ms, "title", "") or "", "artiste": getattr(ms, "artist", "") or "", "lecture": getattr(ms, "player_state", "") or ""}
        if action == "brightness":                              # « intensité » d'une enceinte = volume
            cc.set_volume(max(0, min(100, int(valeur))) / 100)
        elif action == "on":
            mc.play()
        elif action == "toggle":
            mc.update_status()
            (mc.pause if mc.status.player_state == "PLAYING" else mc.play)()
        elif action == "off":
            cc.quit_app()
        elif action == "pause":
            mc.pause()
        elif action == "media":
            mc.play_media(url, type_media)
            mc.block_until_active(timeout=10)
        elif action == "youtube":                               # vidéo YouTube sur la TV (Chromecast, Google TV)
            from pychromecast.controllers.youtube import YouTubeController
            yt = YouTubeController()
            cc.register_handler(yt)
            yt.play_video(str(valeur))
        elif action == "suivant":
            mc.queue_next()
        elif action == "precedent":
            mc.queue_prev()
        elif action == "muet":
            cc.set_volume_muted(not bool(getattr(cc.status, "volume_muted", False)))
        elif action == "avancer":
            mc.update_status()
            mc.seek(max(0, (mc.status.current_time or 0) + int(valeur or 30)))
        else:
            raise CastError(f"Action non prise en charge par une enceinte : {action}.")
        return {"ok": True}
    finally:
        try:
            cc.disconnect(timeout=3)
        except Exception:  # noqa: BLE001
            pass


async def piloter(cfg: dict, action: str, value, pct_de=None) -> dict:
    if action == "brightness" and pct_de:
        value = pct_de(value)
    return await asyncio.to_thread(_faire, cfg["ip"], int(cfg.get("port") or 8009), action, value)


async def annoncer(cfg: dict, texte: str) -> dict:
    from . import voix_interne
    from .lan_discovery import _scanner_headers
    if not settings.scanner_url:
        raise CastError("eva-scanner est nécessaire pour les annonces sur les enceintes Google.")
    try:
        wav = await voix_interne.synthese(texte)
    except Exception as exc:  # noqa: BLE001
        raise CastError(f"Voix d'EVA indisponible : {exc}") from exc
    async with httpx.AsyncClient(timeout=20) as cl:
        r = await cl.post(settings.scanner_url.rstrip("/") + "/audio", params={"vers": cfg["ip"]}, content=wav, headers=_scanner_headers())
    if r.status_code >= 300:
        raise CastError("eva-scanner n'a pas accepté l'annonce : reconstruis-le (docker compose up -d --build eva-scanner).")
    return await asyncio.to_thread(_faire, cfg["ip"], int(cfg.get("port") or 8009), "media", None, r.json()["url"])


_YT = __import__("re").compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def id_youtube(texte: str) -> str | None:
    t = (texte or "").strip()
    if __import__("re").fullmatch(r"[A-Za-z0-9_-]{11}", t):
        return t
    m = _YT.search(t)
    return m.group(1) if m else None


TYPES_MEDIA = {".mp3": "audio/mpeg", ".aac": "audio/aac", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".wav": "audio/wav", ".flac": "audio/flac",
               ".mp4": "video/mp4", ".webm": "video/webm", ".m3u8": "application/x-mpegURL", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".png": "image/png"}


async def diffuser(cfg: dict, action: str, valeur: str = "", url: str = "") -> dict:
    """TV et enceintes : youtube (identifiant), media (lien direct : radio, vidéo, image), suivant, precedent, muet, avancer, pause, on, off, state, brightness (volume)."""
    type_media = "audio/mpeg"
    if action == "media":
        from urllib.parse import urlparse
        ext = "." + urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path.rsplit("/", 1)[-1] else ""
        type_media = TYPES_MEDIA.get(ext, "audio/mpeg")
    return await asyncio.to_thread(_faire, cfg["ip"], int(cfg.get("port") or 8009), action, valeur, url, type_media)
