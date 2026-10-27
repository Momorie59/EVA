"""Accès interne d'eva-core au service voix (synthèse d'une annonce pour une enceinte Google, par exemple).

Clé aléatoire tirée au démarrage, jamais écrite nulle part : eva-voice la fait vérifier par eva-core (/api/auth/verify)."""
import os
import secrets

import httpx

CLE = "evainterne_" + secrets.token_urlsafe(32)
URL = os.getenv("EVA_VOICE_INTERNE", "http://eva-voice:8100")


def est_cle(jeton: str | None) -> bool:
    return bool(jeton) and secrets.compare_digest(jeton, CLE)


async def synthese(texte: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as cl:
        r = await cl.post(f"{URL}/tts", json={"text": texte[:900]}, headers={"Authorization": f"Bearer {CLE}"})
    if r.status_code != 200:
        raise RuntimeError(f"Service voix indisponible ({r.status_code}).")
    return r.content
