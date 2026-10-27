"""APIs publiques : un catalogue hors ligne (≈2000 APIs gratuites, issu du dépôt public-apis) et un appel GET sécurisé.

api_search  -> trouve une API par thème / mot-clé (sans clé par défaut).
api_get     -> appelle une URL d'API publique en GET et renvoie le JSON (hôtes publics seulement, sans clé secrète)."""
import asyncio
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from ..permissions import Permission
from .base import Tool
from .web import USER_AGENT, _check_url_safe

CATALOG_FILE = Path(__file__).resolve().parents[2] / "data" / "public_apis.json"
MAX_RESULT_CHARS = 6000
MAX_REDIRECTS = 4
_cache: list[dict] | None = None


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def set_catalog(entries: list[dict]) -> None:
    """Remplace le catalogue en mémoire (copie plus récente téléchargée)."""
    global _cache
    _cache = list(entries)


def catalog() -> list[dict]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = []
    return _cache


# mots français courants -> équivalents anglais du catalogue (les descriptions sont en anglais)
FR_EN = {"meteo": "weather", "pays": "country countries", "capitale": "capital", "devise": "currency exchange", "change": "exchange currency",
         "ferie": "holiday", "feries": "holidays", "jours": "days", "livre": "book books", "livres": "books", "recette": "recipe food meal",
         "cuisine": "food", "cocktail": "cocktail drink", "blague": "joke", "film": "movie", "films": "movies", "musique": "music",
         "chien": "dog", "chat": "cat", "animaux": "animals", "espace": "space", "nasa": "nasa", "bourse": "stock", "crypto": "cryptocurrency",
         "actualite": "news", "actualites": "news", "sport": "sports", "jeu": "game", "jeux": "games", "traduction": "translation",
         "adresse": "geocoding address", "carte": "map", "vol": "flight", "avion": "flight aircraft", "train": "transport train",
         "citation": "quotes quote", "histoire": "history", "art": "art", "photo": "photography", "image": "image", "sante": "health",
         "covid": "covid", "plante": "plants", "ville": "city", "villes": "cities", "code postal": "postal code zip", "soleil": "sun sunrise sunset"}


def search(query: str, category: str = "", keyless_only: bool = True, limit: int = 8) -> list[dict]:
    words: list[str] = []
    for w in re.findall(r"[a-z0-9]+", _fold(query)):
        words.append(w)
        words.extend(FR_EN.get(w, "").split())
    words = [w for w in dict.fromkeys(words) if len(w) > 2 or w.isdigit()]
    cat = _fold(category)
    scored = []
    for e in catalog():
        if keyless_only and e["a"]:
            continue
        if cat and cat not in _fold(e["c"]):
            continue
        hay = _fold(f"{e['n']} {e['d']} {e['c']}")
        name = _fold(e["n"])
        score = sum((3 if w in name else 2 if w in _fold(e["c"]) else 1) for w in words if w in hay)
        if words and not score:
            continue
        scored.append((score + (0.5 if e["h"] else 0), e))
    scored.sort(key=lambda t: -t[0])
    return [e for _s, e in scored[:max(1, min(limit, 15))]]


def categories() -> list[str]:
    return sorted({e["c"] for e in catalog()})


class ApiSearchTool(Tool):
    name = "api_search"
    description = ("Cherche dans un catalogue de ~2000 API publiques gratuites (météo, pays, devises, jours fériés, recettes, livres, espace, blagues…). "
                   "Donne le nom, la description, l'adresse de la documentation et si une clé est nécessaire. Ensuite, lis la documentation avec web_fetch "
                   "puis appelle l'API avec api_get. Par défaut : seulement les API SANS clé. Skill « apis-publiques » : exemples prêts à l'emploi.")
    parameters = {"type": "object", "properties": {
        "query": {"type": "string", "description": "Thème ou mots-clés (français ou anglais)"},
        "category": {"type": "string", "description": "Catégorie facultative (ex. Animals, Weather, Finance)"},
        "keyless_only": {"type": "boolean", "description": "Seulement les API sans clé (défaut : oui)"}},
        "required": ["query"]}
    permission = Permission.AUTO

    async def execute(self, query: str = "", category: str = "", keyless_only: bool = True, **_: Any) -> dict:
        if not catalog():
            return {"error": "Catalogue d'API introuvable."}
        res = search(query, category, bool(keyless_only))
        if not res:
            return {"results": [], "note": "Rien trouvé. Catégories : " + ", ".join(categories())}
        return {"results": [{"name": e["n"], "about": e["d"], "category": e["c"], "docs": e["u"], "key": e["a"] or "aucune", "https": e["h"]} for e in res]}


class ApiGetTool(Tool):
    name = "api_get"
    description = ("Appelle une API publique en GET (HTTPS) et renvoie sa réponse JSON. Réseau public uniquement, aucune clé ni donnée personnelle : "
                   "ne mets jamais de mot de passe ou de jeton dans l'adresse. Exemple : https://restcountries.com/v3.1/name/france?fields=name,capital")
    parameters = {"type": "object", "properties": {
        "url": {"type": "string", "description": "Adresse complète de l'API (https://…)"},
        "params": {"type": "object", "description": "Paramètres de requête facultatifs (clé -> valeur)"}},
        "required": ["url"]}
    permission = Permission.AUTO

    async def execute(self, url: str = "", params: dict | None = None, **_: Any) -> dict:
        if not url.startswith(("https://", "http://")):
            return {"error": "URL invalide : doit commencer par https://"}
        if re.search(r"(?i)[?&;](?:api_?key|apikey|key|token|access_token|secret|password|passwd|auth)=[^&]{6,}", url) or urlparse(url).username:
            return {"error": "Pas de clé, jeton ou mot de passe dans l'adresse : EVA n'envoie pas de secrets à une API publique."}
        if params:
            if not isinstance(params, dict):
                return {"error": "params doit être un objet clé -> valeur."}
            url += ("&" if "?" in url else "?") + urlencode({str(k): str(v) for k, v in list(params.items())[:20]})
        current = url
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, follow_redirects=False) as client:
            for _i in range(MAX_REDIRECTS + 1):
                bad = await asyncio.to_thread(_check_url_safe, current)       # chaque destination est revérifiée (anti-SSRF)
                if bad:
                    return {"error": bad}
                try:
                    resp = await client.get(current)
                except httpx.HTTPError as exc:
                    return {"error": f"API injoignable : {exc}"}
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                break
            else:
                return {"error": "Trop de redirections."}
        if resp.status_code >= 400:
            hint = " (cette API demande peut-être une clé)" if resp.status_code in (401, 403) else ""
            return {"error": f"L'API a répondu {resp.status_code}{hint}.", "body": resp.text[:300]}
        ctype = resp.headers.get("content-type", "")
        try:
            data = resp.json()
        except ValueError:
            if "text" in ctype or "xml" in ctype:
                return {"url": current, "text": resp.text[:MAX_RESULT_CHARS], "truncated": len(resp.text) > MAX_RESULT_CHARS}
            return {"error": f"Réponse non exploitable ({ctype or 'type inconnu'})."}
        dump = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if len(dump) <= MAX_RESULT_CHARS:
            return {"url": current, "data": data}
        return {"url": current, "data_excerpt": dump[:MAX_RESULT_CHARS], "truncated": True,
                "note": "Réponse trop longue, tronquée : affine avec des paramètres (fields, limit…)."}
