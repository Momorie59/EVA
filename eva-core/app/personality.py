"""Personnalités d'EVA : un style de réponse choisi par l'utilisateur (réglage global, conservé en base)."""
import json
import re
import unicodedata

from .db import get_pool

PRESETS: dict[str, dict] = {
    "normal": {"label": "Équilibrée (par défaut)", "prompt": ""},
    "concise": {"label": "Concise", "prompt": "STYLE : réponds le plus brièvement possible, une ou deux phrases, sans introduction ni politesses superflues."},
    "chaleureuse": {"label": "Chaleureuse", "prompt": "STYLE : ton chaleureux, attentionné et encourageant, comme une amie proche, sans excès."},
    "pro": {"label": "Professionnelle", "prompt": "STYLE : ton professionnel, précis et structuré ; vouvoie seulement si l'utilisateur le fait."},
    "humour": {"label": "Pince-sans-rire", "prompt": "STYLE : une pointe d'humour sec et d'esprit, jamais au détriment de l'exactitude ni de la clarté."},
    "majordome": {"label": "Majordome (à la Jarvis)", "prompt": "STYLE : majordome britannique stylé, flegmatique et pince-sans-rire ; vouvoie la personne, "
                  "l'appelle « Monsieur » ou « Madame » (ou par son prénom précédé de « Monsieur »/« Madame » si tu le connais) ; ironie légère et élégante, "
                  "jamais blessante ; reste parfaitement exact et utile, les traits d'esprit ne remplacent jamais la réponse."},
    "pedagogue": {"label": "Pédagogue", "prompt": "STYLE : explique pas à pas avec des exemples simples, vérifie que c'est compris, évite le jargon."},
}
_ALIASES = {
    "concise": ("concis", "concise", "bref", "breve", "court", "courte"),
    "chaleureuse": ("chaleureux", "chaleureuse", "gentil", "gentille", "amical", "amicale"),
    "pro": ("pro", "professionnel", "professionnelle", "serieux", "serieuse", "formel", "formelle"),
    "humour": ("humour", "drole", "blagueur", "blagueuse", "pince sans rire", "rigolo", "rigolote"),
    "majordome": ("majordome", "butler", "jarvis", "alfred", "maitre d hotel", "sarcastique", "britannique"),
    "pedagogue": ("pedagogue", "pedagogique", "explicatif", "explicative", "prof"),
    "normal": ("normal", "normale", "standard", "par defaut", "equilibre", "equilibree", "habituel", "habituelle"),
}
_CMD = re.compile(r"\b(?:passe|mets|met|change|bascule|sois|deviens|prends|active)\b[^.?!]{0,25}?\b(?:en )?(?:mode|ton|style|personnalite)\b[ :]*(?:en |plus |d |de |du |la |le |un |une )*([a-z ]{2,25})")
_CMD2 = re.compile(r"\b(?:mode|personnalite|style)\s+([a-z ]{2,25})$")


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().replace("'", " ")) if unicodedata.category(c) != "Mn")


def detect_switch(text: str) -> str | None:
    """« Passe en mode concis », « sois plus chaleureuse » → identifiant de personnalité, sinon None."""
    t = _fold(text).strip(" .!?")
    m = _CMD.search(t) or _CMD2.search(t) or re.search(r"\b(?:sois|deviens)\s+(?:plus\s+)?([a-z ]{2,25})$", t)
    if not m:
        return None
    word = m.group(1).strip()
    for pid, names in _ALIASES.items():
        if any(word == n or word.startswith(n + " ") or word.endswith(" " + n) for n in names):
            return pid
    return None


async def get() -> str:
    async with get_pool().acquire() as conn:
        v = await conn.fetchval("SELECT value FROM kv WHERE key='personality'")
    try:
        pid = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        pid = None
    pid = pid.get("id") if isinstance(pid, dict) else pid
    return pid if pid in PRESETS else "normal"


async def set_(pid: str) -> str:
    if pid not in PRESETS:
        raise ValueError("Personnalité inconnue.")
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('personality', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                           json.dumps({"id": pid}))
    return pid


def prompt_for(pid: str) -> str:
    return PRESETS.get(pid, PRESETS["normal"])["prompt"]
