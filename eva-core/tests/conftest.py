"""Faux Paperless / faux Ollama pour tester les papiers sans aucun service réel."""
import asyncio
from datetime import date

import pytest

from app import papiers
from app.papiers.config import Reglages
from app.papiers.db import DB
from app.papiers.moteur import Majordome
from integration_pg import eva  # noqa: F401 — EVA complète + Postgres (tests d'intégration)

AUJ = date(2026, 10, 22)


class FauxPaperless:
    def __init__(self, docs: dict):
        self.docs = docs
        self.tags: dict = {}
        self.deposes: list = []
        self.panne = False

    def ping(self):
        self._check()
        return True

    def _check(self):
        if self.panne:
            import httpx
            raise httpx.ConnectError("hors ligne")

    def tous_les_ids(self):
        self._check()
        return sorted(self.docs)

    def document(self, i):
        return self.docs[i]

    def recherche(self, t, limite=5):
        self.requetes = getattr(self, "requetes", []) + [t]
        mots = [m.lower() for m in t.split(" OR ")]
        return [d for d in self.docs.values() if any(m in d["content"].lower() for m in mots)][:limite]

    def ajouter_tag(self, i, t):
        self.tags.setdefault(i, set()).add(t)

    def retirer_tag(self, i, t):
        self.tags.setdefault(i, set()).discard(t)

    def lien(self, i):
        return f"http://paperless/documents/{i}/details"

    def deposer(self, nom, donnees, titre=None):
        self._check()
        self.deposes.append((nom, len(donnees)))
        return f"tache-{len(self.deposes)}"


class FauxOllama:
    def __init__(self, reponses: dict):
        self.reponses = reponses
        self.noms = ["llama3.1:8b"]

    def modeles(self):
        return list(self.noms)

    def chat_json(self, system, user, schema):
        for titre, rep in self.reponses.items():
            if titre in user:
                if isinstance(rep, Exception):
                    raise rep
                return rep
        return {"type_document": "autre", "pays": "FR", "emetteur": "", "resume": "", "montant": None,
                "devise": None, "echeances": [], "confiance": 0.95}

    def chat(self, system, user):
        self.dernier_contexte = user
        return "La garantie court jusqu'au 14 mars 2027."


ASSURANCE = {"type_document": "assurance", "pays": "FR", "emetteur": "MAIF",
             "resume": "Avis d'échéance assurance habitation", "montant": 312.4, "devise": "EUR",
             "echeances": [{"nature": "renouvellement", "date": "2026-12-01",
                            "description": "Renouvellement assurance habitation MAIF",
                            "preavis_jours": 30, "recurrence": "annuelle", "montant": 312.4}],
             "confiance": 0.92}
TARI = {"type_document": "impot", "pays": "IT", "emetteur": "Comune di Cefalù", "resume": "Avviso TARI",
        "montant": 180.0, "devise": "EUR",
        "echeances": [{"nature": "paiement", "date": "2026-10-29", "description": "Paiement TARI",
                       "preavis_jours": None, "recurrence": "aucune", "montant": 180.0}],
        "confiance": 0.55}
DOCS = {
    1: {"id": 1, "title": "Avis MAIF", "content": "MAIF habitation échéance 01/12/2026 préavis 1 mois", "created": "2026-10-01"},
    2: {"id": 2, "title": "Avviso TARI", "content": "TARI scadenza 29/10/2026 euro 180", "created": "2026-10-10"},
    3: {"id": 3, "title": "Ticket de caisse", "content": "Boulangerie 3,20 garantie lave-linge", "created": "2026-10-12"},
    4: {"id": 4, "title": "Doc cassé", "content": "???", "created": "2026-10-12"},
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Moteur des papiers branché sur de faux services, installé comme moteur d'EVA."""
    monkeypatch.setenv("EVA_PAPIERS_RACINE", str(tmp_path / "nas"))
    (tmp_path / "nas").mkdir()
    reg = Reglages()
    reg.paperless_url, reg.paperless_token, reg.ollama_model = "http://paperless:8000", "jeton", "llama3.1:8b"
    reg.alert_days = [30, 7, 1, 0]
    p = FauxPaperless(dict(DOCS))
    o = FauxOllama({"Avis MAIF": ASSURANCE, "Avviso TARI": TARI, "Doc cassé": RuntimeError("timeout")})
    m = Majordome(reg, DB(str(tmp_path / "papiers.db")), p, o)
    m.aujourd_hui = lambda: AUJ
    papiers._installer(m)
    yield m, p, o, tmp_path
    papiers._installer(None)


def run(coro):
    return asyncio.run(coro)
