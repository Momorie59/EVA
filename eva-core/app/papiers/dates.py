"""Outils de dates : analyse, plausibilité, préavis, seuils d'alerte, formatage français."""
from datetime import date, timedelta

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def parse_date(s) -> date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def plausible(d: date, aujourd_hui: date) -> bool:
    return date(2000, 1, 1) <= d <= aujourd_hui + timedelta(days=365 * 15)


def date_action(d: date, preavis_jours: int | None) -> date:
    if preavis_jours and preavis_jours > 0:
        return d - timedelta(days=preavis_jours)
    return d


def ajouter_annees(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 février
        return d.replace(year=d.year + n, day=28)


def projeter_annuel(d: date, aujourd_hui: date) -> date:
    """Pour un contrat à reconduction annuelle, renvoie la prochaine occurrence >= aujourd'hui."""
    n = 0
    while ajouter_annees(d, n) < aujourd_hui:
        n += 1
    return ajouter_annees(d, n)


def seuil_applicable(jours_restants: int, seuils: list[int]) -> int | None:
    """Plus petit seuil >= jours restants. -1 signifie « en retard »."""
    if jours_restants < 0:
        return -1
    candidats = [s for s in seuils if s >= jours_restants]
    return min(candidats) if candidats else None


def fr_date(d: date, avec_jour: bool = False) -> str:
    jour = "1er" if d.day == 1 else str(d.day)
    txt = f"{jour} {MOIS[d.month - 1]} {d.year}"
    return f"{JOURS[d.weekday()]} {txt}" if avec_jour else txt


def fr_delai(n: int) -> str:
    if n < 0:
        return f"en retard de {-n} jour{'s' if -n > 1 else ''}"
    if n == 0:
        return "aujourd'hui"
    if n == 1:
        return "demain"
    return f"dans {n} jours"
