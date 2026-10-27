"""Raccourci météo : si la question porte clairement sur la météo, EVA va chercher
les données elle-même (outil weather_get) au lieu de compter sur le modèle pour
penser à appeler l'outil. Les petits modèles rapides (mode vocal) l'oublient
souvent et répondent « je ne peux pas accéder à la météo »."""
import json
import re
import unicodedata

_WEATHER = re.compile(
    r"\b(meteo|temps qu.il fait|quel temps|fait.il (chaud|froid|beau)|va.t.il (pleuvoir|neiger)|"
    r"pleuvoir|prevision|previsions|temperature (dehors|exterieure)|il pleut|il neige)\b"
)
_PREP = re.compile(r"(?:^|[\s,;(])(?:a|à|de|du|pour|sur|dans|en|au|aux|vers|chez)\s+((?:[\w'’\-]+)(?:\s+[\w'’\-]+){0,4})", re.IGNORECASE)
_BAD_FIRST = {"le", "la", "les", "l", "un", "une", "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "quel", "quelle", "moi", "nous", "toi", "lui", "elle",
              "eva", "demain", "aujourd'hui", "aujourdhui", "ce", "maintenant", "ici", "cet", "tout", "toute", "cours", "plus", "fait", "faire", "quoi", "que", "qui", "il", "ils"}
_CUT = {"aujourd'hui", "aujourdhui", "demain", "apres-demain", "apres", "ce", "cet", "cette", "ces", "matin", "soir", "midi", "week-end", "weekend", "semaine", "maintenant",
        "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche", "et", "svp", "stp", "s'il", "please", "merci", "ou", "avec", "pour", "car", "alors", "il", "elle",
        "est", "fait", "va", "vais", "pleut", "pleuvoir", "neige", "chaud", "froid", "beau", "temps", "meteo", "demain,", "quel", "quelle", "eva", "prochain", "prochains", "prochaine"}
_JOIN = {"le", "la", "les", "sur", "sous", "en", "de", "du", "des", "d'", "l'", "au", "aux", "lès", "les"}
_DAYS = re.compile(r"\b(semaine|7 jours|sept jours)\b")


def _title(tokens: list[str]) -> str:
    return " ".join(t if t.lower() in _JOIN else t[:1].upper() + t[1:] for t in tokens)


def _city_from(text: str) -> str | None:
    for m in _PREP.finditer(text):
        toks = m.group(1).split()
        if _fold(toks[0]) in _BAD_FIRST or _fold(toks[0]) in _CUT or toks[0].lower().startswith(("l'", "d'")):
            continue
        keep: list[str] = []
        for t in toks:
            if _fold(t) in _CUT:
                break
            keep.append(t)
        while keep and keep[-1].lower() in _JOIN:             # « Lons le » → « Lons »
            keep.pop()
        if keep:
            return _title(keep)
    return None


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def detect(text: str, default_city: str) -> dict | None:
    """Renvoie {city, days} si la phrase demande la météo, sinon None."""
    if not _WEATHER.search(_fold(text)):
        return None
    city = _city_from(text) or default_city
    days = 7 if _DAYS.search(_fold(text)) else 4
    return {"city": city, "days": days}


def context_block(result: dict) -> str:
    return (
        "[Données météo réelles fournies par EVA (outil weather_get) — utilise-les, "
        "ne dis jamais que tu n'as pas accès à la météo. Une carte détaillée est déjà "
        "affichée à l'utilisateur : fais un commentaire court et utile, sans recopier tout le tableau.]\n"
        + json.dumps(result, ensure_ascii=False)
    )
