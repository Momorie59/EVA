"""Extraction des échéances d'un document via le LLM local, puis validation stricte côté Python."""
from dataclasses import dataclass, field
from datetime import date

from .dates import parse_date, plausible, date_action, projeter_annuel, ajouter_annees

TYPES = ["facture", "contrat", "assurance", "garantie", "abonnement", "impot",
         "banque", "sante", "administratif", "autre"]
NATURES = ["paiement", "renouvellement", "resiliation_limite", "fin_garantie",
           "declaration", "rendez_vous", "expiration", "autre"]
RECURRENCES = ["aucune", "mensuelle", "annuelle"]

SCHEMA = {
    "type": "object",
    "properties": {
        "type_document": {"type": "string", "enum": TYPES},
        "pays": {"type": "string", "enum": ["FR", "IT", "autre"]},
        "emetteur": {"type": "string"},
        "resume": {"type": "string"},
        "montant": {"type": ["number", "null"]},
        "devise": {"type": ["string", "null"]},
        "echeances": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nature": {"type": "string", "enum": NATURES},
                    "date": {"type": "string"},
                    "description": {"type": "string"},
                    "preavis_jours": {"type": ["integer", "null"]},
                    "recurrence": {"type": "string", "enum": RECURRENCES},
                    "montant": {"type": ["number", "null"]},
                },
                "required": ["nature", "date", "description", "preavis_jours", "recurrence", "montant"],
            },
        },
        "confiance": {"type": "number"},
    },
    "required": ["type_document", "pays", "emetteur", "resume", "montant", "devise", "echeances", "confiance"],
}

SYSTEM = """Tu es l'assistant administratif d'une famille (documents en français, en italien ou dans d'autres langues).
Tu lis le texte OCR d'un document (français ou italien) et tu en extrais UNIQUEMENT ce qui y est écrit.

Règles :
- N'invente jamais de date. Une échéance sans date explicite ou calculable à partir du texte ne doit pas apparaître.
- Dates au format AAAA-MM-JJ. Les documents italiens et français écrivent souvent JJ/MM/AAAA : convertis correctement.
- Facture : une échéance « paiement » seulement si une date limite de paiement figure.
- Contrat, assurance, abonnement : la date de renouvellement ou de fin. Si le texte parle de tacite reconduction
  (« tacite reconduction », « tacito rinnovo ») indique recurrence « annuelle » si la période est d'un an.
  Si un préavis de résiliation est indiqué (« 2 mois avant », « disdetta 60 giorni prima »), mets-le en jours dans preavis_jours.
- Facture d'achat d'un appareil ou d'un bien durable : échéance « fin_garantie » = date d'achat + durée de garantie indiquée ;
  si aucune durée n'est indiquée, 2 ans (garantie légale UE) en le précisant dans la description.
- Impôts (impots.gouv, Agenzia delle Entrate, IMU, TARI, taxe foncière...) : dates limites de paiement ou de déclaration.
- Pièces d'identité, permis, contrôle technique, revisione : nature « expiration » avec la date de fin de validité.
- resume : une phrase courte en français décrivant le document.
- description de chaque échéance : courte, en français, compréhensible seule (ex. « Renouvellement assurance habitation MAIF »).
- confiance : entre 0 et 1, ta certitude globale sur l'exactitude des dates extraites.
- S'il n'y a aucune échéance, renvoie une liste vide."""


def construire_message(doc: dict, aujourd_hui: date, max_chars: int) -> str:
    contenu = (doc.get("content") or "").strip()
    if len(contenu) > max_chars:
        tete = int(max_chars * 0.75)
        contenu = contenu[:tete] + "\n[...]\n" + contenu[-(max_chars - tete):]
    return (f"Date du jour : {aujourd_hui.isoformat()}\n"
            f"Titre du document : {doc.get('title', '')}\n"
            f"Date du document (selon Paperless) : {(doc.get('created') or '')[:10]}\n"
            f"--- TEXTE OCR ---\n{contenu}\n--- FIN ---")


@dataclass
class EcheanceX:
    nature: str
    description: str
    date_echeance: date
    preavis_jours: int | None
    date_action: date
    montant: float | None
    statut: str
    projetee: bool = False


@dataclass
class Extraction:
    type_document: str
    pays: str
    emetteur: str
    resume: str
    montant: float | None
    devise: str | None
    confiance: float
    echeances: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)
    statut: str = "traite"


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def normaliser(brut: dict, aujourd_hui: date, seuil_confiance: float) -> Extraction:
    av = []
    type_doc = brut.get("type_document") if brut.get("type_document") in TYPES else "autre"
    try:
        confiance = max(0.0, min(1.0, float(brut.get("confiance", 0))))
    except (TypeError, ValueError):
        confiance = 0.0

    ex = Extraction(
        type_document=type_doc,
        pays=brut.get("pays") if brut.get("pays") in ("FR", "IT") else "autre",
        emetteur=(brut.get("emetteur") or "").strip()[:200],
        resume=(brut.get("resume") or "").strip()[:500],
        montant=_num(brut.get("montant")),
        devise=(brut.get("devise") or None),
        confiance=confiance,
    )

    vus = set()
    for e in brut.get("echeances") or []:
        if not isinstance(e, dict):
            continue
        d = parse_date(e.get("date"))
        if d is None:
            av.append(f"date illisible ignorée : {e.get('date')!r}")
            continue
        if not plausible(d, aujourd_hui):
            av.append(f"date improbable ignorée : {d.isoformat()}")
            continue
        nature = e.get("nature") if e.get("nature") in NATURES else "autre"
        preavis = e.get("preavis_jours")
        preavis = int(preavis) if isinstance(preavis, (int, float)) and 0 < preavis <= 365 else None
        recurrence = e.get("recurrence") if e.get("recurrence") in RECURRENCES else "aucune"
        description = (e.get("description") or nature).strip()[:300]

        projetee = False
        if recurrence == "annuelle" and date_action(d, preavis) < aujourd_hui:
            origine = d
            d = projeter_annuel(d, aujourd_hui)
            if date_action(d, preavis) < aujourd_hui:
                # préavis déjà dépassé cette année : on vise l'occurrence suivante
                d = ajouter_annees(d, 1)
            if d != origine:
                projetee = True
                description += f" (projeté depuis le {origine.isoformat()})"
                av.append("échéance annuelle projetée sur la prochaine occurrence")

        cle = (nature, d)
        if cle in vus:
            continue
        vus.add(cle)

        da = date_action(d, preavis)
        statut = "passee" if d < aujourd_hui else "active"
        ex.echeances.append(EcheanceX(nature, description, d, preavis, da, _num(e.get("montant")), statut, projetee))

    ex.avertissements = av
    a_risque = type_doc in ("contrat", "assurance", "abonnement", "garantie")
    if confiance < seuil_confiance or any(e.projetee for e in ex.echeances):
        ex.statut = "a_valider"
    elif not ex.echeances:
        ex.statut = "a_valider" if (a_risque and confiance < 0.9) else "sans_echeance"
    else:
        ex.statut = "traite"

    if ex.statut == "a_valider":
        for e in ex.echeances:
            if e.statut == "active":
                e.statut = "a_valider"
    return ex
