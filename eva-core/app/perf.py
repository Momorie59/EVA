"""Vitesse du serveur IA : modèles en mémoire vidéo, rechargements, vitesse de lecture et d'écriture.

Sur une carte de 6 Go, deux modèles (principal + rapide) ne tiennent pas toujours ensemble : passer de l'un à l'autre
oblige Ollama à recharger un modèle (plusieurs secondes). EVA évite ces rechargements (voir router.select et fil.py :
on prend le modèle déjà chargé quand il peut répondre) et les mesure ici pour l'afficher dans Paramètres › Intelligence."""
import time
from collections import deque

import httpx

from .config import settings

RECHARGEMENT_MS = 1500              # au-delà, le chargement compte comme un rechargement de modèle
_tours: deque = deque(maxlen=300)
_charges: dict = {"at": 0.0, "models": None}


def noter(model: str, data: dict) -> dict:
    """Mesures d'Ollama en fin de réponse (durées en nanosecondes) → dict en millisecondes, gardé pour les statistiques."""
    ms = lambda k: int((data.get(k) or 0) / 1e6)          # noqa: E731
    t = {"ts": time.time(), "model": model, "load_ms": ms("load_duration"), "prompt_tokens": data.get("prompt_eval_count") or 0,
         "prompt_ms": ms("prompt_eval_duration"), "gen_tokens": data.get("eval_count") or 0, "gen_ms": ms("eval_duration"),
         "total_ms": ms("total_duration")}
    _tours.append(t)
    return t


async def modeles_charges(max_age: float = 3.0) -> list[dict] | None:
    """Modèles actuellement en mémoire sur Ollama (/api/ps), avec la part en mémoire vidéo. None si injoignable."""
    if _charges["models"] is not None and time.monotonic() - _charges["at"] < max_age:
        return _charges["models"]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_host.rstrip('/')}/api/ps")
        if r.status_code != 200:
            return None
        out = [{"name": m.get("name") or m.get("model"), "size_gb": round((m.get("size") or 0) / 1e9, 2),
                "vram_gb": round((m.get("size_vram") or 0) / 1e9, 2), "until": m.get("expires_at")} for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return None
    _charges.update(at=time.monotonic(), models=out)
    return out


async def est_charge(model: str) -> bool | None:
    charges = await modeles_charges()
    if charges is None:
        return None
    return any(m["name"] == model or m["name"] == f"{model}:latest" for m in charges)


async def resume(fenetre_s: int = 3600) -> dict:
    depuis = time.time() - fenetre_s
    tours = [t for t in _tours if t["ts"] >= depuis]
    rech = [t for t in tours if t["load_ms"] >= RECHARGEMENT_MS]
    vit = lambda n, d: round(sum(t[n] for t in tours) / max(1, sum(t[d] for t in tours)) * 1000, 1) if sum(t[d] for t in tours) else None  # noqa: E731
    charges = await modeles_charges(0)
    conseil = ""
    if len(rech) >= 3 and len({t["model"] for t in rech}) >= 2:
        conseil = ("Plusieurs modèles se remplacent en mémoire vidéo : chaque changement coûte quelques secondes. "
                   "Choisis un modèle rapide plus petit (ex. llama3.2:1b) ou aucun modèle rapide (Paramètres › Intelligence › Choix automatique).")
    elif charges and any(m["vram_gb"] < m["size_gb"] * 0.95 for m in charges):
        conseil = "Un modèle déborde de la mémoire vidéo vers la mémoire normale : il répond beaucoup plus lentement. Un modèle plus petit irait plus vite."
    return {"tours": len(tours), "rechargements": len(rech),
            "rechargement_moyen_ms": int(sum(t["load_ms"] for t in rech) / len(rech)) if rech else 0,
            "lecture_tokens_s": vit("prompt_tokens", "prompt_ms"), "ecriture_tokens_s": vit("gen_tokens", "gen_ms"),
            "charges": charges, "derniers": list(_tours)[-8:][::-1], "conseil": conseil}
