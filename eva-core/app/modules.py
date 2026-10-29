"""Modules facultatifs, activés par l'administrateur dans Paramètres › Modules : Wiki, Livre de recettes.

Un module coupé disparaît pour tout le monde (menu, pages, outils d'EVA) ; ses données restent sur le NAS et reviennent
quand on le rallume. Un module allumé suit ensuite les droits habituels par personne (fonctionnalités « wiki », « recettes »)."""
import json

from .db import get_pool

KV = "modules"
MODULES = {
    "wiki": {"label": "Wiki", "icon": "📚", "hint": "Pages de la famille (modes d'emploi, contacts, procédures…) et pages personnelles, avec historique. EVA s'en sert pour répondre."},
    "recettes": {"label": "Livre de recettes", "icon": "🍲", "hint": "Recettes avec photos, étapes et vidéos, belle mise en page, partage par lien ou PDF, liste de courses en un clic."},
    "finances": {"label": "Finances personnelles", "icon": "💶", "hint": "Comptes, relevés importés (CSV, OFX), catégories automatiques, budgets du mois. Strictement privé : chacun ne voit que ses finances, pas même l'administrateur."},
    "inventaire": {"label": "Inventaire et prêts", "icon": "📦", "hint": "Où est rangée chaque chose (pièce › meuble › tiroir) et à qui on l'a prêtée : « où est la perceuse ? », « j'ai prêté la tondeuse à Paul »."},
    "contenus": {"label": "Suivi de contenus", "icon": "🎬", "hint": "Idées → brouillon → programmé → publié pour tes vidéos et publications (YouTube, Instagram, TikTok, Twitch…), calendrier de publication."},
}
# Ce que chaque module ouvre : adresses de l'API (coupées → 404) et préfixes de ses outils (retirés à EVA).
_API = {"wiki": ("/api/wiki", "/api/public/wiki"), "recettes": ("/api/recettes", "/api/public/recettes"),
        "finances": ("/api/finances",), "contenus": ("/api/contenus",), "inventaire": ("/api/inventaire",)}
_OUTILS = {"wiki": ("wiki_",), "recettes": ("recette_",), "finances": ("finances_",), "contenus": ("contenu_",), "inventaire": ("inventaire_",)}


def api_coupee(chemin: str) -> bool:
    return any(chemin.startswith(pre) and not actif(m) for m, pre in _API.items())


def outil_coupe(nom: str) -> bool:
    return any(nom.startswith(pre) and not actif(m) for m, pre in _OUTILS.items())
_cache: dict = {}


async def charger() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    _cache.clear()
    _cache.update({k: bool(d.get(k, False)) for k in MODULES})
    return dict(_cache)


def actif(nom: str) -> bool:
    return bool(_cache.get(nom, False))


async def regler(changes: dict) -> dict:
    d = await charger()
    for k, v in changes.items():
        if k in MODULES:
            d[k] = bool(v)
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    return await charger()


def coupes() -> frozenset:
    return frozenset(k for k in MODULES if not _cache.get(k, False))
