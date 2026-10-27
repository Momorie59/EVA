"""IA gratuites : la liste « awesome-free-llm-apis » (github.com/mnfst/awesome-free-llm-apis, licence CC0) dans EVA.

Des services en ligne offrent un accès gratuit et permanent à de gros modèles (Gemini, Mistral, Groq, OpenRouter…). EVA
en garde une copie (data/ia_gratuites.json), que l'administrateur peut mettre à jour d'un clic. Chaque service s'ajoute
aux « IA du marché » en un clic (adresse et modèles préremplis, prix 0) ; il ne reste qu'à coller la clé gratuite — et
pour certains, aucune clé n'est nécessaire. Comme pour toute IA du marché, les messages partent alors sur Internet :
la liste signale les services qui peuvent s'en servir pour entraîner leurs modèles."""
import json
import re
from pathlib import Path

import httpx

from .db import get_pool

SOURCE = "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json"
PAGE = "https://github.com/mnfst/awesome-free-llm-apis"
KV = "ia_gratuites"
COPIE = Path(__file__).parent / "data" / "ia_gratuites.json"

# Adresse « compatible OpenAI » quand celle de la liste ne l'est pas (EVA parle le format OpenAI).
_ADRESSES = [
    (re.compile(r"^https://generativelanguage\.googleapis\.com/v1beta/?$"), "https://generativelanguage.googleapis.com/v1beta/openai"),
    (re.compile(r"^https://api\.cohere\.(?:com|ai)/v\d/?$"), "https://api.cohere.ai/compatibility/v1"),
    (re.compile(r"^https://ollama\.com/api/?$"), "https://ollama.com/v1"),
    (re.compile(r"^(https://api\.cloudflare\.com/client/v4/accounts/\{account_id\}/ai)/run/?$"), r"\1/v1"),
]
_SANS_CLE = re.compile(r"no (?:api )?key(?: required)?|anonymous (?:access|tier)|without (?:an )?(?:api )?key|no signup", re.I)
_ENTRAINEMENT = re.compile(r"\btrain|improve (?:their |its )?products|may (?:be )?log|log prompts|used by \w+ to improve", re.I)
_NON_TEXTE = re.compile(r"embedding|moderation|speech|audio only|image generation", re.I)
_VERIF = re.compile(r"phone verification|identity verification|real-name|(?<!no )credit card required|membership|non-commercial", re.I)
_UE = re.compile(r"except for users in the EEA|EEA[^.]{0,80}not used", re.I)
_FR = {"phone verification": "vérification par téléphone", "identity verification": "pièce d'identité demandée",
       "real-name": "vérification d'identité", "membership": "inscription à un programme développeur",
       "non-commercial": "usage non commercial seulement", "credit card required": "carte bancaire demandée"}


class GratuitesError(RuntimeError):
    pass


def _slug(nom: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", nom.lower()).strip("-")
    return (s or "gratuit")[:24]


def adresse_openai(url: str) -> str:
    u = (url or "").strip()
    for motif, rempl in _ADRESSES:
        if motif.match(u):
            return motif.sub(rempl, u)
    return u.rstrip("/")


def normaliser(data: dict) -> dict:
    notes = {f.get("id"): f.get("text", "") for f in data.get("footnotes", []) if isinstance(f, dict)}
    out = []
    for p in data.get("providers", []):
        if not isinstance(p, dict) or not p.get("baseUrl") or not p.get("name"):
            continue
        texte = f"{p.get('description', '')} {notes.get(p.get('footnoteRef'), '')}"
        modeles = []
        for m in p.get("models", []):
            mid = m.get("id")
            if not mid or _NON_TEXTE.search(m.get("modality", "")):
                continue
            mod = m.get("modality", "")
            modeles.append({"id": mid, "nom": m.get("name", mid), "contexte": m.get("context", ""), "limite": m.get("rateLimit", ""),
                            "vision": bool(re.search(r"image|vision|multimodal", mod, re.I)), "raisonnement": "reasoning" in mod.lower(),
                            "code": "code" in mod.lower()})
        if not modeles:
            continue
        base = adresse_openai(p["baseUrl"])
        conditions = sorted({_FR[k.lower()] for k in (x.group(0) for x in _VERIF.finditer(texte)) if k.lower() in _FR})
        out.append({
            "nom": p["name"], "id": _slug(p["name"]), "drapeau": p.get("flag", ""), "pays": p.get("country", ""),
            "page_cle": p.get("url", ""), "base_url": base, "categorie": p.get("category", ""),
            "cle_facultative": bool(_SANS_CLE.search(p.get("description", ""))),
            "compte_cloudflare": "{account_id}" in base,
            # « oui » : tes messages peuvent servir à entraîner leurs modèles ; « hors_ue » : pas pour les utilisateurs européens
            "entrainement": ("hors_ue" if _UE.search(texte) else "oui") if _ENTRAINEMENT.search(texte) else "",
            "conditions": conditions,
            "description": p.get("description", ""), "modeles": modeles,
        })
    return {"maj": data.get("lastUpdated", ""), "source": PAGE, "services": out}


async def _brut() -> dict:
    try:
        async with get_pool().acquire() as conn:
            raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
        if raw:
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001 — base indisponible : la copie livrée avec EVA
        pass
    return json.loads(COPIE.read_text(encoding="utf-8"))


async def catalogue() -> dict:
    return normaliser(await _brut())


async def mettre_a_jour() -> dict:
    """Télécharge la dernière version de la liste (GitHub) et la garde dans la base d'EVA."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(SOURCE)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GratuitesError(f"Liste injoignable ({type(exc).__name__}) : la copie actuelle est conservée.") from exc
    if not isinstance(data, dict) or not normaliser(data)["services"]:
        raise GratuitesError("Liste reçue illisible : la copie actuelle est conservée.")
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps(data))
    return normaliser(data)
