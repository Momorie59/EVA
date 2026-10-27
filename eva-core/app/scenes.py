"""Scènes toutes prêtes pour l'interface : heure/date, actualités, et détection des demandes de présentation."""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from .harness.tools.present import normalize_scene

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


_TIME = re.compile(r"\b(quelle heure|l heure|quel jour|quelle date|on est quel jour|date d aujourd|heure est il|heure qu il est)\b")
_NEWS = re.compile(r"\b(actualite|actualites|actu|infos? du monde|news|que se passe t il|qu est ce qui se passe|nouvelles du monde|dernieres infos|dernieres nouvelles)\b")
_BRIEF = re.compile(r"\b(briefing|brief du|point du (matin|jour)|programme du jour|resume de ma journee|ma journee|bilan du jour|quoi de neuf aujourd hui)\b")
_PRESENT = re.compile(r"\b(presentation|presente moi|diaporama|powerpoint|power point|slides?|diapos?)\b")
_CLEAR = re.compile(r"^\s*(eva[ ,]*)?(efface|effacer|ferme|fermer|masque|cache|retour|reviens|quitte)\b[\w ']{0,40}$")


def fold(text: str) -> str:
    return re.sub(r"[^\w ]", " ", _fold(text).replace("'", " ")).strip()


def wants_time(text: str) -> bool:
    return bool(_TIME.search(fold(text)))


_TOPIC = re.compile(r"\s*(de|des|du|sur|a|au|aux|en|dans|concernant|pour|autour)\s+(?!(le monde|monde|jour|aujourd|ce jour|la journee|maintenant)\b)\w")
_FRESH = re.compile(r"\b(actualites?|news|nouvelles|actuellement|en ce moment|actuel\w*|aujourd hui|ces derniers (jours|temps)|derniere?s? (infos?|nouvelles?)|recent\w*|situation|cette semaine|ce mois)\b")


def wants_news(text: str) -> bool:
    """Actualités GÉNÉRALES seulement : « actualités de la Bretagne » est un sujet précis → le modèle cherche lui-même sur le web."""
    f = fold(text)
    m = _NEWS.search(f)
    return bool(m) and not _TOPIC.match(f[m.end():])


def wants_fresh(text: str) -> bool:
    return bool(_FRESH.search(fold(text)))


FRESH_NUDGE = ("[Question d'actualité : appelle web_search avec une requête PRÉCISE sur le sujet demandé (garde le lieu/sujet exact, ajoute l'année en cours), "
               "puis réponds uniquement à partir des résultats, avec les dates. Ne réponds pas de mémoire et ne dérive pas vers l'actualité générale du monde.]")


_STATS = re.compile(r"\b(stats?|statistiques?|etat du (serveur|nas|systeme)|comment va (le |mon )?(serveur|nas|ia)|(mon |le )?serveur ia|mon ia local\w*|dashboard)\b")


def wants_stats(text: str) -> bool:
    return bool(_STATS.search(fold(text)))


def wants_briefing(text: str) -> bool:
    return bool(_BRIEF.search(fold(text)))


def briefing_scene(tz: str, weather: dict | None, news: list[dict], stats: dict | None, now: datetime | None = None) -> dict:
    """Briefing parlé + affiché : heure, météo, gros titres, état du serveur."""
    clock = clock_scene(tz, now)
    slides = [{"title": f"Bonjour — {clock['time']}", "emoji": "👋", "bullets": [clock["date"]]}]
    if weather and not weather.get("error"):
        cur = weather.get("current", {})
        bullets = [f"{cur.get('temperature_c')} °C, {cur.get('condition')}, vent {cur.get('windspeed_kmh')} km/h"]
        rows = [[f.get("date", ""), f"{f.get('temp_min')}° / {f.get('temp_max')}°", f"{f.get('precipitation_probability_max')} %", f.get("condition", "")]
                for f in (weather.get("forecast") or [])[:4]]
        slide = {"title": f"Météo — {weather.get('city', '')}", "emoji": "⛅", "bullets": bullets}
        if rows:
            slide["table"] = {"headers": ["Jour", "Min / Max", "Pluie", "Ciel"], "rows": rows}
        slides.append(slide)
    heads = [(r.get("title") or "").strip()[:110] for r in news[:5] if (r.get("title") or "").strip()]
    if heads:
        slides.append({"title": "À la une", "emoji": "📰", "bullets": heads})
    if stats and "cpu_percent" in stats:
        slides.append({"title": "Serveur", "emoji": "🖥", "bullets": [
            f"Processeur {stats['cpu_percent']:.0f} %", f"Mémoire {stats['memory']['percent']:.0f} %", f"Disque {stats['disk']['percent']:.0f} %"]})
    return normalize_scene("Briefing", slides)


def wants_presentation(text: str) -> bool:
    return bool(_PRESENT.search(fold(text)))


def is_clear_command(text: str) -> bool:
    return bool(_CLEAR.match(fold(text)))


def clock_scene(tz: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(ZoneInfo(tz))
    return {
        "kind": "clock", "title": "Il est", "tz": tz,
        "time": now.strftime("%H:%M"),
        "date": f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}",
        "iso": now.isoformat(),
    }


def news_scene(results: list[dict], query: str) -> dict:
    slides = []
    for r in results[:8]:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        slide = {"title": title[:90], "emoji": "📰"}
        if r.get("snippet"):
            slide["bullets"] = [r["snippet"][:220]]
        if r.get("url"):
            slide["note"] = r["url"]
        slides.append(slide)
    return normalize_scene("À la une", slides) if slides else {}


PRESENT_NUDGE = (
    "Cette demande est une présentation : appelle l'outil present pour l'afficher à l'écran en diaporama "
    "(4 à 8 diapos claires : titre, puces courtes, tableau ou chiffre clé si utile), puis dis une seule phrase. "
    "Si tu as besoin de faits récents, cherche d'abord avec web_search."
)


_IMAGE_FOLLOWUP = re.compile(r"\b(image|photo|photos|cliche|capture|screenshot|tu vois|vois tu|regarde|sur la photo|dans l image|sur l image|ce que je t ai montre)\b")


def refers_to_image(text: str) -> bool:
    """Question de suivi sur la dernière photo envoyée (« et sur la photo, il y a quoi ? »)."""
    return bool(_IMAGE_FOLLOWUP.search(fold(text)))
