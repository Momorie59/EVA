"""Préparer le texte avant de le lire à voix haute (français) : heures, températures, unités, symboles, émojis, Markdown.
Sans ça, la voix lit « 21 h 45 » comme « vingt et un hache quarante-cinq », « °C » lettre par lettre, ou bute sur les émojis."""
import re

_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️\u2b00-\u2bff]+")
_REMPLACEMENTS = [
    (re.compile(r"\*\*|__|`+|^#+\s*|^\s*[-*•]\s+", re.M), ""),           # Markdown
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),                       # [texte](lien) → texte
    (re.compile(r"https?://\S+"), "le lien"),
    (re.compile(r"(\d{1,2})\s*[hH]\s*(\d{2})\b"), r"\1 heures \2"),        # 21 h 45, 21h45
    (re.compile(r"(\d{1,2}):(\d{2})\b"), r"\1 heures \2"),                # 21:45
    (re.compile(r"\b1\s*[hH]\b"), "une heure"),
    (re.compile(r"(\d{1,2})\s*[hH]\b"), r"\1 heures"),                    # 21 h
    (re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°\s*C\b"), r"\1 degrés"),
    (re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°"), r"\1 degrés"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*km/h\b"), r"\1 kilomètres heure"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*km\b"), r"\1 kilomètres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*mm\b"), r"\1 millimètres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*cm\b"), r"\1 centimètres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b"), r"\1 kilos"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*g\b"), r"\1 grammes"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*ml\b"), r"\1 millilitres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*cl\b"), r"\1 centilitres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*l\b"), r"\1 litres"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*min\b"), r"\1 minutes"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*s\b"), r"\1 secondes"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*%"), r"\1 pour cent"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*€"), r"\1 euros"),
    (re.compile(r"€\s*(\d+(?:[.,]\d+)?)"), r"\1 euros"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*\$"), r"\1 dollars"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*Go\b"), r"\1 gigaoctets"),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*Mo\b"), r"\1 mégaoctets"),
    (re.compile(r"(\d),(\d)"), r"\1 virgule \2"),
    (re.compile(r"\bn°\s*", re.I), "numéro "),
    (re.compile(r"\bM\.\s+(?=[A-Z])"), "Monsieur "),
    (re.compile(r"\bMme\b\.?"), "Madame"),
    (re.compile(r"\betc\.?", re.I), "et cetera"),
    (re.compile(r"\bp\.\s*ex\.?", re.I), "par exemple"),
    (re.compile(r"\bex\.\s"), "exemple, "),
    (re.compile(r"\bRDV\b", re.I), "rendez-vous"),
    (re.compile(r"\bEVA\b"), "Éva"),
    (re.compile(r"\s*→\s*"), ", "),
    (re.compile(r"\s*[|•·]\s*"), ", "),
    (re.compile(r"&"), " et "),
    (re.compile(r"\s+/\s+"), " ou "),
    (re.compile(r"[«»\"“”]"), ""),
    (re.compile(r"\b(1|un|une) (litre|kilo|gramme|minute|seconde|degré|euro|kilomètre|centimètre|millilitre|centilitre|heure)s\b"), r"\1 \2"),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+([,.;:!?])"), r"\1"),
]


def preparer(texte: str, langue: str = "fr") -> str:
    t = _EMOJI.sub(" ", texte or "")
    if langue == "fr":
        for motif, remplacement in _REMPLACEMENTS:
            t = motif.sub(remplacement, t)
    else:
        t = re.sub(r"\*\*|__|`+|^#+\s*", "", t, flags=re.M)
        t = re.sub(r"https?://\S+", "", t)
    return t.strip()
