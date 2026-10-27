"""Spotify : ce qui joue, lancer un artiste / morceau / playlist, pause, suivant, volume, appareils."""
from typing import Any

from ... import spotify
from ..permissions import Permission
from .base import Tool


async def _sur(coro) -> dict:
    try:
        return await coro
    except spotify.SpotifyError as exc:
        return {"error": str(exc)}


class SpotifyEnCoursTool(Tool):
    name = "spotify_en_cours"
    description = "Ce qui joue sur Spotify (morceau, artiste, appareil, volume) et la liste des appareils Spotify disponibles."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        try:
            r = await spotify.en_cours()
            r["appareils"] = [a["nom"] for a in await spotify.appareils()]
            return r
        except spotify.SpotifyError as exc:
            return {"error": str(exc)}


class SpotifyJouerTool(Tool):
    name = "spotify_jouer"
    description = ("Lance de la musique sur Spotify : un artiste (« mets du Daft Punk »), un morceau, un album ou une playlist ; "
                   "sans recherche = reprendre la lecture. appareil = nom de l'enceinte / du téléphone (facultatif).")
    parameters = {"type": "object", "properties": {
        "recherche": {"type": "string", "description": "Ce qu'il faut jouer (vide = reprendre)"},
        "genre": {"type": "string", "enum": ["artiste", "morceau", "album", "playlist", ""]},
        "appareil": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, recherche: str = "", genre: str = "", appareil: str = "", **_: Any) -> dict:
        return await _sur(spotify.jouer(str(recherche or ""), str(genre or ""), str(appareil or "")))


class SpotifyCommandeTool(Tool):
    name = "spotify_commande"
    description = "Pilote Spotify : pause, suivant, precedent, volume (0-100), aleatoire (oui/non), transferer (vers un autre appareil)."
    parameters = {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["pause", "suivant", "precedent", "volume", "aleatoire", "transferer"]},
        "valeur": {"type": "string", "description": "Volume ou oui/non"},
        "appareil": {"type": "string"}}, "required": ["action"]}
    permission = Permission.AUTO

    async def execute(self, action: str = "", valeur: str = "", appareil: str = "", **_: Any) -> dict:
        return await _sur(spotify.commande(str(action), valeur, str(appareil or "")))
